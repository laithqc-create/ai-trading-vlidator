"""
db/models_marketplace.py
Marketplace models — listings, purchases, rentals.
"""

import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Text, DateTime, Boolean,
    ForeignKey, Enum as SAEnum, JSON
)
from sqlalchemy.orm import relationship
from db.database import Base
from db.models_appbuilder import UUID  # cross-db compatible UUID type


class ListingType(str, enum.Enum):
    SELL  = "sell"    # one-time purchase
    RENT  = "rent"    # recurring monthly
    FREE  = "free"    # free download


class ListingStatus(str, enum.Enum):
    DRAFT     = "draft"
    PENDING   = "pending"    # awaiting review (future)
    ACTIVE    = "active"
    PAUSED    = "paused"
    REMOVED   = "removed"


class MarketplaceListing(Base):
    __tablename__ = "marketplace_listings"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_user_id  = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id      = Column(UUID(as_uuid=True), ForeignKey("app_projects.id"), nullable=True)

    title           = Column(String(160), nullable=False)
    description     = Column(Text, nullable=False)
    platform        = Column(String(40), nullable=False)     # mql5 | pine | python
    listing_type    = Column(SAEnum(ListingType), nullable=False)
    price_usd       = Column(Float, default=0.0)             # 0 for free
    rent_price_usd  = Column(Float, default=0.0)             # monthly rent price

    # Whop product IDs — seller creates these on Whop and pastes them here
    whop_product_id       = Column(String(120), nullable=True)
    whop_checkout_url     = Column(String(500), nullable=True)

    tags            = Column(JSON, default=list)             # ["scalping","rsi","engulfing"]
    preview_code    = Column(Text, nullable=True)            # first 50 lines shown publicly
    version         = Column(String(20), default="1.0")

    status          = Column(SAEnum(ListingStatus), default=ListingStatus.DRAFT)
    downloads       = Column(Integer, default=0)
    purchases       = Column(Integer, default=0)
    rating_total    = Column(Float, default=0.0)
    rating_count    = Column(Integer, default=0)

    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at      = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    purchases_rel   = relationship("MarketplacePurchase", back_populates="listing",
                                   cascade="all, delete-orphan")

    @property
    def avg_rating(self) -> float:
        if self.rating_count == 0:
            return 0.0
        return round(self.rating_total / self.rating_count, 1)


class MarketplacePurchase(Base):
    """Records every purchase or active rental."""
    __tablename__ = "marketplace_purchases"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_id      = Column(UUID(as_uuid=True), ForeignKey("marketplace_listings.id"), nullable=False, index=True)
    buyer_user_id   = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    listing_type    = Column(SAEnum(ListingType), nullable=False)
    amount_paid_usd = Column(Float, default=0.0)
    whop_membership_id = Column(String(120), nullable=True)   # for rent subscriptions

    active          = Column(Boolean, default=True)
    expires_at      = Column(DateTime(timezone=True), nullable=True)   # for rentals
    purchased_at    = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Review
    rating          = Column(Integer, nullable=True)    # 1–5
    review_text     = Column(Text, nullable=True)

    listing         = relationship("MarketplaceListing", back_populates="purchases_rel")
