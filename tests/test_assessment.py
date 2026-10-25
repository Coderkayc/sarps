"""Submitting assessments: validation, consent, the model, the 50% rule and flagging."""
import pytest

from sarps.extensions import db
from sarps.models import Assessment
from sarps.services.classification import classify
from sarps.services.prediction import Prediction, PredictionError
from tests.helpers import (VALID_ASSESSMENT, count_assessments, login, make_department,
                           make_student)


class FixedModel:
    """A stand-in model that returns one chosen probability. For testing the rules only."""

    def __init__(self, percent=None, error=None):
        self.percent, self.error = percent, error

    def is_available(self):
        return True

    def status(self):
        return {"available": True, "version": "fixed-test"}

    def predict(self, features):
        if self.error:
            raise self.error
        return Prediction(self.percent, "fixed-test")


def signed_in_student(client):
    student = make_student("stu@x.com", make_department())
    login(client, "stu@x.com")
    return student


def post(client, **overrides):
    data = dict(VALID_ASSESSMENT)
    data.update(overrides)
    data = {k: v for k, v in data.items() if v is not None}
    return client.post("/student/assess", data=data)


# ---------- no model installed ----------
def test_without_a_model_the_form_is_disabled_and_nothing_is_saved(app, client):
    signed_in_student(client)
    html = client.get("/student/assess").get_data(as_text=True)
    assert "has not been installed yet" in html
    assert "disabled" in html.split("Submit assessment")[0].rsplit("<button", 1)[1]
    response = post(client)
    assert response.status_code == 503
    assert count_assessments() == 0


# ---------- with a model ----------
def test_valid_submission_is_saved_with_a_real_prediction(model_app, model_client):
    student = signed_in_student(model_client)
    response = post(model_client)
    assert response.status_code == 302
    saved = db.session.query(Assessment).one()
    assert response.headers["Location"].endswith(f"/student/assessments/{saved.id}")
    assert saved.student_id == student.id
    assert 0 <= saved.prob_not_at_risk <= 100
    assert saved.risk_label == classify(saved.prob_not_at_risk)
    assert saved.is_flagged == (saved.risk_label == "At Risk")
    assert saved.model_version and saved.model_version != "unknown"
    assert saved.consent_given and saved.consent_version == "v1"
    assert (saved.attendance_pct, saved.assignment_completion_pct) == (80, 70)
    assert saved.previous_cgpa == 3.5 and saved.financial_capability == "medium"


def test_result_page_shows_the_meter_with_the_saved_value(model_app, model_client):
    signed_in_student(model_client)
    post(model_client)
    saved = db.session.query(Assessment).one()
    html = model_client.get(f"/student/assessments/{saved.id}").get_data(as_text=True)
    assert f'data-gauge="{saved.prob_not_at_risk}"' in html
    assert f"{saved.prob_not_at_risk:.2f}%" in html
    assert saved.risk_label in html


def test_only_the_two_mandatory_fields_plus_consent_are_needed(model_app, model_client):
    signed_in_student(model_client)
    response = post(model_client, previous_cgpa=None, financial_capability="", study_hours_per_week=None)
    assert response.status_code == 302
    saved = db.session.query(Assessment).one()
    assert saved.previous_cgpa is None and saved.cgpa_unavailable is False
    assert saved.financial_capability is None and saved.study_hours_per_week is None


def test_cgpa_can_be_marked_unavailable(model_app, model_client):
    signed_in_student(model_client)
    response = post(model_client, previous_cgpa=None, cgpa_unavailable="y")
    assert response.status_code == 302
    saved = db.session.query(Assessment).one()
    assert saved.previous_cgpa is None and saved.cgpa_unavailable is True


def test_cgpa_and_unavailable_together_is_rejected(model_app, model_client):
    signed_in_student(model_client)
    response = post(model_client, cgpa_unavailable="y")
    assert "not both" in response.get_data(as_text=True)
    assert count_assessments() == 0


