"""Initial schema — all base tables.

Revision ID: 0001
Revises:
Create Date: 2026-01-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ──────────────────────────────────────────────────────────────────
    plantier = postgresql.ENUM(
        "free", "trial", "product1", "product2", "product3", "pro",
        name="plantier", create_type=True,
    )
    plantier.create(op.get_bind(), checkfirst=True)

    validationstatus = postgresql.ENUM(
        "pending", "processing", "completed", "failed",
        name="validationstatus", create_type=True,
    )
    validationstatus.create(op.get_bind(), checkfirst=True)

    signaltype = postgresql.ENUM(
        "BUY", "SELL", "HOLD",
        name="signaltype", create_type=True,
    )
    signaltype.create(op.get_bind(), checkfirst=True)

    # ── users ──────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id",           sa.Integer(),    primary_key=True, autoincrement=True),
        sa.Column("telegram_id",  sa.BigInteger(), nullable=False, unique=True, index=True),
        sa.Column("username",     sa.String(255),  nullable=True),
        sa.Column("plan",         sa.Enum("free","trial","product1","product2","product3","pro", name="plantier"), nullable=False, server_default="free"),
        sa.Column("whop_user_id",       sa.String(128), nullable=True),
        sa.Column("whop_membership_id", sa.String(128), nullable=True),
        sa.Column("ragflow_dataset_id", sa.String(255), nullable=True),
        sa.Column("indicator_webhook_token",  sa.String(64), nullable=True, unique=True),
        sa.Column("ea_webhook_token",         sa.String(64), nullable=True, unique=True),
        sa.Column("screenshot_webhook_token", sa.String(64), nullable=True, unique=True),
        sa.Column("trial_started_at",  sa.DateTime(), nullable=True),
        sa.Column("trial_expires_at",  sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # ── validations ────────────────────────────────────────────────────────────
    op.create_table(
        "validations",
        sa.Column("id",      sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("product", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("ticker",  sa.String(32),  nullable=True),
        sa.Column("signal",  sa.Enum("BUY","SELL","HOLD", name="signaltype"), nullable=True),
        sa.Column("price",   sa.Float(),     nullable=True),
        sa.Column("status",  sa.Enum("pending","processing","completed","failed", name="validationstatus"), nullable=False, server_default="pending"),
        sa.Column("verdict",          sa.String(32), nullable=True),
        sa.Column("confidence_score", sa.Float(),    nullable=True),
        sa.Column("final_message",    sa.Text(),     nullable=True),
        sa.Column("trader_analysis",  sa.JSON(),     nullable=True),
        sa.Column("raw_payload",      sa.JSON(),     nullable=True),
        sa.Column("source_payload",   sa.JSON(),     nullable=True),
        sa.Column("source_platform",  sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # ── ea_logs ────────────────────────────────────────────────────────────────
    op.create_table(
        "ea_logs",
        sa.Column("id",          sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id",     sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("analysis_id", sa.Integer(), sa.ForeignKey("validations.id"), nullable=True),
        sa.Column("ea_name",     sa.String(255), nullable=True),
        sa.Column("ticker",      sa.String(32),  nullable=True),
        sa.Column("action",      sa.String(16),  nullable=True),
        sa.Column("result",      sa.String(16),  nullable=True),
        sa.Column("pnl",         sa.Float(),     nullable=True),
        sa.Column("trade_time",  sa.DateTime(),  nullable=True),
        sa.Column("raw_payload", sa.JSON(),      nullable=True),
        sa.Column("created_at",  sa.DateTime(),  server_default=sa.func.now(), nullable=False),
    )

    # ── user_rules ─────────────────────────────────────────────────────────────
    op.create_table(
        "user_rules",
        sa.Column("id",      sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("rule_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_rules")
    op.drop_table("ea_logs")
    op.drop_table("validations")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS signaltype")
    op.execute("DROP TYPE IF EXISTS validationstatus")
    op.execute("DROP TYPE IF EXISTS plantier")
