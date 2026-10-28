"""Course records, official-vs-claimed figures, the plan page, advice and attendance prefill."""
import pytest
from sqlalchemy import select

from sarps.extensions import db
from sarps.models import Assessment, Course, CourseRecord
from sarps.services import records as rec
from sarps.services.plan import build_plan
from tests.helpers import (VALID_ASSESSMENT, login, make_department, make_student, make_user)
from sarps.constants import Role

TERM = ("2026/2027", 1)


def make_course(code="CSC 211", units=3, title="Data Structures"):
    course = Course(code=code, title=title, units=units)
    db.session.add(course)
    db.session.commit()
    return course


def make_record(student, course, **values):
    record = CourseRecord(student_id=student.id, course_id=course.id, session=TERM[0], semester=TERM[1], **values)
    db.session.add(record)
    db.session.commit()
    return record


def student_client(client):
    student = make_student("stu@x.com", make_department())
    login(client, "stu@x.com")
    return student


# ---------- who wins ----------
def test_official_beats_claimed_and_claim_alone_is_unverified(app):
    student = make_student("a@x.com")
    record = make_record(student, make_course(), attendance_claimed=90, ca_official=20, ca_claimed=25)
    assert rec.effective(record, "attendance") == (90, "unverified")
    assert rec.effective(record, "ca") == (20, "official")
    assert rec.effective(record, "exam") == (None, None)


def test_discrepancy_uses_a_tolerance(app):
    student = make_student("a@x.com")
    record = make_record(student, make_course(), attendance_official=80, attendance_claimed=80.8,
                         ca_official=20, ca_claimed=22)
    assert not rec.is_disputed(record, "attendance")  # within 1 point
    assert rec.is_disputed(record, "ca")              # 2 marks apart
    assert not rec.is_disputed(record, "exam")        # nothing to compare


def test_attendance_summary_averages_effective_values(app):
    student = make_student("a@x.com")
    make_record(student, make_course("CSC 211"), attendance_official=80)
    make_record(student, make_course("MTH 201", 2), attendance_claimed=60)
    summary = rec.records_attendance(student.id)
    assert summary["value"] == 70 and summary["courses"] == 2
    assert summary["official"] == 1 and summary["unverified"] == 1
    assert rec.records_attendance(make_student("b@x.com").id) is None


