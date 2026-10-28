"""Plain-language advice for a student, built from their own answers.

Every sentence below comes from a fixed rule and cites the answer it is based on.
Nothing is generated freely, so nothing can be invented. Rules that depend on an
assumption say so in the text.
"""
from ml.features import (ATTENDANCE_OPTIONS, STUDY_HOURS_OPTIONS, option_label)
from sarps import unn

# A commonly required minimum for sitting exams in Nigerian universities. NOT confirmed
# for UNN, so the advice words it as "commonly required".
ATTENDANCE_COMMON_MINIMUM = 75
FEATURE_WORDS = {
    "attendance_level": "class attendance",
    "previous_cgpa": "previous CGPA",
    "study_hours_level": "weekly study hours",
}
# Inputs we never turn into "fix this" advice: not something a student can change this
# semester, or only a proxy in the training data.
NOT_ACTIONABLE = {"financial_comfort", "financial_impact"}
# Plain names for the model inputs, used when saying which answers do not change the score.
INPUT_WORDS = {
    "attendance_level": "class attendance",
    "assignment_submission_rate": "assignment submission",
    "ca_high_rate": "tests and CAs (above 70%)",
    "ca_low_rate": "tests and CAs (below 50%)",
    "study_hours_level": "study hours",
    "financial_comfort": "financial comfort",
    "financial_impact": "how often money affects participation",
    "previous_cgpa": "CGPA",
}


def _item(kind, title, body):
    return {"kind": kind, "title": title, "body": body}


def _level_text(options, level):
    """The dropdown wording for the nearest whole level, e.g. 'Often (61\u201380%)'."""
    return option_label(options, int(round(level))) or f"level {level:.1f}"


def build_advice(assessment, drivers, meta=None, plan=None, unused=()):
    """Return an ordered list of {kind, title, body}. kind: urgent, important, info or good."""
    items = []
    a = assessment
    prob = a.prob_not_at_risk
    at_risk = a.risk_label == "At Risk"

    # 1. What the number means
    if at_risk:
        closeness = ("This is close to the 50% line, so a few good weeks could change it. "
                     if prob >= 40 else "")
        items.append(_item("urgent", "Your score needs attention",
                           f"The model puts your Not at Risk score at {prob:.1f}%, which is 50% or below, "
                           f"so you are classified At Risk. {closeness}This is an estimate, not a verdict. "
                           "Please speak to your academic adviser early; they have been told so they can help."))
    else:
        close = " It is not far above the 50% line, so keep the habits that got you here." if prob < 60 else ""
        items.append(_item("good", "You are currently Not at Risk",
                           f"Your Not at Risk score is {prob:.1f}%, above the 50% line.{close}"))

    # 2. The biggest things pulling the score down or up (actionable inputs only)
    pulls = [d for d in drivers if d["name"] not in NOT_ACTIONABLE and d["contribution"] < -0.05]
    for d in pulls[:2]:
        if d["name"] == "previous_cgpa":
            items.append(_item("important", "Your CGPA is holding the score down",
                               f"Your CGPA of {d['value']:.2f} is below the average of "
                               f"{d['typical']:.2f} in the data the model learned from. You cannot change "
                               "the past, but a strong semester raises it (see your plan)."))
        elif d["name"] == "attendance_level":
            items.append(_item("important", "Attendance is the main thing you can change",
                               f"You said you attend: {_level_text(ATTENDANCE_OPTIONS, d['value'])}. The students the model "
                               f"learned from typically attended: {_level_text(ATTENDANCE_OPTIONS, d['typical'])}. "
                               "Your attendance is pulling your score down. Attend every class you can from now on."))
        elif d["name"] == "study_hours_level":
            items.append(_item("important", "More study time would help",
                               f"You said you study: {_level_text(STUDY_HOURS_OPTIONS, d['value'])}. The students the model "
                               f"learned from typically studied: {_level_text(STUDY_HOURS_OPTIONS, d['typical'])}. "
                               "This is pulling your score down. A steady routine of even a few more hours a week adds up."))
        else:
            label = FEATURE_WORDS.get(d["name"], d["name"])
            items.append(_item("important", f"Raise your {label}",
                               "This is below the average in the data the model learned from, "
                               "and it is pulling your score down."))
    helps = [d for d in drivers if d["name"] not in NOT_ACTIONABLE and d["contribution"] > 0.05]
    if helps:
        d = helps[0]
        if d["name"] == "previous_cgpa":
            detail = f"At {d['value']:.2f} it is above the average of {d['typical']:.2f} in the data the model learned from"
        elif d["name"] == "attendance_level":
            detail = f"Attending \"{_level_text(ATTENDANCE_OPTIONS, d['value'])}\" is better than the typical student the model learned from"
        else:
            detail = f"Studying \"{_level_text(STUDY_HOURS_OPTIONS, d['value'])}\" is more than the typical student the model learned from"
        items.append(_item("good", f"Your {FEATURE_WORDS.get(d['name'], d['name'])} is helping",
                           f"{detail}, which raises your score."))

    # 3. Rules that depend only on the student's own answers
    if a.attendance_level is not None and a.attendance_level <= 3:
        items.append(_item("urgent", "Attendance is below the commonly required level",
                           f"Many Nigerian universities require about {ATTENDANCE_COMMON_MINIMUM}% attendance to sit exams. "
                           f"You said you attend: {option_label(ATTENDANCE_OPTIONS, a.attendance_level)}, which is below that. "
                           "Check your department's exact rule and talk to your lecturers."))
    elif a.attendance_level == 4:
        items.append(_item("important", "Attendance may be close to the commonly required level",
                           f"You said you attend: {option_label(ATTENDANCE_OPTIONS, 4)}. Many Nigerian universities require about "
                           f"{ATTENDANCE_COMMON_MINIMUM}% attendance to sit exams, so you could be near the limit. "
                           "Check your exact figure with your lecturers."))
    if a.assignments_assigned:
        rate = 100.0 * a.assignments_submitted / a.assignments_assigned
        if rate < 60:
            items.append(_item("important", "Catch up on assignments",
                               f"You have submitted {a.assignments_submitted} of {a.assignments_assigned} assignments "
                               f"({rate:.0f}%). Assignments usually feed into your continuous assessment, which is "
                               f"{unn.CA_MAX} of the 100 marks in each course."))
    if a.tests_done:
        if a.tests_low * 2 >= a.tests_done:
            items.append(_item("important", "Your tests and CAs are worrying you",
                               f"You feel you scored below 50% in {a.tests_low} of {a.tests_done} tests or CAs. "
                               f"CA is {unn.CA_MAX} of the 100 marks, so ask your lecturers for your actual marks "
                               "and a plan to recover marks in the exam."))
        elif a.tests_high * 2 >= a.tests_done:
            items.append(_item("good", "Your tests and CAs are going well",
                               f"You feel you scored above 70% in {a.tests_high} of {a.tests_done} tests or CAs. Keep it up."))
    if a.financial_impact is not None and a.financial_impact >= 4:
        items.append(_item("info", "Money is getting in the way of your studies",
                           "You said your finances often affect your ability to take part in school activities. "
                           "Please tell your academic adviser, who can point you to any support available."))
    if unused:
        names = ", ".join(INPUT_WORDS.get(n, n) for n in unused)
        items.append(_item("info", "Some of your answers do not change the score",
                           f"The current model was trained on data that did not include: {names}. "
                           "Your answers are saved and used for the advice above, but they do not move the percentage."))

    # 4. Course by course, from the semester plan
    if plan and plan.get("has_courses"):
        for row in plan.get("pending", []):
            code = row["course"].code
            if row["ca"] is None:
                continue
            needs = dict(row["needs"] or [])
            if needs.get("E") is None:
                items.append(_item("urgent", f"{code}: a pass is out of reach on current marks",
                                   f"With a CA of {row['ca']:g}/{unn.CA_MAX}, even full marks in the exam "
                                   "would not reach the 40 needed to pass. Ask your lecturer and adviser what options exist."))
            elif needs["E"] >= 30:
                items.append(_item("important", f"{code}: you need {needs['E']}/70 in the exam just to pass",
                                   f"Your CA is {row['ca']:g}/{unn.CA_MAX}. Put extra revision time into this course."))
        for row in plan.get("finished", []):
            if row["grade"] == "F":
                items.append(_item("urgent", f"{row['course'].code}: you have an F",
                                   "An F usually means repeating the course. Check your department's regulations "
                                   "and speak to your adviser."))
        target = plan.get("target")
        if target:
            items.append(_target_item(target, plan))
        if plan.get("unverified_used"):
            items.append(_item("info", "Some figures are your own and unverified",
                               "Figures you typed yourself are marked unverified until a lecturer or the "
                               "ICT office confirms them. Official figures always replace yours."))
    elif meta and meta.target_cgpa:
        previous = a.previous_cgpa
        gap = f" Your CGPA is {previous:.2f}, a gap of {meta.target_cgpa - previous:.2f}." if previous is not None else ""
        items.append(_item("info", f"Your target is {meta.target_cgpa:.2f}",
                           f"Add this semester's courses on the Plan page to see exactly what you need.{gap}"))

    # 5. Data honesty
    items.append(_item("info", "How much to trust this",
                       "The estimate comes from a model trained on student records from another university, so "
                       "treat it as a prompt to act, not a final answer. Your adviser knows your situation better."))
    return items


