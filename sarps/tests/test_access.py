"""Who can see whose assessments. This is the most important test file for privacy."""
from sqlalchemy import select

from sarps.constants import Role
from sarps.extensions import db
from sarps.models import StaffAssignment, User
from sarps.services.access import (can_view_student, staff_who_can_view, visible_assessments,
                                   visible_students)
from tests.helpers import (assign, login, make_assessment, make_department, make_student,
                           make_user)


def build_world():
    """Two departments, four students, one of each staff role."""
    dept_a, dept_b = make_department("Dept A"), make_department("Dept B")
    w = {"dept_a": dept_a, "dept_b": dept_b}
    w["s1"] = make_student("s1@x.com", dept_a, name="Student One")
    w["s2"] = make_student("s2@x.com", dept_a, name="Student Two")
    w["s3"] = make_student("s3@x.com", dept_b, name="Student Three")
    w["s4"] = make_student("s4@x.com", None, name="Student Nodept")
    w["adviser"] = make_user(Role.ADVISER, "adv@x.com", name="Adviser Ann")
    w["lecturer"] = make_user(Role.LECTURER, "lec@x.com", name="Lecturer Len")
    w["hod_a"] = make_user(Role.HOD, "hoda@x.com", name="Head A", department=dept_a)
    w["hod_b"] = make_user(Role.HOD, "hodb@x.com", name="Head B", department=dept_b)
    w["hod_none"] = make_user(Role.HOD, "hodn@x.com", name="Head Nowhere")
    w["admin"] = make_user(Role.ADMIN, "admin@x.com")
    assign(w["adviser"], w["s1"])
    assign(w["lecturer"], w["s2"])
    for key in ("s1", "s2", "s3", "s4"):
        w["a_" + key] = make_assessment(w[key], prob=40 if key == "s1" else 80)
    return w


def students_seen_by(user):
    return {s.email for s in db.session.scalars(visible_students(user))}


def assessments_seen_by(user):
    return {a.id for a in db.session.scalars(visible_assessments(user))}


# ---------- the rules themselves ----------
def test_student_sees_only_self(app):
    w = build_world()
    assert students_seen_by(w["s1"]) == {"s1@x.com"}
    assert assessments_seen_by(w["s1"]) == {w["a_s1"].id}


def test_adviser_sees_only_assigned_students(app):
    w = build_world()
    assert students_seen_by(w["adviser"]) == {"s1@x.com"}
    assert assessments_seen_by(w["adviser"]) == {w["a_s1"].id}


def test_lecturer_sees_only_assigned_students(app):
    w = build_world()
    assert students_seen_by(w["lecturer"]) == {"s2@x.com"}


def test_head_of_department_sees_own_department_only(app):
    w = build_world()
    assert students_seen_by(w["hod_a"]) == {"s1@x.com", "s2@x.com"}
    assert students_seen_by(w["hod_b"]) == {"s3@x.com"}


def test_head_without_department_sees_nobody(app):
    # Guards against the NULL = NULL trap: a student with no department must NOT match.
    w = build_world()
    assert students_seen_by(w["hod_none"]) == set()
    assert assessments_seen_by(w["hod_none"]) == set()
    assert not can_view_student(w["hod_none"], w["s4"].id)


def test_administrator_sees_no_assessments(app):
    w = build_world()
    assert students_seen_by(w["admin"]) == set()
    assert assessments_seen_by(w["admin"]) == set()


def test_unassigning_removes_access(app):
    w = build_world()
    db.session.query(StaffAssignment).delete()
    db.session.commit()
    assert students_seen_by(w["adviser"]) == set()
    assert students_seen_by(w["lecturer"]) == set()
    assert students_seen_by(w["hod_a"]) == {"s1@x.com", "s2@x.com"}  # department access is automatic


def test_staff_cannot_be_viewed_as_students(app):
    w = build_world()
    assert not can_view_student(w["hod_a"], w["adviser"].id)


