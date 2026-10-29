"""
The SARPS application package.
"""
from datetime import datetime, timezone

from flask import Flask, render_template, request
from flask_login import current_user
from flask_wtf.csrf import CSRFError

from config import Config
from sarps.cli import register_commands
from sarps.constants import STAFF_ROLES, Role
from sarps.extensions import csrf, db, login_manager, oauth
from sarps.services.prediction import PredictionService


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    if app.config.get("TRUST_PROXY"):
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    oauth.init_app(app)
    if app.config.get("GOOGLE_CLIENT_ID") and app.config.get("GOOGLE_CLIENT_SECRET"):
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_CLIENT_ID"],
            client_secret=app.config["GOOGLE_CLIENT_SECRET"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
    PredictionService().init_app(app)

    from sarps import models  
    from sarps.routes.admin import admin_bp
    from sarps.routes.auth import auth_bp
    from sarps.routes.main import main_bp
    from sarps.routes.staff import staff_bp
    from sarps.routes.student import student_bp
    for blueprint in (main_bp, auth_bp, student_bp, staff_bp, admin_bp):
        app.register_blueprint(blueprint)

    register_commands(app)
    register_error_pages(app)
    register_template_helpers(app)
    register_security_headers(app)
    return app


def register_error_pages(app):
    def show(code, title, message):
        return render_template("errors/error.html", code=code, title=title, message=message), code

    @app.errorhandler(403)
    def forbidden(error):
        return show(403, "Access denied", "Your account does not have permission to open this page.")

    @app.errorhandler(404)
    def not_found(error):
        return show(404, "Page not found", "The page you are looking for does not exist or has moved.")

    @app.errorhandler(CSRFError)
    def csrf_failed(error):
        return show(400, "Form expired", "That form is no longer valid. Go back, refresh the page and try again.")

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        return show(500, "Something went wrong", "An unexpected error occurred. Nothing was changed.")


def register_template_helpers(app):
    @app.context_processor
    def inject_globals():
        return {
            "app_name": app.config["APP_NAME"],
            "app_full_name": app.config["APP_FULL_NAME"],
            "institution": app.config.get("INSTITUTION", "University of Nigeria, Nsukka"),
            "now_year": datetime.now(timezone.utc).year,
            "model_status": app.extensions["prediction"].status,
            "Role": Role,
            "STAFF_ROLES": STAFF_ROLES,
        }

    from ml.features import (ATTENDANCE_OPTIONS, FINANCIAL_COMFORT_OPTIONS, FINANCIAL_IMPACT_OPTIONS,
                             STUDY_HOURS_OPTIONS, option_label)
    option_sets = {"attendance": ATTENDANCE_OPTIONS, "study": STUDY_HOURS_OPTIONS,
                   "comfort": FINANCIAL_COMFORT_OPTIONS, "impact": FINANCIAL_IMPACT_OPTIONS}

    @app.template_global("answer")
    def answer(kind, level):
        """Return the label for a given option."""
        return option_label(option_sets[kind], level) if level is not None else None

    @app.template_filter("risk_display")
    def risk_display(label):
        """"""
        return "AT RISK \u26a0" if label == "At Risk" else "NOT AT RISK \u2713"

    @app.template_filter("dt")
    def format_datetime(value):
        return value.strftime("%d %b %Y, %H:%M UTC") if value else ""

    @app.template_filter("pct")
    def format_percent(value):
        return f"{value:.2f}%" if value is not None else ""


def register_security_headers(app):
    @app.after_request
    def add_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; form-action 'self'")
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response
