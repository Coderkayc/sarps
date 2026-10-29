"""
"""
from sqlalchemy import false, select

from sarps.constants import Role
from sarps.extensions import db
from sarps.models import Assessment, StaffAssignment, User


def visible_student_ids(user):
    """"""
    if user.role == Role.STUDENT:
        return select(User.id).where(User.id == user.id)
    if user.role in (Role.ADVISER, Role.LECTURER):
        return select(StaffAssignment.student_id).where(StaffAssignment.staff_id == user.id)
    if user.role == Role.HOD:
        if user.department_id is None:
            return select(User.id).where(false())
        return select(User.id).where(
            User.role == Role.STUDENT, User.department_id == user.department_id
        )
    return select(User.id).where(false())


def visible_students(user):
    """"""
    return select(User).where(
        User.role == Role.STUDENT, User.id.in_(visible_student_ids(user))
    )


def visible_assessments(user):
    """"""
    return select(Assessment).where(Assessment.student_id.in_(visible_student_ids(user)))


def latest_assessment_ids(user):
    """"""
    return (
        select(db.func.max(Assessment.id))
        .where(Assessment.student_id.in_(visible_student_ids(user)))
        .group_by(Assessment.student_id)
    )


def can_view_student(user, student_id):
    query = select(User.id).where(
        User.id == student_id,
        User.role == Role.STUDENT,
        User.id.in_(visible_student_ids(user)),
    )
    return db.session.scalar(query) is not None


def get_visible_assessment(user, assessment_id):
    """"""
    return db.session.scalar(visible_assessments(user).where(Assessment.id == assessment_id))


def staff_who_can_view(student):
    """"""
    assigned = select(StaffAssignment.staff_id).where(StaffAssignment.student_id == student.id)
    conditions = [User.id.in_(assigned)]
    if student.department_id is not None:
        conditions.append(
            (User.role == Role.HOD) & (User.department_id == student.department_id)
        )
    query = select(User).where(User.active.is_(True), db.or_(*conditions)).order_by(User.full_name)
    return list(db.session.scalars(query))
