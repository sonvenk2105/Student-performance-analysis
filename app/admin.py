from functools import wraps
import csv
import math
import re
import secrets
from io import StringIO
from flask import Blueprint, abort, flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import case, desc, func
from app import db
from app.analysis import DEFAULT_RULES, validate_grade_ranges
from app.models import AcademicSubject, Assessment, AuditEvent, GradingRule, User

bp = Blueprint("admin", __name__, url_prefix="/admin")

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.admin_login", next=request.url))
        if current_user.role != "admin": abort(403)
        return view(*args, **kwargs)
    return wrapped

@bp.get("/")
@admin_required
def dashboard():
    students = db.session.scalar(db.select(func.count(User.id)).where(User.role == "student")) or 0
    assessments = db.session.scalar(db.select(func.count(Assessment.id))) or 0
    avg = db.session.scalar(db.select(func.avg(Assessment.percentage)))
    courses = db.session.execute(db.select(Assessment.course, func.count(Assessment.id), func.avg(Assessment.percentage), func.sum(case((Assessment.passed.is_(True), 1), else_=0)).label("passed")).group_by(Assessment.course).order_by(Assessment.course)).all()
    return render_template("admin/dashboard.html", students=students, assessments=assessments, average=avg, courses=courses)

@bp.get("/reports/aggregate.csv")
@admin_required
def aggregate_export():
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["course", "semester", "assessment_count", "average_percentage", "pass_count", "fail_count", "pass_rate_percent"])
    groups = db.session.execute(db.select(Assessment.course, Assessment.semester, func.count(Assessment.id), func.avg(Assessment.percentage), func.sum(case((Assessment.passed.is_(True), 1), else_=0))).group_by(Assessment.course, Assessment.semester).order_by(Assessment.course, Assessment.semester)).all()
    for course, semester, count, average, passed in groups:
        passed = passed or 0
        safe_course = "'" + course if str(course).startswith(("=", "+", "-", "@", "\t", "\r")) else course
        writer.writerow([safe_course, semester, count, f"{average:.2f}", passed, count - passed, f"{passed * 100 / count:.2f}" if count else ""])
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=academic-aggregate.csv"
    return response

@bp.get("/students")
@admin_required
def students():
    term = request.args.get("q", "").strip()
    query = db.select(User).where(User.role == "student")
    if term: query = query.where((User.name.ilike(f"%{term}%")) | (User.college_name.ilike(f"%{term}%")) | (User.email.ilike(f"%{term}%")) | (User.student_id.ilike(f"%{term}%")))
    rows = db.paginate(query.order_by(User.name), page=request.args.get("page", 1, type=int), per_page=30, error_out=False)
    return render_template("admin/students.html", rows=rows, term=term)

@bp.route("/students/new", methods=["GET", "POST"])
@admin_required
def create_student():
    if request.method == "POST":
        name=request.form.get("name", "").strip(); sid=request.form.get("student_id", "").strip().upper(); college_name=request.form.get("college_name", "").strip(); email=request.form.get("email", "").strip().lower(); course=request.form.get("course", "").strip(); semester=request.form.get("semester", "")
        if not 2 <= len(name) <= 120 or not sid or len(sid) > 40 or not college_name or len(college_name) > 150 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or not course or len(course) > 100 or not semester.isdigit() or not 1 <= int(semester) <= 20:
            flash("Check the student details.", "error")
        elif db.session.scalar(db.select(User.id).where((func.lower(User.email) == email) | (func.lower(User.student_id) == sid.lower()))):
            flash("That email or student ID is already registered.", "error")
        else:
            user=User(name=name,student_id=sid,email=email,college_name=college_name,course=course,semester=int(semester),role="student",active=True); user.set_password(secrets.token_urlsafe(32))
            db.session.add(user); db.session.flush()
            db.session.add(AuditEvent(actor_id=current_user.id,action="student_account_created",detail=f"user_id={user.id}")); db.session.commit()
            flash("Student account created.", "success"); return redirect(url_for("admin.student_detail",user_id=user.id))
    return render_template("admin/student_form.html", student=None, reset=False)

@bp.get("/students/<int:user_id>")
@admin_required
def student_detail(user_id):
    user = db.get_or_404(User, user_id)
    if user.role != "student": abort(404)
    records = db.session.scalars(db.select(Assessment).where(Assessment.student_id == user.id).order_by(desc(Assessment.assessed_at)).limit(100)).all()
    return render_template("admin/student_detail.html", student=user, records=records)

@bp.route("/students/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_student(user_id):
    user=db.get_or_404(User,user_id)
    if user.role != "student": abort(404)
    if request.method == "POST":
        name=request.form.get("name", "").strip(); sid=request.form.get("student_id", "").strip().upper(); college_name=request.form.get("college_name", "").strip(); email=request.form.get("email", "").strip().lower() or None; course=request.form.get("course", "").strip(); semester=request.form.get("semester", "")
        if not 2 <= len(name) <= 120 or not sid or len(sid) > 40 or not college_name or len(college_name) > 150 or (email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)) or not course or len(course) > 100 or not semester.isdigit() or not 1 <= int(semester) <= 20:
            flash("Enter valid account details.", "error")
        elif (
            db.session.scalar(db.select(User.id).where(User.id != user.id, func.upper(User.student_id) == sid))
            or (email and db.session.scalar(db.select(User.id).where(User.id != user.id, func.lower(User.email) == email)))
        ):
            flash("That email or student ID belongs to another account.", "error")
        else:
            user.name,user.student_id,user.email,user.college_name,user.course,user.semester=name,sid,email,college_name,course,int(semester)
            db.session.add(AuditEvent(actor_id=current_user.id,action="student_account_edited",detail=f"user_id={user.id}")); db.session.commit()
            flash("Student account updated. Historical assessments retain their saved course and semester.", "success")
            return redirect(url_for("admin.student_detail",user_id=user.id))
    return render_template("admin/student_form.html", student=user, reset=False)

