"""Administrator functions: accounts, departments, assignments."""
from sqlalchemy import select

from sarps.constants import Role
from sarps.extensions import db
from sarps.models import Department, StaffAssignment, User
from tests.helpers import (PASSWORD, assign, login, make_department, make_student, make_user)


def admin_client(client):
    admin = make_user(Role.ADMIN, "admin@x.com", name="The Admin")
    login(client, "admin@x.com")
    return admin


def staff_form(dept_id=0, **overrides):
    data = {"full_name": "New Adviser", "email": "New.Adviser@x.com", "role": Role.ADVISER,
            "department_id": str(dept_id), "password": "Temporary123!"}
    data.update(overrides)
    return data


def test_admin_creates_staff_account(client):
    admin_client(client)
    response = client.post("/admin/users", data=staff_form())
    assert response.status_code == 302
    staff = db.session.scalar(select(User).where(User.email == "new.adviser@x.com"))
    assert staff.role == Role.ADVISER and staff.active
    assert staff.password_hash != "Temporary123!" and staff.check_password("Temporary123!")


def test_new_staff_can_sign_in(client):
    admin_client(client)
    client.post("/admin/users", data=staff_form())
    client.post("/logout")
    assert login(client, "new.adviser@x.com", "Temporary123!").headers["Location"].endswith("/staff/")


def test_head_of_department_needs_a_department(client):
    admin_client(client)
    response = client.post("/admin/users", data=staff_form(role=Role.HOD))
    assert "must be linked to a department" in response.get_data(as_text=True)
    dept = make_department()
    assert client.post("/admin/users", data=staff_form(role=Role.HOD, dept_id=dept.id,
                                                       department_id=str(dept.id))).status_code == 302
    hod = db.session.scalar(select(User).where(User.role == Role.HOD))
    assert hod.department_id == dept.id


def test_admin_cannot_create_students_or_other_admins_here(client):
    admin_client(client)
    for role in (Role.STUDENT, Role.ADMIN, "superuser"):
        client.post("/admin/users", data=staff_form(role=role))
    assert db.session.scalar(select(User).where(User.email == "new.adviser@x.com")) is None


def test_duplicate_staff_email_and_weak_password_rejected(client):
    admin_client(client)
    assert "already exists" in client.post("/admin/users", data=staff_form(email="admin@x.com")).get_data(as_text=True)
    assert "at least 8" in client.post("/admin/users", data=staff_form(password="abc")).get_data(as_text=True)


def test_non_admins_cannot_use_admin_actions(client):
    student = make_student("s@x.com", make_department())
    login(client, "s@x.com")
    assert client.post("/admin/users", data=staff_form()).status_code == 403
    assert client.post(f"/admin/users/{student.id}/toggle").status_code == 403
    assert client.post("/admin/departments", data={"name": "Hack"}).status_code == 403
    assert client.post("/admin/assignments", data={"staff_id": 1, "student_id": 1}).status_code == 403
    assert db.session.scalar(select(User).where(User.email == "new.adviser@x.com")) is None


def test_departments_can_be_added_but_not_duplicated(client):
    admin_client(client)
    assert client.post("/admin/departments", data={"name": "Physics"}).status_code == 302
    assert "already exists" in client.post("/admin/departments", data={"name": "Physics"}).get_data(as_text=True)
    assert db.session.query(Department).count() == 1


def test_assignment_lifecycle(client):
    admin_client(client)
    dept = make_department()
    student = make_student("s@x.com", dept)
    adviser = make_user(Role.ADVISER, "adv@x.com")
    data = {"staff_id": str(adviser.id), "student_id": str(student.id)}
    assert client.post("/admin/assignments", data=data).status_code == 302
    assert db.session.query(StaffAssignment).count() == 1
    client.post("/admin/assignments", data=data)  # duplicate
    assert db.session.query(StaffAssignment).count() == 1
    row = db.session.scalar(select(StaffAssignment))
    assert client.post(f"/admin/assignments/{row.id}/delete").status_code == 302
    assert db.session.query(StaffAssignment).count() == 0


def test_cannot_assign_a_student_as_staff_or_staff_as_student(client):
    admin_client(client)
    dept = make_department()
    student = make_student("s@x.com", dept)
    adviser = make_user(Role.ADVISER, "adv@x.com")
    hod = make_user(Role.HOD, "hod@x.com", department=dept)
    for staff_id, student_id in [(student.id, student.id), (adviser.id, adviser.id), (hod.id, student.id)]:
        client.post("/admin/assignments", data={"staff_id": str(staff_id), "student_id": str(student_id)})
    assert db.session.query(StaffAssignment).count() == 0


def test_deactivating_blocks_sign_in_and_reactivating_restores_it(client):
    admin_client(client)
    student = make_student("s@x.com", make_department())
    client.post(f"/admin/users/{student.id}/toggle")
    other = client.application.test_client()
    assert "deactivated" in login(other, "s@x.com").get_data(as_text=True)
    client.post(f"/admin/users/{student.id}/toggle")
    assert login(other, "s@x.com").status_code == 302


def test_admin_cannot_deactivate_themselves(client):
    admin = admin_client(client)
    client.post(f"/admin/users/{admin.id}/toggle")
    assert db.session.get(User, admin.id).active is True


def test_admin_pages_show_model_status(app, client):
    admin_client(client)
    assert "Not installed" in client.get("/admin/").get_data(as_text=True)


def test_admin_pages_show_installed_model(model_app, model_client):
    admin_client(model_client)
    html = model_client.get("/admin/").get_data(as_text=True)
    assert "Installed" in html and "At Risk recall" in html


def test_admin_overview_and_lists_load(client):
    admin_client(client)
    make_student("s@x.com", make_department())
    for path in ["/admin/", "/admin/users", "/admin/users?role=student", "/admin/departments", "/admin/assignments"]:
        assert client.get(path).status_code == 200, path
