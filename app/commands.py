import os
import time
import click
from flask import current_app
from app import db
from app.analysis import DEFAULT_RULES
from app.models import GradingRule, LoginAttempt, User

def register_commands(app):
    @app.cli.command("create-admin")
    def create_admin():
        """Provision an administrator from ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_NAME."""
        email, password = os.getenv("ADMIN_EMAIL", "").strip().lower(), os.getenv("ADMIN_PASSWORD", "")
        name = os.getenv("ADMIN_NAME", "Administrator").strip()
        if not email or len(password) < 14:
            raise click.ClickException("Set ADMIN_EMAIL and an ADMIN_PASSWORD of at least 14 characters in the environment.")
        if db.session.query(User.id).filter_by(email=email).first():
            raise click.ClickException("An account with that email already exists.")
        user = User(name=name, email=email, role="admin", active=True)
        user.set_password(password)
        db.session.add(user)
        if not db.session.query(GradingRule.id).first():
            db.session.add(GradingRule(version=1, **DEFAULT_RULES))
        db.session.commit()
        click.echo("Administrator account provisioned.")

    @app.cli.command("init-grading")
    def init_grading():
        """Create the initial grading configuration if none exists."""
        if not db.session.query(GradingRule.id).first():
            db.session.add(GradingRule(version=1, **DEFAULT_RULES)); db.session.commit()
            click.echo("Initial grading rules created.")
        else:
            click.echo("Grading rules already exist.")

    @app.cli.command("cleanup-uploads")
    @click.option("--days", default=30, type=click.IntRange(min=1, max=3650))
    def cleanup_uploads(days):
        """Delete abandoned marksheet drafts and legacy uploads past retention."""
        removed = 0
        for name in os.listdir(current_app.config["UPLOAD_FOLDER"]):
            path = os.path.join(current_app.config["UPLOAD_FOLDER"], name)
            retention_days = min(days, 1) if name.startswith("draft-") and name.endswith(".json") else days
            if os.path.isfile(path) and os.path.getmtime(path) < time.time() - retention_days * 86400:
                os.remove(path); removed += 1
        click.echo(f"Removed {removed} expired upload(s).")

    @app.cli.command("cleanup-login-attempts")
    def cleanup_login_attempts():
        """Remove old hashed login-failure records."""
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=15)
        removed = db.session.query(LoginAttempt).filter(LoginAttempt.attempted_at < cutoff).delete(synchronize_session=False)
        db.session.commit()
        click.echo(f"Removed {removed} old login-attempt record(s).")

    @app.cli.command("evaluate-prediction-model")
    def evaluate_prediction_model():
        """Train, evaluate and persist an optional baseline model from real records."""
        from uuid import uuid4
        from app.models import Assessment, PredictionModelRun
        from app.prediction import train_if_suitable
        rows = db.session.execute(db.select(User.analytics_key, Assessment.percentage, Assessment.semester, Assessment.assessed_at).join(Assessment, Assessment.student_id == User.id).order_by(Assessment.assessed_at)).all()
        history = [{"student_key":key,"percentage":percentage,"semester":semester,"assessment_date":date} for key,percentage,semester,date in rows]
        result = train_if_suitable(history)
        if result is None:
            click.echo("No model trained: historical data does not meet the minimum data requirements.")
            return
        artifact_name = None
        if result["available"]:
            import joblib
            artifact_name = f"{uuid4().hex}.joblib"
            joblib.dump(result["model"], os.path.join(current_app.config["PREDICTION_FOLDER"], artifact_name))
        run = PredictionModelRun(version=result["version"], artifact_filename=artifact_name,
            training_students=result["students"], training_sequences=result["sequences"],
            validation_mae=result["mae"], baseline_mae=result["baseline_mae"],
            validation_r2=result["r2"], validated=result["available"])
        db.session.add(run); db.session.commit()
        click.echo("Validated model stored." if result["available"] else "Evaluation stored; model did not pass validation and will not produce estimates.")
