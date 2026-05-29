"""add user_pattern_rules table

Revision ID: 0004_pattern_rules
Revises: 0003_appbuilder_marketplace
Create Date: 2026-05-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0004_pattern_rules"
down_revision = "0003_appbuilder_marketplace"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "user_pattern_rules",
        sa.Column("id",               postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id",          sa.Integer(),  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pattern_name",     sa.String(80), nullable=False),
        sa.Column("enabled",          sa.Boolean(),  nullable=False, server_default="true"),
        sa.Column("min_body_ratio",   sa.Float(),    nullable=True),
        sa.Column("max_wick_ratio",   sa.Float(),    nullable=True),
        sa.Column("min_engulf_ratio", sa.Float(),    nullable=True),
        sa.Column("created_at",       sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at",       sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_user_pattern_rules_user_id",      "user_pattern_rules", ["user_id"])
    op.create_unique_constraint(
        "uq_user_pattern_rules_user_pattern",
        "user_pattern_rules", ["user_id", "pattern_name"]
    )


def downgrade() -> None:
    op.drop_table("user_pattern_rules")
