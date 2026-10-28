"""The assessment form, the advice on the result page and the assumptions page."""
from tests.helpers import VALID_ASSESSMENT, login, make_department, make_student


def student_client(client):
    student = make_student("stu@x.com", make_department())
    login(client, "stu@x.com")
    return student


# ---------- the assessment form ----------
def submit(client, **overrides):
    data = dict(VALID_ASSESSMENT)
    data.update(overrides)
    return client.post("/student/assess", data=data)


def test_attendance_is_a_dropdown_not_a_typed_percentage(model_client):
    student_client(model_client)
    html = model_client.get("/student/assess").get_data(as_text=True)
    assert '<select' in html and 'id="attendance_level"' in html
    assert 'name="attendance_pct"' not in html


def test_assessment_form_has_no_target_cgpa_question(model_client):
    student_client(model_client)
    html = model_client.get("/student/assess").get_data(as_text=True)
    assert "aiming for" not in html and 'name="target_cgpa"' not in html


# ---------- advice ----------
def test_result_page_explains_and_advises(model_client):
    student = student_client(model_client)
    response = submit(model_client, attendance_level="1", assignments_assigned="5", assignments_submitted="1",
                      previous_cgpa="1.8")
    page = model_client.get(response.headers["Location"]).get_data(as_text=True)
    assert "What this means for you" in page and "How much to trust this" in page
    assert "below the commonly required level" in page and "Catch up on assignments" in page


def test_explain_returns_signed_contributions_for_the_logistic_model(model_app):
    from ml.features import features_from_inputs
    service = model_app.extensions["prediction"]
    good = service.explain(features_from_inputs(6, 10, 10, 5, 4, 0, 8, 5, 1, 4.8))
    bad = service.explain(features_from_inputs(0, 10, 2, 5, 0, 4, 1, 1, 5, 1.2))
    names = {d["name"] for d in good}
    assert {"attendance_level", "previous_cgpa"} <= names
    assert all(d["contribution"] > 0 for d in good if d["name"] == "attendance_level")
    assert all(d["contribution"] < 0 for d in bad if d["name"] == "attendance_level")
    blank = service.explain(features_from_inputs(3, 0, 0, 0, 0, 0, 3, 3, 3, None))
    assert "previous_cgpa" not in {d["name"] for d in blank}
    assert "assignment_submission_rate" not in {d["name"] for d in blank}   # nothing assigned: says nothing


def test_advice_never_blames_financial_answers(model_app):
    from sarps.services.advice import build_advice
    from tests.helpers import make_assessment
    student = make_student("adv@x.com")
    assessment = make_assessment(student, prob=30)
    drivers = [{"name": "financial_comfort", "value": 1, "typical": 3, "contribution": -0.9},
               {"name": "financial_impact", "value": 5, "typical": 3, "contribution": -0.9}]
    text = " ".join(i["title"] + i["body"] for i in build_advice(assessment, drivers))
    assert "financial" not in text.lower()


def test_assumptions_page_is_public_and_lists_the_assumptions(client):
    html = client.get("/assumptions").get_data(as_text=True)
    assert "Rules and assumptions" in html and "Assumed, not confirmed" in html
    assert "has not been confirmed for UNN" in html


def test_courses_and_plan_pages_are_gone(client):
    student_client(client)
    for url in ("/student/courses", "/student/plan"):
        assert client.get(url).status_code == 404
    html = client.get("/student/assess").get_data(as_text=True)
    assert "My courses" not in html and ">Plan<" not in html
