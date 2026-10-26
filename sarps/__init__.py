"""The SARPS application package.

create_app() builds a fresh Flask app. Using a function (the "application
factory" pattern) lets the tests build their own app with a throw-away database.
"""
from datetime import datetime, timezone

from flask import Flask, render_template, request
from flask_login import current_user
from flask_wtf.csrf import CSRFError

from config import Config
from sarps.cli import register_commands
from sarps.constants import STAFF_ROLES, Role
from sarps.extensions import csrf, db, login_manager
from sarps.services.prediction import PredictionService


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    PredictionService().init_app(app)

    from sarps import models  # noqa: F401  (makes sure the tables are registered)
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
        # Only this site's own scripts and styles may run.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; form-action 'self'")
        # Pages with personal data must not be kept in the browser's cache.
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response
