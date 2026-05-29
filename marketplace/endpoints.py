"""
marketplace/endpoints.py
FastAPI router for the Marketplace.
Mount in main.py:
  from marketplace.endpoints import router as marketplace_router
  app.include_router(marketplace_router)
"""

from __future__ import annotations
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from loguru import logger

from db.database import AsyncSessionLocal
from db.models_marketplace import MarketplaceListing, MarketplacePurchase, ListingType, ListingStatus
from db.models_appbuilder import AppProject
from services.user import UserService

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


def _require_tg_id(request: Request) -> int:
    tid = request.headers.get("X-Telegram-User-Id", "")
    if not tid.isdigit():
        raise HTTPException(401, "Missing X-Telegram-User-Id header")
    return int(tid)


def _listing_to_dict(l: MarketplaceListing, owned: bool = False) -> dict:
    return {
        "id":           str(l.id),
        "title":        l.title,
        "description":  l.description,
        "platform":     l.platform,
        "listing_type": l.listing_type.value,
        "price_usd":    l.price_usd,
        "rent_price_usd": l.rent_price_usd,
        "tags":         l.tags or [],
        "preview_code": l.preview_code,
        "version":      l.version,
        "status":       l.status.value,
        "downloads":    l.downloads,
        "purchases":    l.purchases,
        "avg_rating":   l.avg_rating,
        "rating_count": l.rating_count,
        "whop_checkout_url": l.whop_checkout_url if not owned else None,
        "created_at":   l.created_at.isoformat() if l.created_at else None,
    }


# ── GET /api/marketplace ──────────────────────────────────────────────────────
@router.get("")
async def list_marketplace(
    request: Request,
    platform: Optional[str] = Query(None),
    listing_type: Optional[str] = Query(None),
    q: Optional[str] = Query(None),          # search query
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
):
    """Browse active marketplace listings."""
    async with AsyncSessionLocal() as db:
        query = (
            select(MarketplaceListing)
            .where(MarketplaceListing.status == ListingStatus.ACTIVE)
        )
        if platform:
            query = query.where(MarketplaceListing.platform == platform.lower())
        if listing_type:
            query = query.where(MarketplaceListing.listing_type == listing_type)
        if q:
            term = f"%{q.lower()}%"
            query = query.where(
                or_(
                    func.lower(MarketplaceListing.title).like(term),
                    func.lower(MarketplaceListing.description).like(term),
                )
            )

        # Count
        count_r = await db.execute(select(func.count()).select_from(query.subquery()))
        total = count_r.scalar() or 0

        # Page
        offset = (page - 1) * per_page
        query = query.order_by(MarketplaceListing.purchases.desc()).offset(offset).limit(per_page)
        result = await db.execute(query)
        listings = result.scalars().all()

    return {
        "ok": True,
        "total": total,
        "page": page,
        "per_page": per_page,
        "listings": [_listing_to_dict(l) for l in listings],
    }


# ── GET /api/marketplace/{listing_id} ────────────────────────────────────────
@router.get("/{listing_id}")
async def get_listing(listing_id: UUID, request: Request):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MarketplaceListing).where(MarketplaceListing.id == listing_id)
        )
        listing = result.scalar_one_or_none()
        if not listing or listing.status == ListingStatus.REMOVED:
            raise HTTPException(404, "Listing not found")

    return {"ok": True, "listing": _listing_to_dict(listing)}


# ── POST /api/marketplace/listings — Create listing ──────────────────────────
class CreateListingRequest(BaseModel):
    title: str
    description: str
    platform: str
    listing_type: str          # sell | rent | free
    price_usd: float = 0.0
    rent_price_usd: float = 0.0
    tags: list[str] = []
    preview_code: Optional[str] = None
    version: str = "1.0"
    whop_product_id: Optional[str] = None
    whop_checkout_url: Optional[str] = None
    project_id: Optional[str] = None    # link to an AppProject


@router.post("/listings")
async def create_listing(req: CreateListingRequest, request: Request):
    telegram_id = _require_tg_id(request)

    # Validate
    try:
        lt = ListingType(req.listing_type)
    except ValueError:
        raise HTTPException(400, "listing_type must be sell, rent, or free")

    if lt != ListingType.FREE and req.price_usd <= 0 and req.rent_price_usd <= 0:
        raise HTTPException(400, "Price must be > 0 for paid listings")

    if lt in (ListingType.SELL, ListingType.RENT) and not req.whop_checkout_url:
        raise HTTPException(400, "whop_checkout_url is required for paid listings")

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=telegram_id)
        if not user.has_product_access(1):
            raise HTTPException(403, "Listing requires an active trial or paid plan")

        project_uuid = UUID(req.project_id) if req.project_id else None

        listing = MarketplaceListing(
            seller_user_id=user.id,
            project_id=project_uuid,
            title=req.title,
            description=req.description,
            platform=req.platform.lower(),
            listing_type=lt,
            price_usd=req.price_usd,
            rent_price_usd=req.rent_price_usd,
            tags=req.tags,
            preview_code=req.preview_code,
            version=req.version,
            whop_product_id=req.whop_product_id,
            whop_checkout_url=req.whop_checkout_url,
            status=ListingStatus.ACTIVE,  # auto-approve for now
        )
        db.add(listing)
        await db.flush()

        # Update the project if linked
        if project_uuid:
            proj_r = await db.execute(
                select(AppProject).where(
                    AppProject.id == project_uuid,
                    AppProject.user_id == user.id,
                )
            )
            proj = proj_r.scalar_one_or_none()
            if proj:
                proj.listed_on_marketplace = True
                proj.marketplace_listing_id = listing.id

        await db.commit()
        listing_id = str(listing.id)

    return {
        "ok": True,
        "listing_id": listing_id,
        "message": "Listing is now active on the marketplace.",
    }


