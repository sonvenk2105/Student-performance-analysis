"""Initial student performance schema.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("user",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("student_id", sa.String(40), nullable=True),
        sa.Column("analytics_key", sa.String(36), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("course", sa.String(100), nullable=False, server_default=""),
        sa.Column("semester", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("role", sa.String(16), nullable=False, server_default="student"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("student_id"),
        sa.UniqueConstraint("analytics_key"),
        sa.UniqueConstraint("email"))
    op.create_index("ix_user_role", "user", ["role"], unique=False)
    op.create_table("grading_rule",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("grade_ranges", sa.JSON(), nullable=False),
        sa.Column("subject_pass_percent", sa.Float(), nullable=False, server_default="40"),
        sa.Column("overall_pass_percent", sa.Float(), nullable=False, server_default="40"),
        sa.Column("weak_threshold", sa.Float(), nullable=False, server_default="50"),
        sa.Column("changed_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("version", name="uq_grading_rule_version"))
    op.create_table("assessment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course", sa.String(100), nullable=False),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.Column("academic_year", sa.String(20), nullable=True),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("idempotency_key", sa.String(36), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("percentage", sa.Float(), nullable=False),
        sa.Column("grade", sa.String(12), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("total_obtained", sa.Float(), nullable=False),
        sa.Column("total_maximum", sa.Float(), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("rule_snapshot", sa.JSON(), nullable=False),
        sa.Column("analysis_version", sa.String(16), nullable=False, server_default="1.0"),
        sa.UniqueConstraint("student_id", "idempotency_key", name="uq_assessment_request"))
    op.create_index("ix_assessment_student_id", "assessment", ["student_id"])
    op.create_index("ix_assessment_semester", "assessment", ["semester"])
    op.create_index("ix_assessment_assessed_at", "assessment", ["assessed_at"])
    op.create_table("assessment_mark",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assessment_id", sa.Integer(), sa.ForeignKey("assessment.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject", sa.String(120), nullable=False),
        sa.Column("obtained", sa.Float(), nullable=False),
        sa.Column("maximum", sa.Float(), nullable=False),
        sa.Column("passing", sa.Float(), nullable=False),
        sa.Column("percentage", sa.Float(), nullable=False),
        sa.Column("grade", sa.String(12), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("relative", sa.String(20), nullable=False),
        sa.Column("recommendation", sa.String(240), nullable=False),
        sa.UniqueConstraint("assessment_id", "subject", name="uq_assessment_subject"))
    op.create_index("ix_assessment_mark_assessment_id", "assessment_mark", ["assessment_id"])
    op.create_table("audit_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("detail", sa.String(300), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))

def downgrade():
    op.drop_table("audit_event")
    op.drop_index("ix_assessment_mark_assessment_id", table_name="assessment_mark")
    op.drop_table("assessment_mark")
    op.drop_index("ix_assessment_assessed_at", table_name="assessment")
    op.drop_index("ix_assessment_semester", table_name="assessment")
    op.drop_index("ix_assessment_student_id", table_name="assessment")
    op.drop_table("assessment")
    op.drop_table("grading_rule")
    op.drop_index("ix_user_role", table_name="user")
    op.drop_table("user")
