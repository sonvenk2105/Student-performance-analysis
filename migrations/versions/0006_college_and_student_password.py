"""Store college names and first-sign-in student password state.

Revision ID: 0006_college_and_student_password
Revises: 0005_optional_student_email
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_college_and_student_password"
down_revision = "0005_optional_student_email"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(sa.Column("college_name", sa.String(length=150), nullable=False, server_default="Not provided"))
        batch_op.add_column(sa.Column("student_password_initialized", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_column("student_password_initialized")
        batch_op.drop_column("college_name")
