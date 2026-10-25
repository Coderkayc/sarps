"""Public pages and the role-based dashboard redirect."""
from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required

from sarps.security import home_endpoint

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    return render_template("index.html")


@main_bp.route("/dashboard")
@login_required
def dashboard():
    return redirect(url_for(home_endpoint(current_user)))
