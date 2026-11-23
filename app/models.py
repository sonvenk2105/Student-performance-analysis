from datetime import datetime, timezone
import uuid
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash
from app import db, login_manager

def utcnow():
    return datetime.now(timezone.utc)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    student_id = db.Column(db.String(40), unique=True, nullable=True)
    analytics_key = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    email = db.Column(db.String(254), unique=True, nullable=True)
    college_name = db.Column(db.String(150), nullable=False, default="Not provided")
    course = db.Column(db.String(100), nullable=False, default="")
    semester = db.Column(db.Integer, nullable=False, default=1)
    role = db.Column(db.String(16), nullable=False, default="student", index=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    password_hash = db.Column(db.String(256), nullable=False)
    student_password_initialized = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    assessments = db.relationship("Assessment", back_populates="student", cascade="all, delete-orphan")
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class GradingRule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.Integer, nullable=False)
    grade_ranges = db.Column(db.JSON, nullable=False)
    subject_pass_percent = db.Column(db.Float, nullable=False, default=40)
    overall_pass_percent = db.Column(db.Float, nullable=False, default=40)
    weak_threshold = db.Column(db.Float, nullable=False, default=50)
    changed_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (db.UniqueConstraint("version", name="uq_grading_rule_version"),)

class AcademicSubject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course = db.Column(db.String(100), nullable=False, index=True)
    semester = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    maximum = db.Column(db.Float, nullable=False)
    passing = db.Column(db.Float, nullable=False)
    __table_args__ = (db.UniqueConstraint("course", "semester", "name", name="uq_catalog_subject"),)

class Assessment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    course = db.Column(db.String(100), nullable=False)
    semester = db.Column(db.Integer, nullable=False, index=True)
    academic_year = db.Column(db.String(20))
    label = db.Column(db.String(120), nullable=False)
    idempotency_key = db.Column(db.String(36), nullable=False)
    assessed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    percentage = db.Column(db.Float, nullable=False)
    grade = db.Column(db.String(12), nullable=False)
    passed = db.Column(db.Boolean, nullable=False)
    total_obtained = db.Column(db.Float, nullable=False)
    total_maximum = db.Column(db.Float, nullable=False)
    rule_version = db.Column(db.Integer, nullable=False)
    rule_snapshot = db.Column(db.JSON, nullable=False)
    analysis_version = db.Column(db.String(16), nullable=False, default="1.0")
    student = db.relationship("User", back_populates="assessments")
    marks = db.relationship("AssessmentMark", back_populates="assessment", cascade="all, delete-orphan")
    __table_args__ = (db.UniqueConstraint("student_id", "idempotency_key", name="uq_assessment_request"),)

class AssessmentMark(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey("assessment.id", ondelete="CASCADE"), nullable=False, index=True)
    subject = db.Column(db.String(120), nullable=False)
    obtained = db.Column(db.Float, nullable=False)
    maximum = db.Column(db.Float, nullable=False)
    passing = db.Column(db.Float, nullable=False)
    percentage = db.Column(db.Float, nullable=False)
    grade = db.Column(db.String(12), nullable=False)
    passed = db.Column(db.Boolean, nullable=False)
    relative = db.Column(db.String(20), nullable=False)
    recommendation = db.Column(db.String(240), nullable=False)
    assessment = db.relationship("Assessment", back_populates="marks")
    __table_args__ = (db.UniqueConstraint("assessment_id", "subject", name="uq_assessment_subject"),)

class AuditEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    action = db.Column(db.String(80), nullable=False)
    detail = db.Column(db.String(300), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

class LoginAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    identity_hash = db.Column(db.String(64), nullable=False)
    attempted_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (db.Index("ix_login_attempt_identity_time", "identity_hash", "attempted_at"),)

class PredictionModelRun(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.String(40), nullable=False)
    artifact_filename = db.Column(db.String(80), nullable=True)
    training_students = db.Column(db.Integer, nullable=False)
    training_sequences = db.Column(db.Integer, nullable=False)
    validation_mae = db.Column(db.Float, nullable=True)
    baseline_mae = db.Column(db.Float, nullable=True)
    validation_r2 = db.Column(db.Float, nullable=True)
    validated = db.Column(db.Boolean, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
