"""Add course/semester subject catalog.

Revision ID: 0003_subject_catalog
Revises: 0002_login_throttle
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_subject_catalog"
down_revision = "0002_login_throttle"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("academic_subject",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course", sa.String(100), nullable=False),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("maximum", sa.Float(), nullable=False),
        sa.Column("passing", sa.Float(), nullable=False),
        sa.UniqueConstraint("course", "semester", "name", name="uq_catalog_subject"))
    op.create_index("ix_academic_subject_course", "academic_subject", ["course"])

def downgrade():
    op.drop_index("ix_academic_subject_course", table_name="academic_subject")
    op.drop_table("academic_subject")
