"""Advice rules built from the student's own answers, legacy rows and the database upgrade."""
from sqlalchemy import create_engine, inspect, text

from sarps.extensions import db
from sarps.models import Assessment
from sarps.schema import upgrade_schema
from sarps.services.advice import build_advice
from tests.helpers import login, make_assessment, make_department, make_student


def titles(assessment, drivers=(), unused=()):
    return [(i["kind"], i["title"]) for i in build_advice(assessment, list(drivers), None, unused)]


def make(**changes):
    student = make_student(f"s{Assessment.query.count()}@x.com")
    assessment = make_assessment(student, prob=30)
    for key, value in changes.items():
        setattr(assessment, key, value)
    return assessment


def test_low_attendance_is_urgent_and_borderline_is_important(app):
    assert ("urgent", "Attendance is below the commonly required level") in titles(make(attendance_level=3))
    assert ("important", "Attendance may be close to the commonly required level") in titles(make(attendance_level=4))
    low = [t for _, t in titles(make(attendance_level=6))]
    assert not any("Attendance is below" in t or "close to the commonly" in t for t in low)


def test_assignment_advice_uses_the_students_counts_and_never_divides_by_zero(app):
    advice = build_advice(make(assignments_assigned=5, assignments_submitted=1), [])
    assert any("1 of 5 assignments" in i["body"] for i in advice)
    none_assigned = titles(make(assignments_assigned=0, assignments_submitted=0))
    assert not any("assignments" in t.lower() for _, t in none_assigned)


def test_test_perception_advice(app):
    assert ("important", "Your tests and CAs are worrying you") in titles(make(tests_done=4, tests_high=0, tests_low=3))
    assert ("good", "Your tests and CAs are going well") in titles(make(tests_done=4, tests_high=3, tests_low=0))
    assert not any("tests" in t.lower() for _, t in titles(make(tests_done=0, tests_high=0, tests_low=0)))


def test_money_trouble_gets_a_kind_pointer_not_blame(app):
    advice = build_advice(make(financial_impact=5), [])
    item = next(i for i in advice if i["title"].startswith("Money is getting in the way"))
    assert item["kind"] == "info" and "adviser" in item["body"]
    assert not any(i["title"].startswith("Money") for i in build_advice(make(financial_impact=2), []))


def test_unused_inputs_are_declared_in_the_advice(app):
    advice = build_advice(make(), [], None, ["assignment_submission_rate", "financial_impact"])
    note = next(i for i in advice if i["title"] == "Some of your answers do not change the score")
    assert "assignment submission" in note["body"] and "how often money affects participation" in note["body"]


def test_drivers_are_described_in_the_dropdown_wording(app):
    drivers = [{"name": "attendance_level", "value": 1.0, "typical": 5.0, "contribution": -1.2}]
    body = " ".join(i["body"] for i in build_advice(make(), drivers))
    assert "Very Rarely (1–20%)" in body and "Most of the Time (81–95%)" in body


# ---------- results made before the redesign still open ----------
def test_old_style_assessment_still_displays(model_client):
    student = make_student("old@x.com", make_department())
    old = Assessment(student_id=student.id, attendance_pct=80, assignment_completion_pct=70, previous_cgpa=3.1,
                     financial_capability="low", study_hours_per_week=9, prob_not_at_risk=40, risk_label="At Risk",
                     is_flagged=True, model_version="old", consent_given=True, consent_version="v1")
    db.session.add(old)
    db.session.commit()
    login(model_client, "old@x.com")
    for url in (f"/student/assessments/{old.id}", "/student/", "/student/history"):
        response = model_client.get(url)
        assert response.status_code == 200, url
    assert "older inputs" in model_client.get(f"/student/assessments/{old.id}").get_data(as_text=True)


# ---------- upgrading an existing database ----------
OLD_TABLE = """CREATE TABLE assessments (
    id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL, created_at DATETIME NOT NULL,
    attendance_pct FLOAT NOT NULL, assignment_completion_pct FLOAT NOT NULL, previous_cgpa FLOAT,
    cgpa_unavailable BOOLEAN NOT NULL, financial_capability VARCHAR(10), study_hours_per_week FLOAT,
    prob_not_at_risk FLOAT NOT NULL, risk_label VARCHAR(20) NOT NULL, is_flagged BOOLEAN NOT NULL,
    model_version VARCHAR(80) NOT NULL, consent_given BOOLEAN NOT NULL, consent_version VARCHAR(20) NOT NULL)"""


def test_upgrade_adds_new_columns_keeps_old_rows_and_is_repeatable():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text(OLD_TABLE))
        connection.execute(text(
            "INSERT INTO assessments VALUES (1, 7, '2026-01-01', 80, 70, 3.0, 0, 'low', 9, 40, 'At Risk', 1, 'old', 1, 'v1')"))
    first = upgrade_schema(engine)
    columns = {c["name"] for c in inspect(engine).get_columns("assessments")}
    for name in ("attendance_level", "assignments_assigned", "assignments_submitted", "tests_done", "tests_high",
                 "tests_low", "study_hours_level", "financial_comfort", "financial_impact"):
        assert name in columns and f"added assessments.{name}" in first
    with engine.connect() as connection:
        row = connection.execute(text("SELECT attendance_pct, attendance_level, risk_label FROM assessments")).one()
    assert row == (80, None, "At Risk")                       # the old row survived, new columns empty
    assert not any(line.startswith("added") for line in upgrade_schema(engine))   # second run changes nothing
