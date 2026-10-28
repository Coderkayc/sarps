"""Student pages: take an assessment, see the result, see history."""
import logging

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, select

from sarps.constants import CONSENT_VERSION, Role
from sarps.extensions import db
from sarps.forms import AssessmentForm, CourseClaimForm
from sarps.models import Assessment, Course, CourseRecord
from sarps.security import role_required
from sarps.services.access import staff_who_can_view
from sarps.services.advice import INPUT_WORDS, build_advice
from sarps.services.classification import classify
from sarps.services.plan import build_plan
from sarps.services.prediction import PredictionError
from sarps.services.records import course_row, current_term, term_records
from ml.features import features_from_inputs

log = logging.getLogger(__name__)
student_bp = Blueprint("student", __name__, url_prefix="/student")


def _own_assessments():
    return select(Assessment).where(Assessment.student_id == current_user.id)


def _assess_context(service, model_ready):
    """Extra values the assessment page needs: which answers the current model ignores."""
    unused = service.status().get("unused_features", []) if model_ready else []
    return {"model_ready": model_ready, "unused_names": [INPUT_WORDS.get(n, n) for n in unused]}


def features_for(assessment):
    """The model inputs for a saved assessment, or None for an older one made before the redesign."""
    if assessment.attendance_level is None:
        return None
    return features_from_inputs(
        assessment.attendance_level, assessment.assignments_assigned, assessment.assignments_submitted,
        assessment.tests_done, assessment.tests_high, assessment.tests_low, assessment.study_hours_level,
        assessment.financial_comfort, assessment.financial_impact, assessment.previous_cgpa)


def advice_for(assessment):
    """Explanation and advice for one of the student's own assessments."""
    service = current_app.extensions["prediction"]
    drivers = []
    features = features_for(assessment)
    if features is not None:
        try:
            drivers = service.explain(features)
        except Exception:  # the explanation is a bonus: it must never stop the result from showing
            log.warning("Could not explain assessment %s", assessment.id, exc_info=True)
    plan = build_plan(current_user.id) if term_records(current_user.id) else None
    unused = service.status().get("unused_features", []) if features is not None else []
    return build_advice(assessment, drivers, plan, unused), drivers


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
    advice = advice_for(latest)[0] if latest else []
    return render_template("student/dashboard.html", latest=latest, recent=recent,
                           total=total, staff=staff, advice=advice)


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
            return render_template("student/assess.html", form=form, **_assess_context(service, False)), 503

        if form.validate_on_submit():
            cgpa = None if form.cgpa_unavailable else form.previous_cgpa.data
            features = features_from_inputs(
                attendance_level=form.attendance_level.data,
                assignments_assigned=form.assignments_assigned.data,
                assignments_submitted=form.assignments_submitted.data,
                tests_done=form.tests_done.data, tests_high=form.tests_high.data, tests_low=form.tests_low.data,
                study_hours_level=form.study_hours_level.data,
                financial_comfort=form.financial_comfort.data,
                financial_impact=form.financial_impact.data,
                previous_cgpa=cgpa,
            )
            try:
                prediction = service.predict(features)
            except PredictionError:
                log.exception("Prediction failed")
                flash("We could not generate a prediction. Nothing was saved. Please try again later.", "error")
                return render_template("student/assess.html", form=form, **_assess_context(service, True)), 503

            label = classify(prediction.prob_not_at_risk)
            assessment = Assessment(
                student_id=current_user.id,
                attendance_level=form.attendance_level.data,
                assignments_assigned=form.assignments_assigned.data,
                assignments_submitted=form.assignments_submitted.data,
                tests_done=form.tests_done.data, tests_high=form.tests_high.data, tests_low=form.tests_low.data,
                study_hours_level=form.study_hours_level.data,
                financial_comfort=form.financial_comfort.data,
                financial_impact=form.financial_impact.data,
                previous_cgpa=cgpa,
                cgpa_unavailable=form.cgpa_unavailable,
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

    return render_template("student/assess.html", form=form, **_assess_context(service, model_ready))


@student_bp.route("/assessments/<int:assessment_id>")
@role_required(Role.STUDENT)
def result(assessment_id):
    # Looking up by BOTH id and owner means another student's id simply "does not exist".
    assessment = db.session.scalar(_own_assessments().where(Assessment.id == assessment_id))
    if assessment is None:
        abort(404)
    staff = staff_who_can_view(current_user) if assessment.is_flagged else []
    advice = advice_for(assessment)[0]
    return render_template("student/result.html", assessment=assessment, staff=staff, advice=advice)


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


# ---------- course records, plan ----------
def _claim_form():
    form = CourseClaimForm()
    form.course_id.choices = [(c.id, c.label) for c in
                              db.session.scalars(select(Course).order_by(Course.code))]
    return form


def _owned_record(record_id):
    record = db.session.get(CourseRecord, record_id)
    if record is None or record.student_id != current_user.id:
        abort(404)  # someone else's record "does not exist"
    return record


@student_bp.route("/courses", methods=["GET", "POST"])
@role_required(Role.STUDENT)
def courses():
    session_name, semester = current_term()
    form = _claim_form()
    if not form.course_id.choices:
        flash("No courses have been added yet. Ask the administrator to add the course list.", "info")
    if form.validate_on_submit():
        course = db.session.get(Course, form.course_id.data)
        if course is None:
            abort(400)
        record = db.session.scalar(select(CourseRecord).where(
            CourseRecord.student_id == current_user.id, CourseRecord.course_id == course.id,
            CourseRecord.session == session_name, CourseRecord.semester == semester))
        if record is None:
            record = CourseRecord(student_id=current_user.id, course_id=course.id,
                                  session=session_name, semester=semester)
        # Only fields the student filled in are changed.
        for field in ("attendance_claimed", "ca_claimed", "exam_claimed"):
            value = getattr(form, field).data
            if value is not None:
                setattr(record, field, value)
        db.session.add(record)
        db.session.commit()
        flash(f"Saved your figures for {course.code}.", "success")
        return redirect(url_for("student.courses"))
    rows = [course_row(r) for r in term_records(current_user.id)]
    return render_template("student/courses.html", form=form, rows=rows,
                           session_name=session_name, semester=semester)


@student_bp.route("/courses/<int:record_id>/delete", methods=["POST"])
@role_required(Role.STUDENT)
def course_delete(record_id):
    record = _owned_record(record_id)
    has_official = any(getattr(record, f"{f}_official") is not None for f in ("attendance", "ca", "exam"))
    if has_official:
        # Official figures stay; the student can only withdraw their own claims.
        record.attendance_claimed = record.ca_claimed = record.exam_claimed = None
        db.session.commit()
        flash("Your own figures were removed. Official figures are kept.", "success")
    else:
        db.session.delete(record)
        db.session.commit()
        flash("Course removed from your list.", "success")
    return redirect(url_for("student.courses"))


@student_bp.route("/plan")
@role_required(Role.STUDENT)
def plan():
    session_name, semester = current_term()
    return render_template("student/plan.html", plan=build_plan(current_user.id),
                           session_name=session_name, semester=semester)