def _target_item(target, plan):
    goal = target["cgpa"]
    if "met" in target:
        if target["met"]:
            return _item("good", f"Target {goal:.2f} reached",
                         f"With these results your CGPA becomes {plan['cgpa_after']:.2f} ({plan['class_after']}).")
        return _item("important", f"Target {goal:.2f} not reached",
                     f"With these results your CGPA becomes {plan['cgpa_after']:.2f} ({plan['class_after']}). "
                     "Plan which courses to improve next semester.")
    if target["already_secured"]:
        return _item("good", f"Target {goal:.2f} is already secured",
                     "Even a weak semester would keep your CGPA at or above your target.")
    if not target["feasible"]:
        return _item("important", f"Target {goal:.2f} cannot be reached in one semester",
                     f"You would need a semester GPA of {target['needed']:.2f}, above the maximum of {unn.MAX_POINTS:.1f}. "
                     "Spread the climb across several semesters.")
    if target.get("exam_each") is not None:
        return _item("important", f"To reach {goal:.2f}, aim for about {target['exam_each']}/70 in every exam",
                     f"You need a semester GPA of {target['needed']:.2f}. With your CA scores, an exam score of "
                     f"{target['exam_each']} out of 70 in each course (about {target['exam_each'] / 0.7:.0f}%) gets you there.")
    if target.get("reachable_with_exams") is False:
        return _item("important", f"Target {goal:.2f} is out of reach this semester",
                     f"You would need a semester GPA of {target['needed']:.2f}, but even 70/70 in every exam "
                     "does not get you there with your current CA scores.")
    return _item("info", f"Target {goal:.2f}",
                 f"You need a semester GPA of {target['needed']:.2f}. Enter your CA scores to see the exam marks required.")
