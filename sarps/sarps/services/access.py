"""Who may see which assessments. Every role rule is in this one file.

    Student               -> only their own
    Academic adviser      -> students the administrator assigned to them
    Lecturer              -> students the administrator assigned to them
    Head of Department    -> every student in their own department
    Administrator         -> no assessments at all (manages accounts only)
"""
from sqlalchemy import false, select

from sarps.constants import Role
from sarps.extensions import db
from sarps.models import Assessment, StaffAssignment, User


def visible_student_ids(user):
    """A query returning the ids of students whose assessments `user` may see."""
    if user.role == Role.STUDENT:
        return select(User.id).where(User.id == user.id)
    if user.role in (Role.ADVISER, Role.LECTURER):
        return select(StaffAssignment.student_id).where(StaffAssignment.staff_id == user.id)
    if user.role == Role.HOD:
        # A head with no department set sees nobody. (Comparing to NULL would
        # otherwise wrongly match every student without a department.)
        if user.department_id is None:
            return select(User.id).where(false())
        return select(User.id).where(
            User.role == Role.STUDENT, User.department_id == user.department_id
        )
    return select(User.id).where(false())


def visible_students(user):
    """A query returning the student User rows `user` may see."""
    return select(User).where(
        User.role == Role.STUDENT, User.id.in_(visible_student_ids(user))
    )


def visible_assessments(user):
    """A query returning the Assessment rows `user` may see."""
    return select(Assessment).where(Assessment.student_id.in_(visible_student_ids(user)))


def latest_assessment_ids(user):
    """A query returning the id of each visible student's most recent assessment."""
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
    """The assessment if `user` may see it, otherwise None."""
    return db.session.scalar(visible_assessments(user).where(Assessment.id == assessment_id))


def staff_who_can_view(student):
    """Staff accounts currently authorised to see this student's assessments."""
    assigned = select(StaffAssignment.staff_id).where(StaffAssignment.student_id == student.id)
    conditions = [User.id.in_(assigned)]
    if student.department_id is not None:
        conditions.append(
            (User.role == Role.HOD) & (User.department_id == student.department_id)
        )
    query = select(User).where(User.active.is_(True), db.or_(*conditions)).order_by(User.full_name)
    return list(db.session.scalars(query))
