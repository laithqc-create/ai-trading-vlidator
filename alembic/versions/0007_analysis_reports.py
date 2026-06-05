"""add analysis_reports table
Revision ID: 0007_analysis_reports
Revises: 0006_indicator_prefs
"""
from alembic import op
import sqlalchemy as sa

revision      = "0007_analysis_reports"
down_revision = "0006_indicator_prefs"


def upgrade():
    op.create_table(
        "analysis_reports",
        sa.Column("id",         sa.Integer, primary_key=True),
        sa.Column("user_id",    sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source",     sa.String(20), nullable=False),
        sa.Column("symbol",     sa.String(20), nullable=True),
        sa.Column("timeframe",  sa.String(10), nullable=True),
        sa.Column("report",     sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_analysis_reports_user_source",
                    "analysis_reports", ["user_id", "source"])


def downgrade():
    op.drop_index("ix_analysis_reports_user_source", table_name="analysis_reports")
    op.drop_table("analysis_reports")
