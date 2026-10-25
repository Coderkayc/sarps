"""Student pages: take an assessment, see the result, see history."""
import logging

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, select

from sarps.constants import CONSENT_VERSION, Role
from sarps.extensions import db
from sarps.forms import AssessmentForm
from sarps.models import Assessment
from sarps.security import role_required
from sarps.services.access import staff_who_can_view
from sarps.services.classification import classify
from sarps.services.prediction import PredictionError
from ml.features import features_from_inputs

log = logging.getLogger(__name__)
student_bp = Blueprint("student", __name__, url_prefix="/student")


def _own_assessments():
    return select(Assessment).where(Assessment.student_id == current_user.id)


def chart_points(assessments):
    """Oldest-to-newest data for the history chart."""
    return {
        "labels": [a.created_at.strftime("%d %b %Y %H:%M") for a in assessments],
        "values": [a.prob_not_at_risk for a in assessments],
    }


@student_bp.route("/")
@role_required(Role.STUDENT)
def dashboard():
    ordering = (Assessment.created_at.desc(), Assessment.id.desc())
    recent = list(db.session.scalars(_own_assessments().order_by(*ordering).limit(5)))
    total = db.session.scalar(
        select(func.count()).select_from(Assessment).where(Assessment.student_id == current_user.id))
    latest = recent[0] if recent else None
    staff = staff_who_can_view(current_user) if latest and latest.is_flagged else []
    return render_template("student/dashboard.html", latest=latest, recent=recent,
                           total=total, staff=staff)


@student_bp.route("/assess", methods=["GET", "POST"])
@role_required(Role.STUDENT)
def assess():
    service = current_app.extensions["prediction"]
    form = AssessmentForm()
    model_ready = service.is_available()

    if request.method == "POST":
        # No real model means no prediction. We refuse rather than make up a number.
        if not model_ready:
            flash("The prediction model is not available yet, so nothing was submitted.", "error")
            return render_template("student/assess.html", form=form, model_ready=False), 503

        if form.validate_on_submit():
            cgpa = None if form.cgpa_unavailable.data else form.previous_cgpa.data
            features = features_from_inputs(
                attendance_pct=form.attendance_pct.data,
                assignment_completion_pct=form.assignment_completion_pct.data,
                previous_cgpa=cgpa,
                financial_capability=form.financial_capability.data or None,
                study_hours_per_week=form.study_hours_per_week.data,
            )
            try:
                prediction = service.predict(features)
            except PredictionError:
                log.exception("Prediction failed")
                flash("We could not generate a prediction. Nothing was saved. Please try again later.", "error")
                return render_template("student/assess.html", form=form, model_ready=True), 503

            label = classify(prediction.prob_not_at_risk)
            assessment = Assessment(
                student_id=current_user.id,
                attendance_pct=form.attendance_pct.data,
                assignment_completion_pct=form.assignment_completion_pct.data,
                previous_cgpa=cgpa,
                cgpa_unavailable=bool(form.cgpa_unavailable.data),
                financial_capability=form.financial_capability.data or None,
                study_hours_per_week=form.study_hours_per_week.data,
                prob_not_at_risk=prediction.prob_not_at_risk,
                risk_label=label,
                is_flagged=(label == "At Risk"),
                model_version=prediction.model_version,
                consent_given=True,
                consent_version=CONSENT_VERSION,
            )
            db.session.add(assessment)
            db.session.commit()
            flash("Assessment submitted.", "success")
            return redirect(url_for("student.result", assessment_id=assessment.id))

    return render_template("student/assess.html", form=form, model_ready=model_ready)


@student_bp.route("/assessments/<int:assessment_id>")
@role_required(Role.STUDENT)
def result(assessment_id):
    # Looking up by BOTH id and owner means another student's id simply "does not exist".
    assessment = db.session.scalar(_own_assessments().where(Assessment.id == assessment_id))
    if assessment is None:
        abort(404)
    staff = staff_who_can_view(current_user) if assessment.is_flagged else []
    return render_template("student/result.html", assessment=assessment, staff=staff)


@student_bp.route("/history")
@role_required(Role.STUDENT)
def history():
    page = request.args.get("page", 1, type=int)
    pagination = db.paginate(
        _own_assessments().order_by(Assessment.created_at.desc(), Assessment.id.desc()),
        page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    chart_rows = list(db.session.scalars(
        _own_assessments().order_by(Assessment.created_at.desc(), Assessment.id.desc()).limit(50)))
    chart_rows.reverse()
    return render_template("student/history.html", pagination=pagination, chart=chart_points(chart_rows))