# ── PATCH /api/marketplace/listings/{listing_id} — Edit listing ──────────────
class UpdateListingRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price_usd: Optional[float] = None
    rent_price_usd: Optional[float] = None
    tags: Optional[list[str]] = None
    preview_code: Optional[str] = None
    version: Optional[str] = None
    whop_checkout_url: Optional[str] = None
    status: Optional[str] = None    # paused | active


@router.patch("/listings/{listing_id}")
async def update_listing(listing_id: UUID, req: UpdateListingRequest, request: Request):
    telegram_id = _require_tg_id(request)
    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=telegram_id)

        result = await db.execute(
            select(MarketplaceListing).where(
                MarketplaceListing.id == listing_id,
                MarketplaceListing.seller_user_id == user.id,
            )
        )
        listing = result.scalar_one_or_none()
        if not listing:
            raise HTTPException(404, "Listing not found or not yours")

        if req.title is not None:       listing.title = req.title
        if req.description is not None: listing.description = req.description
        if req.price_usd is not None:   listing.price_usd = req.price_usd
        if req.rent_price_usd is not None: listing.rent_price_usd = req.rent_price_usd
        if req.tags is not None:        listing.tags = req.tags
        if req.preview_code is not None: listing.preview_code = req.preview_code
        if req.version is not None:     listing.version = req.version
        if req.whop_checkout_url is not None: listing.whop_checkout_url = req.whop_checkout_url
        if req.status in ("paused", "active"):
            listing.status = ListingStatus(req.status)

        listing.updated_at = datetime.now(timezone.utc)
        await db.commit()

    return {"ok": True, "message": "Listing updated."}


# ── GET /api/marketplace/my/listings — Seller dashboard ──────────────────────
@router.get("/my/listings")
async def my_listings(request: Request):
    telegram_id = _require_tg_id(request)
    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=telegram_id)

        result = await db.execute(
            select(MarketplaceListing)
            .where(MarketplaceListing.seller_user_id == user.id)
            .order_by(MarketplaceListing.created_at.desc())
        )
        listings = result.scalars().all()

    return {
        "ok": True,
        "listings": [_listing_to_dict(l, owned=True) for l in listings],
    }


# ── GET /api/marketplace/my/purchases — Buyer library ────────────────────────
@router.get("/my/purchases")
async def my_purchases(request: Request):
    telegram_id = _require_tg_id(request)
    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=telegram_id)

        result = await db.execute(
            select(MarketplacePurchase)
            .where(
                MarketplacePurchase.buyer_user_id == user.id,
                MarketplacePurchase.active == True,
            )
            .order_by(MarketplacePurchase.purchased_at.desc())
        )
        purchases = result.scalars().all()

    return {
        "ok": True,
        "purchases": [
            {
                "id": str(p.id),
                "listing_id": str(p.listing_id),
                "listing_type": p.listing_type.value,
                "amount_paid_usd": p.amount_paid_usd,
                "active": p.active,
                "expires_at": p.expires_at.isoformat() if p.expires_at else None,
                "purchased_at": p.purchased_at.isoformat(),
            }
            for p in purchases
        ],
    }


# ── POST /api/marketplace/{listing_id}/review ─────────────────────────────────
class ReviewRequest(BaseModel):
    rating: int       # 1–5
    review_text: Optional[str] = None


@router.post("/{listing_id}/review")
async def post_review(listing_id: UUID, req: ReviewRequest, request: Request):
    telegram_id = _require_tg_id(request)
    if not (1 <= req.rating <= 5):
        raise HTTPException(400, "Rating must be 1–5")

    async with AsyncSessionLocal() as db:
        user_svc = UserService(db)
        user = await user_svc.get_or_create_user(telegram_id=telegram_id)

        # Verify they purchased it
        purchase_r = await db.execute(
            select(MarketplacePurchase).where(
                MarketplacePurchase.listing_id == listing_id,
                MarketplacePurchase.buyer_user_id == user.id,
                MarketplacePurchase.active == True,
            )
        )
        purchase = purchase_r.scalar_one_or_none()
        if not purchase:
            raise HTTPException(403, "You must purchase this app before reviewing it")

        if purchase.rating is not None:
            raise HTTPException(400, "You have already reviewed this listing")

        purchase.rating = req.rating
        purchase.review_text = req.review_text

        # Update listing aggregate rating
        listing_r = await db.execute(
            select(MarketplaceListing).where(MarketplaceListing.id == listing_id)
        )
        listing = listing_r.scalar_one_or_none()
        if listing:
            listing.rating_total += req.rating
            listing.rating_count += 1

        await db.commit()

    return {"ok": True, "message": "Review submitted."}