@pytest.mark.parametrize("missing", ["attendance_pct", "assignment_completion_pct"])
def test_mandatory_fields_are_enforced(model_app, model_client, missing):
    signed_in_student(model_client)
    response = post(model_client, **{missing: None})
    assert response.status_code == 200
    assert "is required" in response.get_data(as_text=True)
    assert count_assessments() == 0


def test_consent_is_required_before_submitting(model_app, model_client):
    signed_in_student(model_client)
    response = post(model_client, consent=None)
    assert "must agree to the sharing arrangement" in response.get_data(as_text=True)
    assert count_assessments() == 0


@pytest.mark.parametrize("field, value", [
    ("attendance_pct", "101"), ("attendance_pct", "-1"), ("attendance_pct", "abc"),
    ("attendance_pct", "nan"), ("attendance_pct", "inf"),
    ("assignment_completion_pct", "100.5"), ("assignment_completion_pct", "nan"),
    ("previous_cgpa", "5.1"), ("previous_cgpa", "-0.1"), ("previous_cgpa", "nan"),
    ("study_hours_per_week", "101"), ("study_hours_per_week", "-3"), ("study_hours_per_week", "inf"),
    ("financial_capability", "rich"),
])
def test_impossible_values_are_rejected(model_app, model_client, field, value):
    signed_in_student(model_client)
    response = post(model_client, **{field: value})
    assert response.status_code == 200
    assert count_assessments() == 0


def test_boundary_values_are_accepted(model_app, model_client):
    signed_in_student(model_client)
    for attendance, cgpa in [("0", "0"), ("100", "5")]:
        response = post(model_client, attendance_pct=attendance, assignment_completion_pct=attendance,
                        previous_cgpa=cgpa, study_hours_per_week=attendance)
        assert response.status_code == 302, (attendance, cgpa)


# ---------- the 50% rule and flagging, with a fixed probability ----------
@pytest.mark.parametrize("percent, label, flagged", [
    (49.99, "At Risk", True),
    (50.0, "At Risk", True),
    (50.01, "Not at Risk", False),
])
def test_rule_and_flagging_at_the_boundary(app, client, percent, label, flagged):
    app.extensions["prediction"] = FixedModel(percent)
    signed_in_student(client)
    assert post(client).status_code == 302
    saved = db.session.query(Assessment).one()
    assert saved.prob_not_at_risk == percent
    assert saved.risk_label == label
    assert saved.is_flagged is flagged


def test_prediction_failure_saves_nothing(app, client):
    app.extensions["prediction"] = FixedModel(error=PredictionError("boom"))
    signed_in_student(client)
    response = post(client)
    assert response.status_code == 503
    assert "Nothing was saved" in response.get_data(as_text=True)
    assert count_assessments() == 0


def test_a_student_can_submit_many_times_and_history_grows(app, client):
    app.extensions["prediction"] = FixedModel(70.0)
    signed_in_student(client)
    for _ in range(3):
        assert post(client).status_code == 302
    assert count_assessments() == 3
    html = client.get("/student/history").get_data(as_text=True)
    assert html.count("70.00%") >= 3
    assert 'id="history-data"' in html


def test_student_dashboard_shows_latest_result(app, client):
    app.extensions["prediction"] = FixedModel(30.0)
    signed_in_student(client)
    post(client)
    html = client.get("/student/").get_data(as_text=True)
    assert "30.00%" in html and "At Risk" in html and "flagged" in html


def test_staff_see_the_new_flagged_assessment(app, client):
    from sarps.constants import Role
    from tests.helpers import assign, make_user
    app.extensions["prediction"] = FixedModel(20.0)
    student = signed_in_student(client)
    adviser = make_user(Role.ADVISER, "adv@x.com", name="Adviser Ann")
    assign(adviser, student)
    post(client)
    client.post("/logout")
    login(client, "adv@x.com")
    html = client.get("/staff/?filter=flagged").get_data(as_text=True)
    assert "Stu" in html and "20.00%" in html
