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


# ---------- the form itself ----------
def test_form_shows_every_question_and_the_exact_wording(model_app, model_client):
    signed_in_student(model_client)
    html = model_client.get("/student/assess").get_data(as_text=True)
    from ml.features import (ATTENDANCE_OPTIONS, FINANCIAL_COMFORT_OPTIONS, FINANCIAL_IMPACT_OPTIONS,
                             STUDY_HOURS_OPTIONS)
    from markupsafe import escape
    for _, text in ATTENDANCE_OPTIONS + STUDY_HOURS_OPTIONS + FINANCIAL_COMFORT_OPTIONS + FINANCIAL_IMPACT_OPTIONS:
        assert str(escape(text)) in html, text
    for text in ["Class attendance", "Assignment submission", "Tests and Continuous Assessments (CAs)",
                 "Study hours per week", "Financial situation",
                 "How many assignments have been assigned to you so far this semester?",
                 "Out of those, how many have you submitted?",
                 "How many tests or CAs have you done so far this semester?",
                 "Out of those, how many do you think you scored above 70% in?",
                 "How many do you think you scored below 50% in?",
                 "How financially comfortable would you consider yourself as a student?",
                 "Yes, I have my current CGPA", "No, I do not have my CGPA yet",
                 "We understand test results are not always shown to you. Answer based on how you felt your "
                 "performance was"]:
        assert text in html, text


def test_removed_questions_do_not_appear_anywhere(model_app, model_client):
    signed_in_student(model_client)
    post(model_client)
    saved = db.session.query(Assessment).one()
    pages = [model_client.get("/student/assess"), model_client.get(f"/student/assessments/{saved.id}"),
             model_client.get("/student/")]
    for page in pages:
        html = page.get_data(as_text=True).lower()
        for word in ("course difficulty", "carryover", "carry-over", "quiz average"):
            assert word not in html, word


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
    assert saved.attendance_level == 4
    assert (saved.assignments_assigned, saved.assignments_submitted) == (5, 4)
    assert (saved.tests_done, saved.tests_high, saved.tests_low) == (4, 1, 1)
    assert (saved.study_hours_level, saved.financial_comfort, saved.financial_impact) == (3, 3, 2)
    assert saved.previous_cgpa == 3.5 and saved.cgpa_unavailable is False


def test_result_page_shows_the_meter_with_the_saved_value(model_app, model_client):
    signed_in_student(model_client)
    post(model_client)
    saved = db.session.query(Assessment).one()
    html = model_client.get(f"/student/assessments/{saved.id}").get_data(as_text=True)
    assert f'data-gauge="{saved.prob_not_at_risk}"' in html
    assert f"{saved.prob_not_at_risk:.2f}%" in html
    assert ("AT RISK \u26a0" if saved.risk_label == "At Risk" else "NOT AT RISK \u2713") in html


def test_the_two_result_labels_are_exactly_as_specified(app, client):
    for percent, expected, other in [(50.0, "AT RISK \u26a0", "NOT AT RISK"), (50.01, "NOT AT RISK \u2713", "AT RISK \u26a0")]:
        app.extensions["prediction"] = FixedModel(percent)
        signed_in_student(client) if percent == 50.0 else None
        post(client)
        saved = db.session.query(Assessment).order_by(Assessment.id.desc()).first()
        html = client.get(f"/student/assessments/{saved.id}").get_data(as_text=True)
        assert f'chip chip-{"risk" if percent == 50.0 else "ok"}">{expected}' in html
        assert other not in html.split("Classification:")[1].split("</p>")[0]


def test_no_cgpa_is_saved_as_missing_never_zero(model_app, model_client):
    signed_in_student(model_client)
    response = post(model_client, has_cgpa="no", previous_cgpa=None)
    assert response.status_code == 302
    saved = db.session.query(Assessment).one()
    assert saved.previous_cgpa is None and saved.cgpa_unavailable is True


def test_a_cgpa_typed_then_hidden_is_ignored(model_app, model_client):
    signed_in_student(model_client)
    assert post(model_client, has_cgpa="no", previous_cgpa="4.9").status_code == 302
    saved = db.session.query(Assessment).one()
    assert saved.previous_cgpa is None and saved.cgpa_unavailable is True


def test_cgpa_choice_is_required_and_a_value_is_needed_for_yes(model_app, model_client):
    signed_in_student(model_client)
    assert "Please say whether you have a CGPA" in post(model_client, has_cgpa=None).get_data(as_text=True)
    assert "Enter your CGPA" in post(model_client, has_cgpa="yes", previous_cgpa=None).get_data(as_text=True)
    assert count_assessments() == 0


