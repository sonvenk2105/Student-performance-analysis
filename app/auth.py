import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy import func
from app import db
from app.models import LoginAttempt, User

bp = Blueprint("auth", __name__)


def _login_identity_hash(identifier):
    identity = f"{request.remote_addr or 'unknown'}|{identifier}".encode()
    return hmac.new(current_app.config["SECRET_KEY"].encode(), identity, hashlib.sha256).hexdigest()


def _login_is_rate_limited(identity_hash, now):
    window = now - timedelta(minutes=15)
    failures = db.session.scalar(
        db.select(func.count(LoginAttempt.id)).where(
            LoginAttempt.identity_hash == identity_hash,
            LoginAttempt.attempted_at >= window,
        )
    ) or 0
    return failures >= 10


def _record_login_failure(identity_hash, now):
    db.session.add(LoginAttempt(identity_hash=identity_hash, attempted_at=now))
    db.session.commit()


def _generate_student_password(user):
    name_letters = "".join(character for character in user.name if character.isalpha())[:3].upper().ljust(3, "X")
    id_digits = "".join(character for character in (user.student_id or "") if character.isdigit())[-3:].zfill(3)
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    random_chars = "".join(secrets.choice(alphabet) for _ in range(16))
    suffix = "-".join(random_chars[index:index + 4] for index in range(0, 16, 4))
    return f"{name_letters}2026{id_digits}-{suffix}"


def _clear_pending_student():
    for key in ("pending_student_user_id", "pending_student_mode", "pending_student_expires", "pending_student_remember"):
        session.pop(key, None)


def _pending_student():
    user_id = session.get("pending_student_user_id")
    expires = session.get("pending_student_expires", 0)
    if not user_id or expires < datetime.now(timezone.utc).timestamp():
        _clear_pending_student()
        return None
    user = db.session.get(User, user_id)
    if not user or user.role != "student" or not user.active:
        _clear_pending_student()
        return None
    return user


def _finish_student_login(user):
    remember = session.get("pending_student_remember", False)
    _clear_pending_student()
    login_user(user, remember=remember, fresh=True)
    return redirect(url_for("auth.index"))

@bp.get("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard" if current_user.role == "admin" else "student.dashboard"))
    return redirect(url_for("auth.login"))

@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name, sid = request.form.get("name", "").strip(), request.form.get("student_id", "").strip().upper()
        college_name = request.form.get("college_name", "").strip()
        course, semester = request.form.get("course", "").strip(), request.form.get("semester", "")
        if len(name) < 2 or len(name) > 120 or not sid or len(sid) > 40:
            flash("Enter a valid name and student ID.", "error")
        elif not college_name or len(college_name) > 150:
            flash("Enter your college name.", "error")
        elif not course or len(course) > 100 or not semester.isdigit() or not 1 <= int(semester) <= 20:
            flash("Enter a course and semester from 1 to 20.", "error")
        elif db.session.scalar(db.select(User.id).where(func.upper(User.student_id) == sid)):
            flash("That student ID is already registered.", "error")
        else:
            user = User(name=name, student_id=sid, email=None, college_name=college_name, course=course, semester=int(semester), role="student")
            user.set_password(secrets.token_urlsafe(32))
            db.session.add(user); db.session.commit()
            if current_user.is_authenticated:
                logout_user()
            flash("Account created. Please sign in.", "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/register.html")

@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated: return redirect(url_for("auth.index"))
    if request.method == "POST":
        _clear_pending_student()
        name = request.form.get("name", "").strip()
        student_id = request.form.get("student_id", "").strip().upper()
        now = datetime.now(timezone.utc)
        identity_hash = _login_identity_hash(f"student|{student_id[:40]}")
        if _login_is_rate_limited(identity_hash, now):
            flash("Student name or ID was not recognized. Try again after 15 minutes.", "error")
            return render_template("auth/login.html"), 429
        user = None
        if 2 <= len(name) <= 120 and 1 <= len(student_id) <= 40:
            user = db.session.scalar(
                db.select(User).where(
                    User.role == "student",
                    User.active.is_(True),
                    func.lower(User.name) == name.lower(),
                    func.upper(User.student_id) == student_id,
                )
            )
        if user:
            session["pending_student_user_id"] = user.id
            session["pending_student_mode"] = "verify" if user.student_password_initialized else "setup"
            session["pending_student_expires"] = int(now.timestamp()) + 600
            session["pending_student_remember"] = request.form.get("remember") == "yes"
            if not user.student_password_initialized:
                generated_password = _generate_student_password(user)
                user.set_password(generated_password)
                db.session.commit()
                return render_template("auth/student_password_setup.html", generated_password=generated_password)
            return redirect(url_for("auth.student_password"))
        _record_login_failure(identity_hash, now)
        flash("Student name or ID was not recognized.", "error")
    return render_template("auth/login.html")