# ---------- student entry ----------
def test_student_saves_own_figures_and_sees_them_unverified(client):
    student = student_client(client)
    course = make_course()
    response = client.post("/student/courses", data={"course_id": course.id, "attendance_claimed": "72",
                                                     "ca_claimed": "18"}, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert "Saved your figures for CSC 211" in html and "Unverified" in html
    record = db.session.scalar(select(CourseRecord).where(CourseRecord.student_id == student.id))
    assert (record.attendance_claimed, record.ca_claimed, record.exam_claimed) == (72, 18, None)
    assert record.session == "2026/2027" and record.semester == 1


def test_second_save_updates_only_the_filled_fields(client):
    student = student_client(client)
    course = make_course()
    client.post("/student/courses", data={"course_id": course.id, "ca_claimed": "18"})
    client.post("/student/courses", data={"course_id": course.id, "exam_claimed": "40"})
    records = list(db.session.scalars(select(CourseRecord)))
    assert len(records) == 1 and records[0].ca_claimed == 18 and records[0].exam_claimed == 40


@pytest.mark.parametrize("data", [
    {"ca_claimed": "31"}, {"exam_claimed": "71"}, {"attendance_claimed": "101"}, {"ca_claimed": "-1"},
    {"ca_claimed": "nan"}, {},
])
def test_bad_figures_are_rejected(client, data):
    student_client(client)
    course = make_course()
    client.post("/student/courses", data=dict(data, course_id=course.id))
    assert db.session.scalar(select(CourseRecord)) is None


def test_discrepancy_is_shown_to_the_student(client):
    student = student_client(client)
    make_record(student, make_course(), ca_official=15, ca_claimed=25)
    html = client.get("/student/courses").get_data(as_text=True)
    assert "Differs from your figure: ca" in html and "Official" in html


def test_clear_mine_keeps_official_and_remove_deletes_unofficial(client):
    student = student_client(client)
    official = make_record(student, make_course("CSC 211"), ca_official=15, ca_claimed=25)
    plain = make_record(student, make_course("MTH 201", 2), ca_claimed=10)
    client.post(f"/student/courses/{official.id}/delete")
    client.post(f"/student/courses/{plain.id}/delete")
    db.session.expire_all()
    kept = db.session.get(CourseRecord, official.id)
    assert kept is not None and kept.ca_official == 15 and kept.ca_claimed is None
    assert db.session.get(CourseRecord, plain.id) is None


def test_students_cannot_touch_each_others_records(client):
    student_client(client)
    other = make_student("other@x.com")
    record = make_record(other, make_course(), ca_claimed=10)
    assert client.post(f"/student/courses/{record.id}/delete").status_code == 404


def test_staff_and_visitors_cannot_use_student_course_pages(client):
    assert client.get("/student/courses").status_code in (302, 401)
    make_user(Role.LECTURER, "lec@x.com")
    login(client, "lec@x.com")
    assert client.get("/student/courses").status_code == 403
    assert client.get("/student/plan").status_code == 403


# ---------- course catalogue (administrator) ----------
def admin_client(client):
    make_user(Role.ADMIN, "admin@x.com")
    login(client, "admin@x.com")


def test_admin_manages_courses(client):
    admin_client(client)
    data = {"code": " csc  211 ", "title": "Data Structures", "units": "3", "department_id": "0"}
    assert client.post("/admin/courses", data=data).status_code == 302
    course = db.session.scalar(select(Course))
    assert course.code == "CSC 211" and course.units == 3
    assert "already exists" in client.post("/admin/courses", data=data).get_data(as_text=True)
    assert client.post("/admin/courses", data=dict(data, code="CSC 999", units="9")).status_code == 200
    assert db.session.query(Course).count() == 1


def test_course_with_records_cannot_be_deleted_and_students_cannot_add_courses(client):
    admin_client(client)
    student = make_student("s@x.com")
    course = make_course()
    make_record(student, course, ca_claimed=10)
    client.post(f"/admin/courses/{course.id}/delete")
    assert db.session.get(Course, course.id) is not None
    client.get("/logout")
    client2 = client.application.test_client()
    login(client2, "s@x.com")
    assert client2.post("/admin/courses", data={"code": "X 1", "title": "Hack", "units": "1"}).status_code == 403


# ---------- plan ----------
def test_plan_scenarios_match_hand_calculation(client):
    student = student_client(client)
    make_record(student, make_course("CSC 211", 3), ca_claimed=20)
    make_record(student, make_course("MTH 201", 2), ca_claimed=15)
    plan = build_plan(student.id)
    best = plan["scenarios"][-1]  # 70/70 everywhere: 90 = A and 85 = A, so GPA 5.0
    assert best["exam"] == 70 and best["gpa"] == 5.0
    html = client.get("/student/plan").get_data(as_text=True)
    assert "Course by course" in html and "Your target" not in html


def test_plan_final_result_when_every_exam_is_in(client):
    student = student_client(client)
    make_record(student, make_course("CSC 211", 3), ca_official=25, exam_official=50)   # 75 A
    make_record(student, make_course("MTH 201", 2), ca_official=20, exam_official=30)   # 50 C
    plan = build_plan(student.id)
    assert plan["complete"] and plan["semester_gpa"] == 4.2          # (15 + 6) / 5


def test_plan_page_is_read_only_now(client):
    student_client(client)
    assert client.get("/student/plan").status_code == 200
    assert client.post("/student/plan", data={"target_cgpa": "4"}).status_code == 405


def test_missing_ca_is_reported_not_guessed(client):
    student = student_client(client)
    make_record(student, make_course(), attendance_claimed=80)
    plan = build_plan(student.id)
    assert plan["missing_ca"] == ["CSC 211"] and plan["scenarios"] == []


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
    make_record(student, make_course(), ca_official=10)
    response = submit(model_client, attendance_level="1", assignments_assigned="5", assignments_submitted="1",
                      previous_cgpa="1.8")
    page = model_client.get(response.headers["Location"]).get_data(as_text=True)
    assert "What this means for you" in page and "How much to trust this" in page
    assert "below the commonly required level" in page and "Catch up on assignments" in page
    assert "CSC 211" in page            # per-course advice from the plan


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
    assert "not on UNN students" in html and "Grade points A=5" in html and "arts.unn.edu.ng" in html
