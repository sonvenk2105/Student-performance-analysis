"""Persist prediction model validation metadata.

Revision ID: 0004_model_run
Revises: 0003_subject_catalog
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_model_run"
down_revision = "0003_subject_catalog"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("prediction_model_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("artifact_filename", sa.String(80), nullable=True),
        sa.Column("training_students", sa.Integer(), nullable=False),
        sa.Column("training_sequences", sa.Integer(), nullable=False),
        sa.Column("validation_mae", sa.Float(), nullable=True),
        sa.Column("baseline_mae", sa.Float(), nullable=True),
        sa.Column("validation_r2", sa.Float(), nullable=True),
        sa.Column("validated", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_prediction_model_run_created_at", "prediction_model_run", ["created_at"])

def downgrade():
    op.drop_index("ix_prediction_model_run_created_at", table_name="prediction_model_run")
    op.drop_table("prediction_model_run")
