"""Student registration, sign in and sign out."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy import select

from sarps.constants import Role
from sarps.extensions import db
from sarps.forms import LoginForm, StudentRegistrationForm
from sarps.models import Department, User
from sarps.security import home_endpoint, is_safe_next_url
from flask_login import login_required

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Only students can register themselves. Staff accounts are created by the administrator."""
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
        db.session.commit()
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
