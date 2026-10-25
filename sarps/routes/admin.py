"""Administrator pages: accounts, departments and adviser/lecturer assignments.

The administrator manages accounts but has no page that shows assessments.
"""
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, select

from sarps.constants import ASSIGNABLE_ROLES, ROLE_LABELS, Role
from sarps.extensions import db
from sarps.forms import AssignmentForm, CreateStaffForm, DepartmentForm
from sarps.models import Department, StaffAssignment, User
from sarps.security import role_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/")
@role_required(Role.ADMIN)
def dashboard():
    counts = dict(db.session.execute(select(User.role, func.count()).group_by(User.role)).all())
    stats = {
        "roles": [(label, counts.get(role, 0)) for role, label in ROLE_LABELS.items()],
        "departments": db.session.scalar(select(func.count()).select_from(Department)),
        "assignments": db.session.scalar(select(func.count()).select_from(StaffAssignment)),
    }
    model = current_app.extensions["prediction"].status()
    return render_template("admin/dashboard.html", stats=stats, model=model)


@admin_bp.route("/users", methods=["GET", "POST"])
@role_required(Role.ADMIN)
def users():
    departments = list(db.session.scalars(select(Department).order_by(Department.name)))
    form = CreateStaffForm()
    form.department_id.choices = [(0, "None")] + [(d.id, d.name) for d in departments]

    if form.validate_on_submit():
        staff = User(full_name=form.full_name.data, email=form.email.data, role=form.role.data,
                     department_id=form.department_id.data or None)
        staff.set_password(form.password.data)
        db.session.add(staff)
        db.session.commit()
        flash(f"Account created for {staff.full_name}. Share the temporary password with them privately.", "success")
        return redirect(url_for("admin.users"))

    role_filter = request.args.get("role", "")
    query = select(User).order_by(User.role, User.full_name)
    if role_filter in ROLE_LABELS:
        query = query.where(User.role == role_filter)
    pagination = db.paginate(query, page=request.args.get("page", 1, type=int),
                             per_page=current_app.config["PER_PAGE"], error_out=False)
    return render_template("admin/users.html", form=form, pagination=pagination,
                           role_filter=role_filter, role_labels=ROLE_LABELS)


@admin_bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@role_required(Role.ADMIN)
def toggle_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "error")
    else:
        user.active = not user.active
        db.session.commit()
        flash(f"{user.full_name} is now {'active' if user.active else 'deactivated'}.", "success")
    return redirect(request.referrer if request.referrer and request.host in request.referrer
                    else url_for("admin.users"))


@admin_bp.route("/departments", methods=["GET", "POST"])
@role_required(Role.ADMIN)
def departments():
    form = DepartmentForm()
    if form.validate_on_submit():
        db.session.add(Department(name=form.name.data))
        db.session.commit()
        flash("Department added.", "success")
        return redirect(url_for("admin.departments"))
    rows = db.session.execute(
        select(Department, func.count(User.id))
        .outerjoin(User, (User.department_id == Department.id) & (User.role == Role.STUDENT))
        .group_by(Department.id).order_by(Department.name)).all()
    return render_template("admin/departments.html", form=form, rows=rows)


@admin_bp.route("/assignments", methods=["GET", "POST"])
@role_required(Role.ADMIN)
def assignments():
    staff = list(db.session.scalars(
        select(User).where(User.role.in_(ASSIGNABLE_ROLES), User.active.is_(True)).order_by(User.full_name)))
    students = list(db.session.scalars(
        select(User).where(User.role == Role.STUDENT, User.active.is_(True)).order_by(User.full_name)))
    form = AssignmentForm()
    form.staff_id.choices = [(s.id, f"{s.full_name} ({s.role_label})") for s in staff]
    form.student_id.choices = [(s.id, f"{s.full_name} ({s.matric_number})") for s in students]

    if form.validate_on_submit():
        exists = db.session.scalar(select(StaffAssignment.id).where(
            StaffAssignment.staff_id == form.staff_id.data,
            StaffAssignment.student_id == form.student_id.data))
        if exists:
            flash("That assignment already exists.", "error")
        else:
            db.session.add(StaffAssignment(staff_id=form.staff_id.data, student_id=form.student_id.data))
            db.session.commit()
            flash("Assignment saved.", "success")
        return redirect(url_for("admin.assignments"))

    pagination = db.paginate(
        select(StaffAssignment).order_by(StaffAssignment.id.desc()),
        page=request.args.get("page", 1, type=int), per_page=current_app.config["PER_PAGE"], error_out=False)
    return render_template("admin/assignments.html", form=form, pagination=pagination)


@admin_bp.route("/assignments/<int:assignment_id>/delete", methods=["POST"])
@role_required(Role.ADMIN)
def delete_assignment(assignment_id):
    assignment = db.session.get(StaffAssignment, assignment_id)
    if assignment is None:
        abort(404)
    db.session.delete(assignment)
    db.session.commit()
    flash("Assignment removed.", "success")
    return redirect(url_for("admin.assignments"))
