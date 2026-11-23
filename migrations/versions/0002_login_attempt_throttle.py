"""Persist hashed login-failure counters for multi-worker throttling.

Revision ID: 0002_login_throttle
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_login_throttle"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("login_attempt",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("identity_hash", sa.String(64), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_login_attempt_identity_time", "login_attempt", ["identity_hash", "attempted_at"])

def downgrade():
    op.drop_index("ix_login_attempt_identity_time", table_name="login_attempt")
    op.drop_table("login_attempt")
