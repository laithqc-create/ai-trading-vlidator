"""add user_indicator_prefs table
Revision ID: 0006_indicator_prefs
Revises: 0005_webhook_token_columns
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0006_indicator_prefs"
down_revision = "0005_webhook_token_columns"

def upgrade():
    op.create_table(
        "user_indicator_prefs",
        sa.Column("id",                 postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id",            sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("enabled_indicators", postgresql.ARRAY(sa.TEXT), nullable=True),
        sa.Column("custom_settings",    postgresql.JSON, nullable=True, server_default="{}"),
        sa.Column("created_at",         sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at",         sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_user_indicator_prefs_user_id", "user_indicator_prefs", ["user_id"])

def downgrade():
    op.drop_table("user_indicator_prefs")
