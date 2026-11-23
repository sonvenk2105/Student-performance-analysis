import os
import uuid
import json
import time
from collections import defaultdict
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, session, url_for
from flask_login import current_user, login_required, logout_user
from sqlalchemy import desc, or_
from app import db
from app.analysis import DEFAULT_RULES, analyze_marks
from app.models import AcademicSubject, Assessment, AssessmentMark, AuditEvent, GradingRule, LoginAttempt, PredictionModelRun, User
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
import re

bp = Blueprint("student", __name__, url_prefix="/student")
ALLOWED_UPLOADS = {"pdf", "png", "jpg", "jpeg", "xls", "xlsx"}

def comparison_signature(assessment):
    subjects = tuple(sorted((mark.subject.casefold(), mark.maximum) for mark in assessment.marks))
    return assessment.course, subjects, assessment.rule_version

def upload_signature_matches(file, extension):
    signatures = {"pdf": lambda b: b.startswith(b"%PDF-"), "png": lambda b: b.startswith(b"\x89PNG\r\n\x1a\n"),
                  "jpg": lambda b: b.startswith(b"\xff\xd8\xff"), "jpeg": lambda b: b.startswith(b"\xff\xd8\xff"),
                  "xls": lambda b: b.startswith(bytes.fromhex("D0CF11E0A1B11AE1")),
                  "xlsx": lambda b: b.startswith(b"PK\x03\x04")}
    head = file.stream.read(16)
    file.stream.seek(0)
    return signatures[extension](head)

def save_marksheet_draft(rows):
    token = uuid.uuid4().hex
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], f"draft-{token}.json")
    with open(path, "x", encoding="utf-8") as draft_file:
        json.dump({"student_id":current_user.id,"created_at":time.time(),"rows":rows}, draft_file, separators=(",", ":"))
    try: os.chmod(path, 0o600)
    except OSError: pass
    return token

def consume_marksheet_draft(token):
    if not isinstance(token, str) or not re.fullmatch(r"[a-f0-9]{32}", token):
        raise ValueError("This imported marksheet has expired. Upload it again.")
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], f"draft-{token}.json")
    try:
        with open(path, encoding="utf-8") as draft_file:
            draft = json.load(draft_file)
    except (OSError, ValueError):
        raise ValueError("This imported marksheet has expired. Upload it again.")
    finally:
        try: os.remove(path)
        except OSError: pass
    if not isinstance(draft, dict) or draft.get("student_id") != current_user.id or not isinstance(draft.get("created_at"), (int, float)) or time.time() - draft["created_at"] > 900 or not isinstance(draft.get("rows"), list):
        raise ValueError("This imported marksheet has expired. Upload it again.")
    return draft.get("rows", [])

def active_rules():
    rule = db.session.scalar(db.select(GradingRule).order_by(desc(GradingRule.version)))
    return rule, ({"grade_ranges":rule.grade_ranges,"subject_pass_percent":rule.subject_pass_percent,"overall_pass_percent":rule.overall_pass_percent,"weak_threshold":rule.weak_threshold} if rule else DEFAULT_RULES)

@bp.get("/dashboard")
@login_required
def dashboard():
    recent = db.session.scalars(db.select(Assessment).where(Assessment.student_id == current_user.id).order_by(desc(Assessment.assessed_at)).limit(6)).all()
    latest = recent[0] if recent else None
    previous = next((a for a in recent[1:] if latest and comparison_signature(a) == comparison_signature(latest)), None)
    change = latest.percentage - previous.percentage if latest and previous else None
    trend = list(reversed(recent))
    return render_template("student/dashboard.html", recent=recent, latest=latest, change=change, trend=trend)