def test_staff_who_can_view_lists_assigned_staff_and_department_head(app):
    w = build_world()
    names = {u.full_name for u in staff_who_can_view(w["s1"])}
    assert names == {"Adviser Ann", "Head A"}
    w["adviser"].active = False
    db.session.commit()
    assert {u.full_name for u in staff_who_can_view(w["s1"])} == {"Head A"}
    assert staff_who_can_view(w["s4"]) == []


# ---------- the same rules through the website ----------
def test_student_cannot_open_another_students_result(app, client):
    w = build_world()
    login(client, "s2@x.com")
    assert client.get(f"/student/assessments/{w['a_s2'].id}").status_code == 200
    assert client.get(f"/student/assessments/{w['a_s1'].id}").status_code == 404


def test_student_history_lists_only_own(app, client):
    w = build_world()
    make_assessment(w["s1"], prob=61.23)
    login(client, "s2@x.com")
    html = client.get("/student/history").get_data(as_text=True)
    assert "80.00%" in html and "61.23%" not in html and "40.00%" not in html


def test_adviser_pages(app, client):
    w = build_world()
    login(client, "adv@x.com")
    assert client.get(f"/staff/students/{w['s1'].id}").status_code == 200
    assert client.get(f"/staff/students/{w['s2'].id}").status_code == 404
    assert client.get(f"/staff/students/{w['s3'].id}").status_code == 404
    assert client.get(f"/staff/assessments/{w['a_s1'].id}").status_code == 200
    assert client.get(f"/staff/assessments/{w['a_s2'].id}").status_code == 404
    html = client.get("/staff/").get_data(as_text=True)
    assert "Student One" in html
    for hidden in ("Student Two", "Student Three", "Student Nodept"):
        assert hidden not in html


def test_head_of_department_pages(app, client):
    w = build_world()
    login(client, "hoda@x.com")
    html = client.get("/staff/").get_data(as_text=True)
    assert "Student One" in html and "Student Two" in html
    assert "Student Three" not in html and "Student Nodept" not in html
    assert client.get(f"/staff/assessments/{w['a_s3'].id}").status_code == 404


def test_administrator_cannot_open_any_assessment_page(app, client):
    w = build_world()
    login(client, "admin@x.com")
    assert client.get(f"/staff/assessments/{w['a_s1'].id}").status_code == 403
    assert client.get(f"/staff/students/{w['s1'].id}").status_code == 403
    assert client.get(f"/student/assessments/{w['a_s1'].id}").status_code == 403


def test_flagged_list_shows_only_visible_at_risk_students(app, client):
    w = build_world()
    login(client, "hoda@x.com")
    html = client.get("/staff/?filter=flagged").get_data(as_text=True)
    assert "Student One" in html          # prob 40 -> At Risk -> flagged
    assert "Student Two" not in html      # prob 80 -> Not at Risk


def test_dashboard_counts_use_latest_assessment_only(app, client):
    w = build_world()
    make_assessment(w["s1"], prob=90)  # s1 improves; the old At Risk result is no longer the latest
    login(client, "hoda@x.com")
    html = client.get("/staff/?filter=flagged").get_data(as_text=True)
    assert "Student One" not in html


def test_search_is_limited_to_visible_students(app, client):
    build_world()
    login(client, "adv@x.com")
    html = client.get("/staff/?q=Student").get_data(as_text=True)
    assert "Student One" in html and "Student Two" not in html
    # wildcard characters are treated as plain text, not as "match everything"
    html = client.get("/staff/?q=%25").get_data(as_text=True)
    assert "Student One" not in html


def test_student_can_see_which_staff_get_flagged_results(app, client):
    w = build_world()
    login(client, "s1@x.com")
    html = client.get(f"/student/assessments/{w['a_s1'].id}").get_data(as_text=True)
    assert "flagged" in html and "Adviser Ann" in html and "Head A" in html
    login(client, "s1@x.com")  # already signed in, harmless
    db.session.query(StaffAssignment).delete()
    db.session.delete(w["hod_a"])
    db.session.commit()
    html = client.get(f"/student/assessments/{w['a_s1'].id}").get_data(as_text=True)
    assert "No staff are currently linked" in html