@bp.post("/students/<int:user_id>/reset-password")
@admin_required
def reset_student_password(user_id):
    user=db.get_or_404(User,user_id)
    if user.role != "student": abort(404)
    password=request.form.get("new_password", "")
    if len(password) < 14:
        flash("The replacement password must be at least 14 characters.", "error")
    else:
        user.set_password(password)
        user.student_password_initialized = True
        db.session.add(AuditEvent(actor_id=current_user.id,action="student_password_reset",detail=f"user_id={user.id}")); db.session.commit()
        flash("Password reset. Share the replacement through an approved private channel.", "success")
    return redirect(url_for("admin.student_detail",user_id=user.id))

@bp.route("/subjects", methods=["GET", "POST"])
@admin_required
def subjects():
    if request.method == "POST":
        course = request.form.get("course", "").strip()
        name = request.form.get("name", "").strip()
        try:
            semester = int(request.form.get("semester", ""))
            maximum, passing = float(request.form.get("maximum", "")), float(request.form.get("passing", ""))
            if not course or len(course) > 100 or not name or len(name) > 120 or not 1 <= semester <= 20 or not math.isfinite(maximum) or not math.isfinite(passing) or maximum <= 0 or maximum > 100 or not 0 <= passing <= min(maximum, 40): raise ValueError
            subject = AcademicSubject(course=course, semester=semester, name=name, maximum=maximum, passing=passing)
            db.session.add(subject); db.session.flush()
            db.session.add(AuditEvent(actor_id=current_user.id, action="academic_subject_added", detail=f"catalog_subject_id={subject.id};course={course};semester={semester}"))
            db.session.commit(); flash("Subject added to the academic catalog.", "success")
            return redirect(url_for("admin.subjects"))
        except (ValueError, TypeError):
            db.session.rollback(); flash("Enter a unique subject, semester 1–20, maximum marks up to 100, and passing marks up to 40.", "error")
        except Exception:
            db.session.rollback(); flash("That course and semester already have a subject with this name.", "error")
    rows = db.session.scalars(db.select(AcademicSubject).order_by(AcademicSubject.course, AcademicSubject.semester, AcademicSubject.name)).all()
    return render_template("admin/subjects.html", rows=rows)

@bp.post("/subjects/<int:subject_id>/delete")
@admin_required
def delete_subject(subject_id):
    subject = db.get_or_404(AcademicSubject, subject_id)
    db.session.add(AuditEvent(actor_id=current_user.id, action="academic_subject_removed", detail=f"catalog_subject_id={subject.id};course={subject.course};semester={subject.semester}"))
    db.session.delete(subject); db.session.commit()
    flash("Subject removed from the catalog. Saved assessment history is unchanged.", "success")
    return redirect(url_for("admin.subjects"))

@bp.post("/students/<int:user_id>/active")
@admin_required
def set_active(user_id):
    user = db.get_or_404(User, user_id)
    if user.role == "admin": abort(400)
    user.active = request.form.get("active") == "true"
    db.session.add(AuditEvent(actor_id=current_user.id, action="student_account_status", detail=f"user_id={user.id};active={user.active}"))
    db.session.commit(); flash("Account status updated.", "success")
    return redirect(url_for("admin.students"))

@bp.route("/grading", methods=["GET", "POST"])
@admin_required
def grading():
    if request.method == "POST":
        try:
            labels = request.form.getlist("grade_label[]"); lows = request.form.getlist("grade_min[]"); highs = request.form.getlist("grade_max[]")
            if not labels or len({len(labels), len(lows), len(highs)}) != 1: raise ValueError("Each grade needs a label and two boundaries.")
            ranges = validate_grade_ranges([{"label":l.strip(),"min":float(a),"max":float(b)} for l,a,b in zip(labels,lows,highs)])
            sp, op, weak = (float(request.form[k]) for k in ("subject_pass_percent","overall_pass_percent","weak_threshold"))
            if any(v < 0 or v > 100 for v in (sp,op,weak)): raise ValueError("Rule percentages must be between 0 and 100.")
            version = (db.session.scalar(db.select(func.max(GradingRule.version))) or 0) + 1
            db.session.add(GradingRule(version=version, grade_ranges=ranges, subject_pass_percent=sp, overall_pass_percent=op, weak_threshold=weak, changed_by=current_user.id))
            db.session.add(AuditEvent(actor_id=current_user.id, action="grading_rules_changed", detail=f"version={version}"))
            db.session.commit(); flash("A new grading rule version is active. Previous assessments retain their rule snapshot.", "success")
            return redirect(url_for("admin.grading"))
        except (ValueError, TypeError):
            db.session.rollback(); flash("Check the grade coverage and percentage values.", "error")
    rule = db.session.scalar(db.select(GradingRule).order_by(desc(GradingRule.version)))
    return render_template("admin/grading.html", rule=rule, defaults=DEFAULT_RULES)