@bp.route("/analyze", methods=["GET", "POST"])
@login_required
def analyze():
    rule, rules = active_rules()
    prefill_rows = []
    if request.method == "POST":
        try:
            names, obtained, maximum, passing = (request.form.getlist(k) for k in ("subject[]", "obtained[]", "maximum[]", "passing[]"))
            rows = [{"subject":n,"obtained":o,"maximum":m,"passing":p} for n,o,m,p in zip(names, obtained, maximum, passing)]
            prefill_rows = rows
            if not rows or len({len(names),len(obtained),len(maximum),len(passing)}) != 1: raise ValueError("Complete every subject row before analyzing.")
            if request.form.get("confirm_review") != "yes": raise ValueError("Review and confirm the marks before analysis.")
            result = analyze_marks(rows, rules)
            key = request.form.get("request_key", "")
            try: key = str(uuid.UUID(key))
            except (ValueError, TypeError, AttributeError): raise ValueError("Refresh the form and submit again.")
            existing = db.session.scalar(db.select(Assessment).where(Assessment.student_id == current_user.id, Assessment.idempotency_key == key))
            if existing: return redirect(url_for("student.result", assessment_id=existing.id))
            semester = request.form.get("semester", str(current_user.semester))
            if not semester.isdigit() or not 1 <= int(semester) <= 20: raise ValueError("Enter a valid semester.")
            assessment = Assessment(student_id=current_user.id, course=current_user.course, semester=int(semester), academic_year=request.form.get("academic_year", "").strip()[:20] or None, label=request.form.get("label", "Assessment").strip()[:120] or "Assessment", idempotency_key=key, percentage=result["percentage"], grade=result["grade"], passed=result["passed"], total_obtained=result["total_obtained"], total_maximum=result["total_maximum"], rule_version=rule.version if rule else 1, rule_snapshot=rules)
            for row in result["marks"]:
                assessment.marks.append(AssessmentMark(**row))
            db.session.add(assessment)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                existing = db.session.scalar(db.select(Assessment).where(Assessment.student_id == current_user.id, Assessment.idempotency_key == key))
                if existing: return redirect(url_for("student.result", assessment_id=existing.id))
                raise
            return redirect(url_for("student.result", assessment_id=assessment.id))
        except ValueError as exc:
            db.session.rollback(); flash(str(exc), "error")
        except Exception:
            db.session.rollback(); current_app.logger.exception("Assessment save failed")
            flash("We could not save this assessment. Please try again.", "error")
    else:
        draft_token = session.pop("marksheet_draft_token", None)
        if draft_token:
            try: prefill_rows = consume_marksheet_draft(draft_token)
            except ValueError as exc: flash(str(exc), "warning")
    catalog = db.session.scalars(db.select(AcademicSubject).where(AcademicSubject.course == current_user.course, AcademicSubject.semester == current_user.semester).order_by(AcademicSubject.name)).all()
    return render_template("student/analyze.html", request_key=str(uuid.uuid4()), catalog=catalog, prefill_rows=prefill_rows)

def owned_assessment(assessment_id):
    item = db.session.scalar(db.select(Assessment).where(Assessment.id == assessment_id, Assessment.student_id == current_user.id))
    if item is None: abort(404)
    return item

