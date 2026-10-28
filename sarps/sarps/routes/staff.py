"""Pages for academic advisers, lecturers and heads of department.

All three roles use the same pages. What each can see is decided entirely by
sarps/services/access.py, never by the page itself.
"""
from flask import Blueprint, abort, current_app, render_template, request
from flask_login import current_user
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from sarps.constants import STAFF_ROLES
from sarps.extensions import db
from sarps.models import Assessment, User
from sarps.routes.student import chart_points
from sarps.security import role_required
from sarps.services.access import (can_view_student, get_visible_assessment,
                                   latest_assessment_ids, visible_assessments, visible_students)

staff_bp = Blueprint("staff", __name__, url_prefix="/staff")


@staff_bp.route("/")
@role_required(*STAFF_ROLES)
def dashboard():
    latest_ids = latest_assessment_ids(current_user)
    latest = select(Assessment).where(Assessment.id.in_(latest_ids))

    def count(query):
        return db.session.scalar(select(func.count()).select_from(query.subquery()))

    student_total = count(visible_students(current_user))
    assessed = count(latest)
    flagged = count(latest.where(Assessment.is_flagged.is_(True)))

    only_flagged = request.args.get("filter") == "flagged"
    search = request.args.get("q", "").strip()
    listing = latest.join(User, User.id == Assessment.student_id)
    if only_flagged:
        listing = listing.where(Assessment.is_flagged.is_(True))
    if search:
        listing = listing.where(db.or_(
            User.full_name.icontains(search, autoescape=True),
            User.matric_number.icontains(search, autoescape=True)))
    listing = listing.options(selectinload(Assessment.student)).order_by(
        Assessment.is_flagged.desc(), Assessment.created_at.desc())

    pagination = db.paginate(listing, page=request.args.get("page", 1, type=int),
                             per_page=current_app.config["PER_PAGE"], error_out=False)
    return render_template("staff/dashboard.html", pagination=pagination, student_total=student_total,
                           assessed=assessed, flagged=flagged, only_flagged=only_flagged, search=search)


@staff_bp.route("/students/<int:student_id>")
@role_required(*STAFF_ROLES)
def student_detail(student_id):
    if not can_view_student(current_user, student_id):
        abort(404)  # same answer whether the student is missing or simply not yours
    student = db.session.get(User, student_id)
    assessments = list(db.session.scalars(
        visible_assessments(current_user).where(Assessment.student_id == student_id)
        .order_by(Assessment.created_at.desc(), Assessment.id.desc())))
    chart_rows = list(reversed(assessments[:50]))
    return render_template("staff/student_detail.html", student=student,
                           assessments=assessments, chart=chart_points(chart_rows))


@staff_bp.route("/assessments/<int:assessment_id>")
@role_required(*STAFF_ROLES)
def assessment_detail(assessment_id):
    assessment = get_visible_assessment(current_user, assessment_id)
    if assessment is None:
        abort(404)
    return render_template("staff/assessment_detail.html", assessment=assessment)
