"""Semester projection and "what do I need?" for one student, using only the UNN rules.

Nothing here is a prediction. It is arithmetic on the student's own figures,
so it can be checked by hand. The machine-learning model is used separately.
"""
from sarps import unn
from sarps.services.records import UNVERIFIED, course_row, term_records

SCENARIO_EXAMS = (20, 30, 40, 50, 60, 70)  # example exam scores out of 70


def build_plan(student_id):
    rows = [course_row(r) for r in term_records(student_id)]
    plan = {"rows": rows, "has_courses": bool(rows)}
    if not rows:
        return plan

    plan["semester_units"] = sum(r["units"] for r in rows)
    finished = [r for r in rows if r["points"] is not None]
    pending = [r for r in rows if r["points"] is None]
    plan["finished"], plan["pending"] = finished, pending
    plan["unverified_used"] = any(
        r[f"{f}_status"] == UNVERIFIED for r in rows for f in ("attendance", "ca", "exam"))

    # Per-course: what exam score each grade needs (only when the CA is known and no exam yet).
    for r in pending:
        r["needs"] = None
        if r["ca"] is not None and r["exam"] is None:
            r["needs"] = [(letter, unn.exam_needed_for(r["ca"], letter)) for letter in "ABCDE"]
        r["max_possible"] = unn.grade_for_total(r["ca"] + unn.EXAM_MAX)[0] if r["ca"] is not None else None

    fixed = [(r["units"], r["points"]) for r in finished]
    plan["complete"] = not pending
    if plan["complete"]:
        plan["semester_gpa"] = unn.gpa(fixed)

    ready = [r for r in pending if r["ca"] is not None]
    plan["scenarios"] = []
    if pending and len(ready) == len(pending):
        for exam in SCENARIO_EXAMS:
            pairs = fixed + [(r["units"], unn.grade_for_total(r["ca"] + exam)[1]) for r in pending]
            plan["scenarios"].append({"exam": exam, "gpa": unn.gpa(pairs)})
    plan["missing_ca"] = [r["course"].code for r in pending if r["ca"] is None]
    return plan