@bp.route("/login/password", methods=["GET", "POST"])
def student_password():
    user = _pending_student()
    mode = session.get("pending_student_mode")
    if not user or mode not in {"setup", "verify"}:
        flash("Enter your student name and ID to continue.", "warning")
        return redirect(url_for("auth.login"))

    if mode == "setup":
        if request.method != "POST":
            return redirect(url_for("auth.login"))
        saved_password = request.form.get("generated_password", "")
        if request.form.get("saved_password") == "yes" and user.check_password(saved_password):
            user.student_password_initialized = True
            db.session.commit()
            return _finish_student_login(user)
        _clear_pending_student()
        flash("The generated password could not be confirmed. Please sign in again.", "error")
        return redirect(url_for("auth.login"))

    now = datetime.now(timezone.utc)
    identity_hash = _login_identity_hash(f"student-password|{user.id}")
    if request.method == "POST":
        if _login_is_rate_limited(identity_hash, now):
            flash("That password was not recognized. Try again after 15 minutes.", "error")
            return render_template("auth/student_password.html"), 429
        if user.check_password(request.form.get("password", "")):
            return _finish_student_login(user)
        _record_login_failure(identity_hash, now)
        flash("That password was not recognized.", "error")
    return render_template("auth/student_password.html")


@bp.route("/login/forgot-password", methods=["GET", "POST"])
def forgot_student_password():
    if current_user.is_authenticated:
        return redirect(url_for("auth.index"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        student_id = request.form.get("student_id", "").strip().upper()
        now = datetime.now(timezone.utc)
        identity_hash = _login_identity_hash(f"student-password-reset|{student_id[:40]}")
        if _login_is_rate_limited(identity_hash, now):
            flash("Too many recovery attempts. Please try again after 15 minutes.", "error")
            return render_template("auth/student_password_forgot.html"), 429

        user = None
        if 2 <= len(name) <= 120 and 1 <= len(student_id) <= 40:
            user = db.session.scalar(
                db.select(User).where(
                    User.role == "student",
                    User.active.is_(True),
                    func.lower(User.name) == name.lower(),
                    func.upper(User.student_id) == student_id,
                )
            )

        if not user:
            _record_login_failure(identity_hash, now)
            flash("Those details could not be verified. Check them and try again.", "error")
            return render_template("auth/student_password_forgot.html")

        new_password = _generate_student_password(user)
        user.set_password(new_password)
        user.student_password_initialized = True
        db.session.commit()
        session["pending_student_user_id"] = user.id
        session["pending_student_mode"] = "verify"
        session["pending_student_expires"] = int(now.timestamp()) + 600
        session["pending_student_remember"] = False
        return render_template("auth/student_password_forgot.html", new_password=new_password)

    return render_template("auth/student_password_forgot.html")


@bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if current_user.is_authenticated: return redirect(url_for("auth.index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        now = datetime.now(timezone.utc)
        identity_hash = _login_identity_hash(f"admin|{email[:254]}")
        if _login_is_rate_limited(identity_hash, now):
            flash("Email or password was not recognized. Try again after 15 minutes.", "error")
            return render_template("auth/admin_login.html"), 429
        user = db.session.scalar(
            db.select(User).where(
                func.lower(User.email) == email,
                User.role == "admin",
                User.active.is_(True),
            )
        )
        if user and user.check_password(password):
            login_user(user, remember=request.form.get("remember") == "yes", fresh=True)
            return redirect(url_for("auth.index"))
        _record_login_failure(identity_hash, now)
        flash("Email or password was not recognized.", "error")
    return render_template("auth/admin_login.html")

@bp.post("/logout")
def logout():
    logout_user()
    flash("You have signed out.", "success")
    return redirect(url_for("auth.login"))
