"""Initial schema — create all tables

Revision ID: 001_initial
Revises: 
Create Date: 2024-01-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("first_name", sa.String(64), nullable=True),
        sa.Column("last_name", sa.String(64), nullable=True),
        sa.Column("plan", sa.Enum("free","product1","product2","product3","pro", name="plantier"), nullable=False, server_default="free"),
        sa.Column("stripe_customer_id", sa.String(64), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(64), nullable=True),
        sa.Column("plan_expires_at", sa.DateTime(), nullable=True),
        sa.Column("ragflow_dataset_id", sa.String(128), nullable=True),
        sa.Column("indicator_webhook_token", sa.String(64), nullable=True),
        sa.Column("ea_webhook_token", sa.String(64), nullable=True),
        sa.Column("daily_validation_count", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("daily_validation_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
        sa.UniqueConstraint("stripe_customer_id"),
        sa.UniqueConstraint("stripe_subscription_id"),
        sa.UniqueConstraint("indicator_webhook_token"),
        sa.UniqueConstraint("ea_webhook_token"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])

    # validations
    op.create_table(
        "validations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("product", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("signal", sa.Enum("BUY","SELL","HOLD", name="signaltype"), nullable=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("source_payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.Enum("pending","processing","completed","failed", name="validationstatus"), nullable=False, server_default="pending"),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("verdict", sa.String(20), nullable=True),
        sa.Column("trader_analysis", sa.JSON(), nullable=True),
        sa.Column("mentor_context", sa.Text(), nullable=True),
        sa.Column("final_message", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("user_outcome", sa.String(20), nullable=True),
        sa.Column("user_outcome_pnl", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # user_rules
    op.create_table(
        "user_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("rule_text", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("ragflow_doc_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    # ea_logs
    op.create_table(
        "ea_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ea_name", sa.String(128), nullable=True),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("result", sa.String(10), nullable=True),
        sa.Column("pnl", sa.Float(), nullable=True),
        sa.Column("trade_time", sa.DateTime(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("analysis_id", sa.Integer(), sa.ForeignKey("validations.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("ea_logs")
    op.drop_table("user_rules")
    op.drop_table("validations")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS plantier")
    op.execute("DROP TYPE IF EXISTS signaltype")
    op.execute("DROP TYPE IF EXISTS validationstatus")
