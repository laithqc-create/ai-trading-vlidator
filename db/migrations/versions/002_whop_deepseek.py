"""Migrate: Stripe → Whop + add DeepSeek generation tracking

Revision ID: 002_whop_deepseek
Revises: 001_initial
Create Date: 2026-04-26
"""
from alembic import op
import sqlalchemy as sa

revision = "002_whop_deepseek"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove Stripe columns
    op.drop_column("users", "stripe_customer_id")
    op.drop_column("users", "stripe_subscription_id")

    # Add Whop columns
    op.add_column("users", sa.Column("whop_user_id", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("whop_membership_id", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_users_whop_user_id", "users", ["whop_user_id"])
    op.create_unique_constraint("uq_users_whop_membership_id", "users", ["whop_membership_id"])

    # Add DeepSeek generation tracking columns
    op.add_column("users", sa.Column("total_generations", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("users", sa.Column("total_generation_cost", sa.Float(), nullable=True, server_default="0.0"))


def downgrade() -> None:
    op.drop_column("users", "total_generation_cost")
    op.drop_column("users", "total_generations")
    op.drop_constraint("uq_users_whop_membership_id", "users", type_="unique")
    op.drop_constraint("uq_users_whop_user_id", "users", type_="unique")
    op.drop_column("users", "whop_membership_id")
    op.drop_column("users", "whop_user_id")
    op.add_column("users", sa.Column("stripe_customer_id", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("stripe_subscription_id", sa.String(64), nullable=True))
