"""Registration, sign in, sign out and the role guard."""
import pytest
from sqlalchemy import select

from sarps.constants import Role
from sarps.extensions import db
from sarps.models import User
from tests.helpers import PASSWORD, login, make_department, make_user, make_student

REGISTRATION = {"full_name": "Ada Obi", "matric_number": "csc/2020/001", "email": "Ada@Example.com",
                "password": PASSWORD, "confirm": PASSWORD}


def register(client, department, **overrides):
    data = dict(REGISTRATION, department_id=str(department.id), **overrides)
    return client.post("/register", data=data)


# ---------- registration ----------
def test_student_can_register(client):
    dept = make_department()
    response = register(client, dept)
    assert response.status_code == 302
    student = db.session.scalar(select(User).where(User.email == "ada@example.com"))
    assert student.role == Role.STUDENT
    assert student.matric_number == "CSC/2020/001"
    assert student.password_hash != PASSWORD  # stored hashed, never as plain text
    assert student.check_password(PASSWORD)


def test_registration_cannot_choose_a_role(client):
    dept = make_department()
    register(client, dept, role=Role.ADMIN)
    student = db.session.scalar(select(User).where(User.email == "ada@example.com"))
    assert student.role == Role.STUDENT


def test_registration_closed_without_departments(client):
    response = client.get("/register")
    assert response.status_code == 503
    assert "not open yet" in response.get_data(as_text=True)


def test_duplicate_email_rejected(client):
    dept = make_department()
    make_student("ada@example.com", dept)
    response = register(client, dept)
    assert "already exists" in response.get_data(as_text=True)


def test_duplicate_matric_rejected(client):
    dept = make_department()
    make_user(Role.STUDENT, "other@example.com", department=dept, matric="CSC/2020/001")
    response = register(client, dept)
    assert "already registered" in response.get_data(as_text=True)


def test_short_password_and_mismatch_rejected(client):
    dept = make_department()
    assert "at least 8" in register(client, dept, password="short", confirm="short").get_data(as_text=True)
    assert "do not match" in register(client, dept, confirm="different123").get_data(as_text=True)
    assert db.session.scalar(select(User).where(User.email == "ada@example.com")) is None


def test_unknown_department_rejected(client):
    make_department()
    response = client.post("/register", data=dict(REGISTRATION, department_id="999"))
    assert response.status_code == 200
    assert db.session.scalar(select(User).where(User.email == "ada@example.com")) is None


# ---------- sign in ----------
@pytest.mark.parametrize("role, landing", [
    (Role.STUDENT, "/student/"),
    (Role.ADVISER, "/staff/"),
    (Role.LECTURER, "/staff/"),
    (Role.HOD, "/staff/"),
    (Role.ADMIN, "/admin/"),
])
def test_each_role_lands_on_its_own_dashboard(client, role, landing):
    make_user(role, "user@example.com")
    response = login(client, "user@example.com")
    assert response.status_code == 302
    assert response.headers["Location"].endswith(landing)


def test_wrong_password_and_unknown_email_get_same_message(client):
    make_user(Role.STUDENT, "real@example.com")
    wrong = login(client, "real@example.com", "badpassword").get_data(as_text=True)
    unknown = login(client, "nobody@example.com").get_data(as_text=True)
    assert "Incorrect email or password" in wrong
    assert "Incorrect email or password" in unknown


def test_email_login_is_case_insensitive(client):
    make_user(Role.STUDENT, "real@example.com")
    assert login(client, "REAL@Example.com").status_code == 302


def test_deactivated_account_cannot_sign_in(client):
    make_user(Role.STUDENT, "gone@example.com", active=False)
    response = login(client, "gone@example.com")
    assert response.status_code == 200
    assert "deactivated" in response.get_data(as_text=True)
    assert client.get("/student/").status_code == 302


def test_deactivation_ends_an_existing_session(client):
    user = make_user(Role.STUDENT, "live@example.com")
    login(client, "live@example.com")
    assert client.get("/student/").status_code == 200
    user.active = False
    db.session.commit()
    assert client.get("/student/").status_code == 302


def test_redirect_after_login_only_to_same_site(client):
    make_user(Role.STUDENT, "s@example.com")
    response = client.post("/login?next=//evil.example.com", data={"email": "s@example.com", "password": PASSWORD})
    assert response.headers["Location"].endswith("/student/")
    client.post("/logout")
    response = client.post("/login?next=/student/history", data={"email": "s@example.com", "password": PASSWORD})
    assert response.headers["Location"].endswith("/student/history")


def test_logout_ends_session(client):
    make_user(Role.STUDENT, "s@example.com")
    login(client, "s@example.com")
    assert client.get("/student/").status_code == 200
    client.post("/logout")
    response = client.get("/student/")
    assert response.status_code == 302 and "/login" in response.headers["Location"]


# ---------- role guard ----------
def test_pages_need_sign_in(client):
    for path in ["/student/", "/student/assess", "/student/history", "/staff/", "/admin/", "/admin/users", "/dashboard"]:
        response = client.get(path)
        assert response.status_code == 302 and "/login" in response.headers["Location"], path


@pytest.mark.parametrize("role, forbidden", [
    (Role.STUDENT, ["/staff/", "/admin/", "/admin/users", "/admin/assignments"]),
    (Role.ADVISER, ["/student/", "/student/assess", "/admin/"]),
    (Role.LECTURER, ["/student/", "/admin/users"]),
    (Role.HOD, ["/student/", "/admin/departments"]),
    (Role.ADMIN, ["/student/", "/student/assess", "/staff/"]),
])
def test_roles_cannot_open_other_roles_pages(client, role, forbidden):
    make_user(role, "user@example.com")
    login(client, "user@example.com")
    for path in forbidden:
        assert client.get(path).status_code == 403, path
