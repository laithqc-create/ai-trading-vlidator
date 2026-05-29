"""add webhook token columns to users

Revision ID: 0005_webhook_token_columns
Revises: 0004_pattern_rules
Create Date: 2026-05-23

Adds webhook_token_indicator, webhook_token_ea, webhook_token_screenshot
to the users table if they don't already exist.

Uses IF NOT EXISTS so it's safe to run even if some columns were added
manually or by an earlier migration.
"""

from alembic import op
import sqlalchemy as sa


revision      = "0005_webhook_token_columns"
down_revision = "0004_pattern_rules"
branch_labels = None
depends_on    = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c"
    ), {"t": table, "c": column})
    return result.fetchone() is not None


def upgrade() -> None:
    cols = [
        ("webhook_token_indicator",  sa.String(64)),
        ("webhook_token_ea",         sa.String(64)),
        ("webhook_token_screenshot", sa.String(64)),
    ]
    for col_name, col_type in cols:
        if not _column_exists("users", col_name):
            op.add_column("users", sa.Column(col_name, col_type, nullable=True))

    # Unique indexes — safe to create separately so we can check existence
    for col_name, _ in cols:
        idx_name = f"ix_users_{col_name}"
        conn = op.get_bind()
        exists = conn.execute(sa.text(
            "SELECT 1 FROM pg_indexes WHERE indexname = :n"
        ), {"n": idx_name}).fetchone()
        if not exists:
            op.create_index(idx_name, "users", [col_name], unique=True,
                            postgresql_where=sa.text(f"{col_name} IS NOT NULL"))


def downgrade() -> None:
    for col_name in (
        "webhook_token_screenshot",
        "webhook_token_ea",
        "webhook_token_indicator",
    ):
        if _column_exists("users", col_name):
            op.drop_column("users", col_name)
