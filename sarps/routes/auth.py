""""""
import logging
import secrets

import requests
from authlib.integrations.base_client import OAuthError
from flask import (Blueprint, current_app, flash, redirect, render_template, request, session,
                   url_for)
from flask_login import current_user, login_user, logout_user
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from sarps.constants import Role
from sarps.extensions import db, oauth
from sarps.forms import GoogleProfileForm, LoginForm, StudentRegistrationForm
from sarps.models import Department, User
from sarps.security import home_endpoint, is_safe_next_url
from flask_login import login_required

auth_bp = Blueprint("auth", __name__)
log = logging.getLogger(__name__)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """"""
    if current_user.is_authenticated:
        return redirect(url_for(home_endpoint(current_user)))

    departments = list(db.session.scalars(select(Department).order_by(Department.name)))
    form = StudentRegistrationForm()
    form.department_id.choices = [(d.id, d.name) for d in departments]

    if not departments:
        return render_template("auth/register.html", form=form, no_departments=True), 503

    if form.validate_on_submit():
        student = User(full_name=form.full_name.data, email=form.email.data,
                       role=Role.STUDENT, department_id=form.department_id.data,
                       matric_number=form.matric_number.data)
        student.set_password(form.password.data)
        db.session.add(student)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("An account with this email or matriculation number already exists. "
                  "Please sign in.", "error")
            return redirect(url_for("auth.login"))
        flash("Your account has been created. Please sign in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/register.html", form=form, no_departments=False)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(home_endpoint(current_user)))

    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.scalar(select(User).where(User.email == form.email.data))
        if user is None or not user.check_password(form.password.data):
            flash("Incorrect email or password.", "error")
        elif not user.is_active:
            flash("This account has been deactivated. Please contact the administrator.", "error")
        else:
            login_user(user)
            target = request.args.get("next")
            if is_safe_next_url(target):
                return redirect(target)
            return redirect(url_for(home_endpoint(user)))
    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("main.index"))

def google_configured():
    return bool(current_app.config.get("GOOGLE_CLIENT_ID") and current_app.config.get("GOOGLE_CLIENT_SECRET"))


def google_client():
    return oauth.create_client("google")


def _google_unavailable():
    flash("Google sign-in is not set up on this server yet. The administrator needs to add the "
          "Google keys to the .env file. You can sign in with your email and password instead.", "error")
    return redirect(url_for("auth.login"))


def _google_unreachable():
    flash("We could not reach Google just now. Check your internet connection and try again, "
          "or sign in with your email and password.", "error")
    return redirect(url_for("auth.login"))


@auth_bp.route("/auth/google")
def google_login():
    if current_user.is_authenticated:
        return redirect(url_for(home_endpoint(current_user)))
    if not google_configured():
        return _google_unavailable()
    target = request.args.get("next")
    session["google_next"] = target if is_safe_next_url(target) else None
    try:
        return google_client().authorize_redirect(url_for("auth.google_callback", _external=True))
    except (requests.RequestException, OAuthError):
        log.warning("Could not reach Google", exc_info=True)
        return _google_unreachable()


@auth_bp.route("/auth/google/callback")
def google_callback():
    if not google_configured():
        return _google_unavailable()
    try:
        token = google_client().authorize_access_token()
    except requests.RequestException:
        log.warning("Could not reach Google", exc_info=True)
        return _google_unreachable()
    except OAuthError:
        flash("Google sign-in was cancelled or could not be completed. Please try again.", "error")
        return redirect(url_for("auth.login"))

    info = token.get("userinfo") or {}
    sub = str(info.get("sub") or "")
    email = str(info.get("email") or "").strip().lower()
    if not sub or not email or info.get("email_verified") is not True:
        flash("Google did not confirm your email address, so you cannot sign in with it.", "error")
        return redirect(url_for("auth.login"))

    user = db.session.scalar(select(User).where(User.google_sub == sub))
    if user is None:
        user = db.session.scalar(select(User).where(User.email == email))
        if user is not None and user.google_sub and user.google_sub != sub:
            flash("This account is already linked to a different Google account.", "error")
            return redirect(url_for("auth.login"))

    if user is None:
        session["google_pending"] = {"sub": sub, "email": email, "name": str(info.get("name") or "")}
        return redirect(url_for("auth.google_profile"))

    if not user.is_active:
        flash("This account has been deactivated. Please contact the administrator.", "error")
        return redirect(url_for("auth.login"))
    if not user.google_sub:
        user.google_sub = sub
        db.session.commit()
    login_user(user)
    target = session.pop("google_next", None)
    return redirect(target if is_safe_next_url(target) else url_for(home_endpoint(user)))


@auth_bp.route("/auth/google/profile", methods=["GET", "POST"])
def google_profile():
    """"""
    if current_user.is_authenticated:
        return redirect(url_for(home_endpoint(current_user)))
    pending = session.get("google_pending")
    if not pending:
        flash("Please start again with the Google button.", "info")
        return redirect(url_for("auth.login"))

    departments = list(db.session.scalars(select(Department).order_by(Department.name)))
    form = GoogleProfileForm()
    form.department_id.choices = [(d.id, d.name) for d in departments]
    if not departments:
        return render_template("auth/google_profile.html", form=form, email=pending["email"], no_departments=True), 503

    if request.method == "GET":
        form.full_name.data = pending["name"]
    if form.validate_on_submit():
        taken = db.session.scalar(select(User.id).where(
            (User.email == pending["email"]) | (User.google_sub == pending["sub"])))
        if taken:
            session.pop("google_pending", None)
            flash("An account for this Google email already exists. Please sign in.", "error")
            return redirect(url_for("auth.login"))
        student = User(full_name=form.full_name.data, email=pending["email"], role=Role.STUDENT,
                       department_id=form.department_id.data, matric_number=form.matric_number.data,
                       google_sub=pending["sub"])
        student.set_password(secrets.token_urlsafe(32))
        db.session.add(student)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            session.pop("google_pending", None)
            flash("An account with this email or matriculation number already exists. "
                  "Please sign in.", "error")
            return redirect(url_for("auth.login"))
        session.pop("google_pending", None)
        login_user(student)
        flash("Your account has been created.", "success")
        return redirect(url_for(home_endpoint(student)))
    return render_template("auth/google_profile.html", form=form, email=pending["email"], no_departments=False)
