import os
from datetime import timedelta

from flask import Flask, jsonify
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import text

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    is_render = os.getenv("RENDER", "").lower() == "true"
    secret_key = os.getenv("SECRET_KEY")
    database_url = os.getenv("DATABASE_URL", "sqlite:///student_performance.db")
    if is_render and (not secret_key or len(secret_key) < 32):
        raise RuntimeError("Set SECRET_KEY to a random value of at least 32 characters in production.")
    if is_render and database_url.startswith("sqlite:"):
        raise RuntimeError("Production deployment requires PostgreSQL via DATABASE_URL.")
    app.config.from_mapping(
        SECRET_KEY=secret_key or "dev-only-change-me",
        SQLALCHEMY_DATABASE_URI=database_url.replace("postgres://", "postgresql+psycopg://", 1),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True, "pool_recycle": 300},
        MAX_CONTENT_LENGTH=int(os.getenv("MAX_CONTENT_LENGTH", 10 * 1024 * 1024)),
        UPLOAD_FOLDER=os.path.join(app.instance_path, "uploads"),
        PREDICTION_FOLDER=os.path.join(app.instance_path, "prediction_models"),
        REMEMBER_COOKIE_HTTPONLY=True, SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "1" if is_render else "0") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    )
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["PREDICTION_FOLDER"], exist_ok=True)
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"
    from app import models  # noqa: F401
    from app.auth import bp as auth_bp
    from app.student import bp as student_bp
    from app.admin import bp as admin_bp
    from app.commands import register_commands
    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(admin_bp)
    register_commands(app)

    @app.get("/health")
    def health():
        try:
            db.session.execute(text("SELECT 1"))
            return jsonify(status="ok", database="ok")
        except Exception:
            db.session.rollback()
            return jsonify(status="degraded", database="unavailable"), 503

    @app.errorhandler(413)
    def too_large(_error):
        return "Upload is too large. Maximum size is 10 MB.", 413
    return app