@bp.route("/assessment/<int:assessment_id>/edit", methods=["GET", "POST"])
@login_required
def edit_assessment(assessment_id):
    item = owned_assessment(assessment_id)
    rules = item.rule_snapshot or active_rules()[1]
    default_pass_percent = float(rules.get("subject_pass_percent", DEFAULT_RULES["subject_pass_percent"]))
    prefill_rows = [{
        "subject":mark.subject,
        "obtained":mark.obtained,
        "maximum":mark.maximum,
        "passing":None if abs(mark.passing - mark.maximum * default_pass_percent / 100) < 0.000001 else mark.passing,
    } for mark in item.marks]
    if request.method == "POST":
        try:
            names, obtained, maximum, passing = (request.form.getlist(key) for key in ("subject[]", "obtained[]", "maximum[]", "passing[]"))
            rows = [{"subject":name,"obtained":score,"maximum":top,"passing":pass_mark} for name,score,top,pass_mark in zip(names,obtained,maximum,passing)]
            prefill_rows = rows
            if not rows or len({len(names),len(obtained),len(maximum),len(passing)}) != 1:
                raise ValueError("Complete every subject row before saving changes.")
            if request.form.get("confirm_review") != "yes":
                raise ValueError("Review and confirm the edited marks before saving.")
            result = analyze_marks(rows, rules)
            semester = request.form.get("semester", str(item.semester))
            if not semester.isdigit() or not 1 <= int(semester) <= 20:
                raise ValueError("Enter a valid semester.")
            item.label = request.form.get("label", item.label).strip()[:120] or item.label
            item.semester = int(semester)
            item.academic_year = request.form.get("academic_year", "").strip()[:20] or None
            item.percentage = result["percentage"]
            item.grade = result["grade"]
            item.passed = result["passed"]
            item.total_obtained = result["total_obtained"]
            item.total_maximum = result["total_maximum"]
            item.marks.clear()
            db.session.flush()
            for mark in result["marks"]:
                item.marks.append(AssessmentMark(**mark))
            db.session.commit()
            flash("Assessment updated. Your result has been recalculated.", "success")
            return redirect(url_for("student.result", assessment_id=item.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Assessment update failed")
            flash("We could not save these changes. Please try again.", "error")
    catalog = db.session.scalars(db.select(AcademicSubject).where(AcademicSubject.course == current_user.course, AcademicSubject.semester == current_user.semester).order_by(AcademicSubject.name)).all()
    return render_template("student/analyze.html", request_key="", catalog=catalog, prefill_rows=prefill_rows, editing_item=item)

@bp.post("/assessment/<int:assessment_id>/delete")
@login_required
def delete_assessment(assessment_id):
    item = owned_assessment(assessment_id)
    db.session.delete(item)
    db.session.commit()
    flash("Assessment and its subject marks were deleted.", "success")
    return redirect(url_for("student.history"))

@bp.get("/history")
@login_required
def history():
    page = request.args.get("page", 1, type=int)
    term = request.args.get("q", "").strip()[:80]
    query = db.select(Assessment).where(Assessment.student_id == current_user.id)
    if term:
        pattern = f"%{term}%"
        query = query.where(or_(Assessment.label.ilike(pattern), Assessment.course.ilike(pattern)))
    items = db.paginate(query.order_by(desc(Assessment.assessed_at)), page=page, per_page=20, error_out=False)
    return render_template("student/history.html", items=items, term=term)

@bp.get("/compare")
@login_required
def compare():
    rows = db.session.scalars(db.select(Assessment).where(Assessment.student_id == current_user.id).order_by(desc(Assessment.assessed_at), desc(Assessment.id)).limit(200)).all()
    grouped, changes = defaultdict(list), {}
    for item in rows:
        grouped[comparison_signature(item)].append(item)
        changes[item.id] = None
    for attempts in grouped.values():
        attempts.sort(key=lambda item: (item.assessed_at, item.id))
        for previous, item in zip(attempts, attempts[1:]):
            changes[item.id] = item.percentage - previous.percentage
    return render_template("student/compare.html", rows=rows, changes=changes)

@bp.get("/prediction")
@login_required
def prediction():
    run = db.session.scalar(db.select(PredictionModelRun).where(PredictionModelRun.validated.is_(True)).order_by(desc(PredictionModelRun.created_at)).limit(1))
    estimate = None
    if run and run.artifact_filename and re.fullmatch(r"[0-9a-f]{32}\.joblib", run.artifact_filename):
        attempts = db.session.scalars(db.select(Assessment).where(Assessment.student_id == current_user.id).order_by(desc(Assessment.assessed_at), desc(Assessment.id)).limit(100)).all()
        attempts.reverse()
        if len(attempts) >= 2:
            try:
                import joblib
                from app.prediction import predict_next
                model_path = os.path.join(current_app.config["PREDICTION_FOLDER"], run.artifact_filename)
                if os.path.isfile(model_path):
                    estimate = predict_next({"available":True,"model":joblib.load(model_path)},
                        [{"percentage":a.percentage,"semester":a.semester} for a in attempts], current_user.semester)
            except Exception:
                current_app.logger.exception("Validated prediction model could not be loaded")
                estimate = None
    return render_template("student/prediction.html", estimate=estimate, run=run)

@bp.get("/assessment/<int:assessment_id>")
@login_required
def result(assessment_id):
    item = owned_assessment(assessment_id)
    return render_template("student/result.html", item=item, suggestions=[m.recommendation for m in item.marks if not m.passed or m.percentage < item.rule_snapshot.get("weak_threshold", 50)])

@bp.get("/assessment/<int:assessment_id>/report.pdf")
@login_required
def report(assessment_id):
    item = owned_assessment(assessment_id)
    from app.reports import make_report
    return send_file(make_report(item), mimetype="application/pdf", as_attachment=True, download_name=f"performance-{item.id}.pdf")

@bp.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        file = request.files.get("marksheet")
        if not file or not file.filename or "." not in file.filename:
            flash("Choose a PDF, JPG, PNG, XLS or XLSX file.", "error")
        else:
            ext = file.filename.rsplit(".", 1)[1].lower()
            if ext not in ALLOWED_UPLOADS: flash("That file type is not supported.", "error")
            elif not upload_signature_matches(file, ext): flash("The file contents do not match the selected file type.", "error")
            else:
                from app.marksheets import MarksheetError, extract_marksheet
                try:
                    rows = extract_marksheet(file.read(), ext)
                    _, rules = active_rules()
                    analyze_marks(rows, rules)
                    token = save_marksheet_draft(rows)
                except (MarksheetError, ValueError) as exc:
                    flash(str(exc), "error")
                except OSError:
                    flash("We could not prepare the extracted marks securely. Please try again.", "error")
                else:
                    session["marksheet_draft_token"] = token
                    flash(f"Read {len(rows)} subject(s). Review every extracted mark before analyzing.", "success")
                    return redirect(url_for("student.analyze"))
    return render_template("student/upload.html")

@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower() or None
        if not 2 <= len(name) <= 120 or (email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)):
            flash("Enter a valid name and, if provided, a valid email address.", "error")
        else:
            duplicate = db.session.scalar(db.select(User).where(func.lower(User.email) == email, User.id != current_user.id)) if email else None
            if duplicate:
                flash("That email address is already in use.", "error")
            else:
                current_user.name, current_user.email = name, email
                db.session.commit()
                flash("Profile updated.", "success")
                return redirect(url_for("student.profile"))
    return render_template("student/profile.html")

@bp.post("/account/password")
@login_required
def change_password():
    if current_user.role != "student": abort(403)
    old_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")
    if not current_user.check_password(old_password):
        flash("Current secure password was not recognized.", "error")
    elif len(new_password) < 14 or len(new_password) > 256:
        flash("Choose a new secure password with at least 14 characters.", "error")
    elif new_password != confirm_password:
        flash("The new passwords do not match.", "error")
    else:
        current_user.set_password(new_password)
        current_user.student_password_initialized = True
        db.session.commit()
        flash("Secure password updated.", "success")
    return redirect(url_for("student.dashboard"))

@bp.post("/account/delete")
@login_required
def delete_account():
    if current_user.role != "student": abort(403)
    user = current_user._get_current_object()
    if request.form.get("confirm_delete") != "yes" or not user.check_password(request.form.get("current_password", "")):
        flash("Enter your secure password and confirm account deletion to continue.", "error")
        return redirect(url_for("student.dashboard"))
    from app.auth import _login_identity_hash
    identities = {_login_identity_hash(f"student|{(user.student_id or '')[:40]}"), _login_identity_hash(f"student-password|{user.id}")}
    db.session.execute(db.delete(LoginAttempt).where(LoginAttempt.identity_hash.in_(identities)))
    db.session.execute(db.delete(AuditEvent).where(or_(AuditEvent.detail == f"user_id={user.id}", AuditEvent.detail.like(f"user_id={user.id};%"))))
    for filename in os.listdir(current_app.config["UPLOAD_FOLDER"]):
        if filename.startswith("draft-") and filename.endswith(".json"):
            path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
            try:
                with open(path, encoding="utf-8") as draft_file:
                    draft = json.load(draft_file)
                if isinstance(draft, dict) and draft.get("student_id") == user.id:
                    os.remove(path)
            except (OSError, ValueError):
                continue
    session.pop("marksheet_draft_token", None)
    db.session.delete(user)
    db.session.commit()
    logout_user()
    flash("Your account and saved assessment data were deleted.", "success")
    return redirect(url_for("auth.login"))
