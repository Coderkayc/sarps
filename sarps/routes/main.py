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


@main_bp.route("/assumptions")
def assumptions():
    """A public page listing every rule and assumption the system relies on."""
    from flask import current_app
    from sarps import unn
    return render_template("assumptions.html", bands=unn.GRADE_BANDS, classes=unn.DEGREE_CLASSES,
                           model=current_app.extensions["prediction"].status())