def test_nothing_assigned_and_no_tests_is_handled_safely(model_app, model_client):
    signed_in_student(model_client)
    response = post(model_client, assignments_assigned="0", assignments_submitted="0",
                    tests_done="0", tests_high="0", tests_low="0")
    assert response.status_code == 302
    saved = db.session.query(Assessment).one()
    assert 0 <= saved.prob_not_at_risk <= 100
    html = model_client.get(f"/student/assessments/{saved.id}").get_data(as_text=True)
    assert "None assigned yet" in html and "None done yet" in html


@pytest.mark.parametrize("missing", [
    "attendance_level", "assignments_assigned", "assignments_submitted", "tests_done", "tests_high",
    "tests_low", "study_hours_level", "financial_comfort", "financial_impact", "has_cgpa"])
def test_every_question_is_required(model_app, model_client, missing):
    signed_in_student(model_client)
    response = post(model_client, **{missing: None})
    assert response.status_code == 200
    assert 'class="error-text"' in response.get_data(as_text=True)
    assert count_assessments() == 0


def test_consent_is_required_before_submitting(model_app, model_client):
    signed_in_student(model_client)
    response = post(model_client, consent=None)
    assert "must agree to the sharing arrangement" in response.get_data(as_text=True)
    assert count_assessments() == 0


@pytest.mark.parametrize("field, value", [
    ("attendance_level", "7"), ("attendance_level", "-1"), ("attendance_level", "abc"), ("attendance_level", "2.5"),
    ("study_hours_level", "10"), ("study_hours_level", "-1"),
    ("financial_comfort", "0"), ("financial_comfort", "6"),
    ("financial_impact", "0"), ("financial_impact", "6"),
    ("assignments_assigned", "-1"), ("assignments_assigned", "1.5"), ("assignments_assigned", "abc"),
    ("assignments_assigned", "1001"), ("tests_done", "-2"), ("tests_done", "x"),
    ("previous_cgpa", "5.1"), ("previous_cgpa", "-0.1"), ("previous_cgpa", "nan"), ("previous_cgpa", "inf"),
    ("has_cgpa", "maybe"), ("target_cgpa", "5.5"),
])
def test_impossible_values_are_rejected(model_app, model_client, field, value):
    signed_in_student(model_client)
    response = post(model_client, **{field: value})
    assert response.status_code == 200
    assert count_assessments() == 0


@pytest.mark.parametrize("overrides, message", [
    (dict(assignments_assigned="3", assignments_submitted="4"), "cannot have submitted more assignments (4) than were assigned (3)"),
    (dict(assignments_assigned="0", assignments_submitted="1"), "cannot have submitted more assignments (1) than were assigned (0)"),
    (dict(tests_done="3", tests_high="4", tests_low="0"), "cannot be more than the number of tests or CAs you have done (3)"),
    (dict(tests_done="3", tests_high="0", tests_low="4"), "cannot be more than the number of tests or CAs you have done (3)"),
    (dict(tests_done="4", tests_high="3", tests_low="2"), "cannot be both above 70% and below 50%"),
])
def test_counts_must_make_sense_together(model_app, model_client, overrides, message):
    signed_in_student(model_client)
    response = post(model_client, **overrides)
    assert response.status_code == 200
    assert message in response.get_data(as_text=True)
    assert count_assessments() == 0


def test_counts_that_equal_the_total_are_accepted(model_app, model_client):
    signed_in_student(model_client)
    assert post(model_client, assignments_assigned="4", assignments_submitted="4",
                tests_done="4", tests_high="4", tests_low="0").status_code == 302
    assert post(model_client, tests_done="4", tests_high="2", tests_low="2").status_code == 302


def test_boundary_values_are_accepted(model_app, model_client):
    signed_in_student(model_client)
    for level, cgpa, count in [("0", "0", "0"), ("6", "5", "1000")]:
        response = post(model_client, attendance_level=level, previous_cgpa=cgpa,
                        assignments_assigned=count, assignments_submitted=count,
                        tests_done=count, tests_high="0", tests_low="0")
        assert response.status_code == 302, (level, cgpa)
    saved = db.session.query(Assessment).order_by(Assessment.id).first()
    assert saved.previous_cgpa == 0.0 and saved.cgpa_unavailable is False


def test_a_made_up_option_value_cannot_be_submitted(model_app, model_client):
    """A hand-crafted request cannot slip in a level that is not on the dropdown."""
    signed_in_student(model_client)
    assert post(model_client, attendance_level="99").status_code == 200
    assert count_assessments() == 0


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
    assert "30.00%" in html and "AT RISK" in html and "flagged" in html


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
