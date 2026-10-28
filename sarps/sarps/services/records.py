"""Course records: which value counts, and where it came from.

Rule (stated on the Assumptions page): an OFFICIAL value from staff always counts.
If there is none, the student's own (claimed) value is used and marked UNVERIFIED.
If both exist and differ, the record is shown as a DISCREPANCY for staff to resolve.
"""
from flask import current_app
from sqlalchemy import select

from sarps import unn
from sarps.extensions import db
from sarps.models import Course, CourseRecord

# How far apart two values may be before we call it a discrepancy.
TOLERANCE = {"attendance": 1.0, "ca": 0.5, "exam": 0.5}
OFFICIAL, UNVERIFIED = "official", "unverified"


def current_term():
    config = current_app.config
    return config.get("CURRENT_SESSION", "2026/2027"), int(config.get("CURRENT_SEMESTER", 1))


def effective(record, field):
    """(value, status) for 'attendance', 'ca' or 'exam'. status is None when nothing is recorded."""
    official = getattr(record, f"{field}_official")
    if official is not None:
        return official, OFFICIAL
    claimed = getattr(record, f"{field}_claimed")
    if claimed is not None:
        return claimed, UNVERIFIED
    return None, None


def is_disputed(record, field):
    official = getattr(record, f"{field}_official")
    claimed = getattr(record, f"{field}_claimed")
    if official is None or claimed is None:
        return False
    return abs(official - claimed) > TOLERANCE[field]


def term_records(student_id, session=None, semester=None):
    if session is None:
        session, semester = current_term()
    query = (select(CourseRecord).join(Course)
             .where(CourseRecord.student_id == student_id,
                    CourseRecord.session == session, CourseRecord.semester == semester)
             .order_by(Course.code))
    return list(db.session.scalars(query))


def course_row(record):
    """Everything the pages need to know about one record."""
    att, att_status = effective(record, "attendance")
    ca, ca_status = effective(record, "ca")
    exam, exam_status = effective(record, "exam")
    grade = unn.grade_for(ca, exam)
    return {
        "record": record, "course": record.course, "units": record.course.units,
        "attendance": att, "attendance_status": att_status,
        "ca": ca, "ca_status": ca_status, "exam": exam, "exam_status": exam_status,
        "grade": grade[0] if grade else None, "points": grade[1] if grade else None,
        "disputed": [f for f in ("attendance", "ca", "exam") if is_disputed(record, f)],
    }


def attendance_summary(rows):
    """Average attendance over the courses that have a value, and how trustworthy it is."""
    values = [(r["attendance"], r["attendance_status"]) for r in rows if r["attendance"] is not None]
    if not values:
        return None
    from sarps.unn import round_half_up
    mean = round_half_up(sum(v for v, _ in values) / len(values), 1)
    official = sum(1 for _, s in values if s == OFFICIAL)
    return {"value": mean, "courses": len(values), "official": official,
            "unverified": len(values) - official,
            "disputed": any("attendance" in r["disputed"] for r in rows)}


def records_attendance(student_id):
    """The attendance figure taken from the student's records for this semester, or None."""
    rows = [course_row(r) for r in term_records(student_id)]
    return attendance_summary(rows)
