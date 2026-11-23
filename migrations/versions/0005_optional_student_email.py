"""Allow student self-registration without email.

Revision ID: 0005_optional_student_email
Revises: 0004_model_run
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_optional_student_email"
down_revision = "0004_model_run"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user") as batch_op:
        batch_op.alter_column("email", existing_type=sa.String(length=254), nullable=True)


def downgrade():
    op.execute(sa.text('UPDATE "user" SET email = \'student-\' || id || \'@no-email.invalid\' WHERE email IS NULL'))
    with op.batch_alter_table("user") as batch_op:
        batch_op.alter_column("email", existing_type=sa.String(length=254), nullable=False)
