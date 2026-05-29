"""add trial columns to users

Revision ID: 0002_trial_columns
Revises: 0001  (update this to your actual last revision id)
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_trial_columns"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add new TRIAL value to the plan enum
    # PostgreSQL requires ALTER TYPE to add enum values
    op.execute("ALTER TYPE plantier ADD VALUE IF NOT EXISTS 'trial'")

    # 2. Add trial timestamp columns to users table
    op.add_column(
        "users",
        sa.Column("trial_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("trial_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "trial_expires_at")
    op.drop_column("users", "trial_started_at")
    # Note: PostgreSQL does not support removing enum values.
    # To fully downgrade, recreate the enum without 'trial'.
