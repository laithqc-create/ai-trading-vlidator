"""add full auth fields to users table
Revision ID: 0008_auth_fields
Revises: 0007_analysis_reports
"""
from alembic import op
import sqlalchemy as sa

revision      = "0008_auth_fields"
down_revision = "0007_analysis_reports"


def upgrade():
    # These may already exist in some deployments — use try/except per column
    cols = [
        ("full_name",                sa.String(128)),
        ("avatar_url",               sa.String(512)),
        ("google_id",                sa.String(128)),
        ("google_email",             sa.String(255)),
        ("email_verified",           sa.Boolean()),
        ("billing_name",             sa.String(128)),
        ("billing_company",          sa.String(128)),
        ("billing_address",          sa.String(255)),
        ("billing_city",             sa.String(64)),
        ("billing_state",            sa.String(64)),
        ("billing_zip",              sa.String(20)),
        ("billing_country",          sa.String(2)),
        ("tax_id",                   sa.String(64)),
        ("atv_api_token",            sa.String(64)),
    ]
    for col_name, col_type in cols:
        try:
            op.add_column("users", sa.Column(col_name, col_type, nullable=True))
        except Exception:
            pass  # column already exists

    # Unique index on atv_api_token
    try:
        op.create_index("ix_users_atv_api_token", "users", ["atv_api_token"], unique=True)
    except Exception:
        pass

    # Unique index on google_id
    try:
        op.create_index("ix_users_google_id", "users", ["google_id"], unique=True)
    except Exception:
        pass


def downgrade():
    for col in ["atv_api_token", "tax_id", "billing_country", "billing_zip",
                "billing_state", "billing_city", "billing_address",
                "billing_company", "billing_name", "email_verified",
                "google_email", "google_id", "avatar_url", "full_name"]:
        try:
            op.drop_column("users", col)
        except Exception:
            pass
