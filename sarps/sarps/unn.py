"""UNN academic rules: grades, GPA, CGPA, degree class and "what do I need?" arithmetic.

This file contains NO machine learning. It is exact arithmetic on published
rules, so every number it returns can be checked by hand.

SOURCE of the grading bands, CGPA classes and the 30/70 split:
    University of Nigeria, Nsukka, Faculty of Arts "Course Module Credit Unit" page
    https://arts.unn.edu.ng/?p=271
    (A 70-100, B 60-69, C 50-59, D 45-49, E 40-44, F 0-39; CA 30%, exam 70%;
     First Class 4.50-5.00, Second Upper 3.50-4.49, Second Lower 2.40-3.49,
     Third 1.50-2.39.)

ASSUMPTIONS that are NOT stated on that page. Confirm them with your department:
    * Grade points: A=5, B=4, C=3, D=2, E=1, F=0 (the page only shows A, C, D, E).
    * CA is marked out of 30 and the exam out of 70 in every course.
    * Scores are whole numbers; a total such as 69.5 is rounded half up to 70.
    * GPA and CGPA are weighted by credit units and rounded half up to 2 decimals.
    * Computer Science (and every other department) uses the same scale as the page above.
"""
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

CA_MAX = 30
EXAM_MAX = 70
TOTAL_MAX = CA_MAX + EXAM_MAX
MAX_POINTS = 5.0

# (lowest total score, letter, grade points), highest band first.
GRADE_BANDS = [
    (70, "A", 5),
    (60, "B", 4),
    (50, "C", 3),
    (45, "D", 2),
    (40, "E", 1),
    (0, "F", 0),
]
GRADE_POINTS = {letter: points for _, letter, points in GRADE_BANDS}
BAND_MIN = {letter: low for low, letter, _ in GRADE_BANDS}

# (lowest CGPA, name), highest first.
DEGREE_CLASSES = [
    (4.50, "First Class"),
    (3.50, "Second Class Upper"),
    (2.40, "Second Class Lower"),
    (1.50, "Third Class"),
]
BELOW_CLASS = "Below Third Class (no degree class)"


class GradingError(ValueError):
    """A score or input is outside what the UNN rules allow."""


def round_half_up(value, places=2):
    """Round the way people do on paper (2.345 -> 2.35), not like Python's round()."""
    quantum = Decimal(1).scaleb(-places)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def _check_range(value, high, name):
    if value is None:
        return None
    number = float(value)
    if number != number or number < 0 or number > high:
        raise GradingError(f"{name} must be between 0 and {high}.")
    return number


def total_score(ca, exam):
    """CA (out of 30) plus exam (out of 70). Returns None if either is missing."""
    ca = _check_range(ca, CA_MAX, "CA score")
    exam = _check_range(exam, EXAM_MAX, "Exam score")
    if ca is None or exam is None:
        return None
    return ca + exam


def grade_for_total(total):
    """Letter and grade points for a total out of 100."""
    total = _check_range(total, TOTAL_MAX, "Total score")
    whole = int(Decimal(str(total)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    for low, letter, points in GRADE_BANDS:
        if whole >= low:
            return letter, points
    raise GradingError("Total score is outside every grade band.")  # unreachable


def grade_for(ca, exam):
    """Letter and points from CA and exam, or None while either is missing."""
    total = total_score(ca, exam)
    return None if total is None else grade_for_total(total)


def gpa(courses):
    """Semester GPA. `courses` is a list of (credit_units, grade_points). None if no units."""
    units = sum(u for u, _ in courses)
    if units <= 0:
        return None
    return round_half_up(sum(u * p for u, p in courses) / units)


def cumulative(previous_cgpa, previous_units, semester_courses):
    """CGPA after adding this semester. Returns None when there is nothing to compute."""
    sem_units = sum(u for u, _ in semester_courses)
    sem_points = sum(u * p for u, p in semester_courses)
    total_units = (previous_units or 0) + sem_units
    if total_units <= 0:
        return None
    previous_points = (previous_cgpa or 0) * (previous_units or 0)
    return round_half_up((previous_points + sem_points) / total_units)


def degree_class(cgpa):
    if cgpa is None:
        return None
    value = round_half_up(cgpa)
    for low, name in DEGREE_CLASSES:
        if value >= low:
            return name
    return BELOW_CLASS


def exam_needed_for(ca, letter):
    """Smallest exam score (out of 70) that gives at least `letter` with this CA.

    Returns 0 if the CA alone already secures it, or None if even 70/70 is not enough.
    """
    ca = _check_range(ca, CA_MAX, "CA score")
    if letter not in BAND_MIN:
        raise GradingError(f"Unknown grade '{letter}'.")
    ca_whole = Decimal(str(ca))
    # total must round to at least BAND_MIN, i.e. total >= BAND_MIN - 0.5
    needed = Decimal(BAND_MIN[letter]) - Decimal("0.5") - ca_whole
    if needed <= 0:
        return 0
    need = int(needed.to_integral_value(rounding=ROUND_CEILING))
    return need if need <= EXAM_MAX else None


def required_semester_gpa(previous_cgpa, previous_units, semester_units, target_cgpa):
    """The semester GPA needed to finish on `target_cgpa`.

    Returns a dict: needed (float, may be <= 0 if already safe), feasible (needed <= 5.0).
    """
    if semester_units is None or semester_units <= 0:
        raise GradingError("Semester credit units must be above zero.")
    total_units = (previous_units or 0) + semester_units
    needed = (target_cgpa * total_units - (previous_cgpa or 0) * (previous_units or 0)) / semester_units
    needed = round_half_up(needed)
    return {"needed": needed, "feasible": needed <= MAX_POINTS, "already_secured": needed <= 0}


def uniform_exam_for_gpa(courses, needed_gpa, fixed=()):
    """Smallest exam score (out of 70), the SAME in every pending course, that reaches `needed_gpa`.

    `courses` are the courses still waiting for an exam: dicts with units and ca (out of 30).
    `fixed` are courses already finished, as (units, grade_points) pairs.
    Returns an int, or None if even 70/70 everywhere is not enough.
    """
    for exam in range(0, EXAM_MAX + 1):
        pairs = list(fixed) + [(c["units"], grade_for_total(c["ca"] + exam)[1]) for c in courses]
        value = gpa(pairs)
        if value is not None and value >= needed_gpa:
            return exam
    return None
