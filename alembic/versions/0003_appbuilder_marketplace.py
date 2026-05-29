"""add app builder and marketplace tables

Revision ID: 0003_appbuilder_marketplace
Revises: 0002_trial_columns
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_appbuilder_marketplace"
down_revision = "0002_trial_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enums
    op.execute("CREATE TYPE applanguage AS ENUM ('pine_script','mql4','mql5','ctrader','python')")
    op.execute("CREATE TYPE appstatus AS ENUM ('draft','building','review','complete','failed')")
    op.execute("CREATE TYPE listingtype AS ENUM ('sell','rent')")
    op.execute("CREATE TYPE listingstatus AS ENUM ('draft','pending','live','suspended','archived')")

    # builder_apps
    op.create_table(
        "builder_apps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("language", sa.Enum("pine_script","mql4","mql5","ctrader","python", name="applanguage"), nullable=False),
        sa.Column("status", sa.Enum("draft","building","review","complete","failed", name="appstatus"), nullable=False, server_default="draft"),
        sa.Column("requirements", sa.Text(), nullable=True),
        sa.Column("final_code", sa.Text(), nullable=True),
        sa.Column("app_metadata", postgresql.JSON(), nullable=True),
        sa.Column("agent_session", postgresql.JSON(), nullable=True),
        sa.Column("disclaimer_accepted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("disclaimer_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_builder_apps_user_id", "builder_apps", ["user_id"])

    # build_iterations
    op.create_table(
        "build_iterations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("app_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("builder_apps.id"), nullable=False),
        sa.Column("iteration_n", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("plan", sa.Text(), nullable=True),
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column("review", sa.Text(), nullable=True),
        sa.Column("user_feedback", sa.Text(), nullable=True),
        sa.Column("approved", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_build_iterations_app_id", "build_iterations", ["app_id"])

    # marketplace_listings
    op.create_table(
        "marketplace_listings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("app_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("builder_apps.id"), nullable=False, unique=True),
        sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSON(), nullable=True),
        sa.Column("language", sa.Enum("pine_script","mql4","mql5","ctrader","python", name="applanguage"), nullable=False),
        sa.Column("listing_type", sa.Enum("sell","rent", name="listingtype"), nullable=False, server_default="sell"),
        sa.Column("price_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("whop_product_id", sa.String(200), nullable=True),
        sa.Column("status", sa.Enum("draft","pending","live","suspended","archived", name="listingstatus"), nullable=False, server_default="draft"),
        sa.Column("total_sales", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_revenue", sa.Float(), nullable=False, server_default="0"),
        sa.Column("rating_sum", sa.Float(), nullable=False, server_default="0"),
        sa.Column("rating_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_marketplace_listings_seller_id", "marketplace_listings", ["seller_id"])
    op.create_index("ix_marketplace_listings_status",    "marketplace_listings", ["status"])

    # marketplace_purchases
    op.create_table(
        "marketplace_purchases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("marketplace_listings.id"), nullable=False),
        sa.Column("buyer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("listing_type", sa.Enum("sell","rent", name="listingtype"), nullable=False),
        sa.Column("amount_usd", sa.Float(), nullable=False),
        sa.Column("access_expires", sa.DateTime(timezone=True), nullable=True),
        sa.Column("whop_membership_id", sa.String(200), nullable=True),
        sa.Column("purchased_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_marketplace_purchases_listing_id", "marketplace_purchases", ["listing_id"])
    op.create_index("ix_marketplace_purchases_buyer_id",   "marketplace_purchases", ["buyer_id"])

    # marketplace_reviews
    op.create_table(
        "marketplace_reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("marketplace_listings.id"), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("marketplace_reviews")
    op.drop_table("marketplace_purchases")
    op.drop_table("marketplace_listings")
    op.drop_table("build_iterations")
    op.drop_table("builder_apps")
    op.execute("DROP TYPE IF EXISTS listingstatus")
    op.execute("DROP TYPE IF EXISTS listingtype")
    op.execute("DROP TYPE IF EXISTS appstatus")
    op.execute("DROP TYPE IF EXISTS applanguage")
