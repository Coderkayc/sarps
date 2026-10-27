"""Small functions that build test data."""
from sarps.constants import Role
from sarps.extensions import db
from sarps.models import Assessment, Department, StaffAssignment, User

PASSWORD = "Password123!"

VALID_ASSESSMENT = {
    "attendance_level": "4",
    "assignments_assigned": "5",
    "assignments_submitted": "4",
    "tests_done": "4",
    "tests_high": "1",
    "tests_low": "1",
    "study_hours_level": "3",
    "financial_comfort": "3",
    "financial_impact": "2",
    "has_cgpa": "yes",
    "previous_cgpa": "3.5",
    "consent": "y",
}


def make_department(name="Computer Science"):
    dept = Department(name=name)
    db.session.add(dept)
    db.session.commit()
    return dept


def make_user(role, email, name=None, department=None, matric=None, active=True):
    user = User(full_name=name or email.split("@")[0].title(), email=email, role=role,
                department_id=department.id if department else None,
                matric_number=matric, active=active)
    user.set_password(PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user


def make_student(email, department=None, name=None):
    return make_user(Role.STUDENT, email, name=name, department=department,
                     matric=f"M-{email.split('@')[0].upper()}")


def assign(staff, student):
    db.session.add(StaffAssignment(staff_id=staff.id, student_id=student.id))
    db.session.commit()


def make_assessment(student, prob=72.5, label=None):
    label = label or ("Not at Risk" if prob > 50 else "At Risk")
    assessment = Assessment(
        student_id=student.id, attendance_level=4, assignments_assigned=5, assignments_submitted=4,
        tests_done=4, tests_high=1, tests_low=1, study_hours_level=3, financial_comfort=3, financial_impact=2,
        previous_cgpa=3.5,
        prob_not_at_risk=prob, risk_label=label, is_flagged=(label == "At Risk"),
        model_version="test", consent_given=True, consent_version="v1")
    db.session.add(assessment)
    db.session.commit()
    return assessment


def login(client, email, password=PASSWORD, **kwargs):
    return client.post("/login", data={"email": email, "password": password}, **kwargs)


def count_assessments():
    return db.session.query(Assessment).count()
