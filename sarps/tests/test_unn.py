"""UNN rules, checked against hand calculation."""
import pytest

from sarps import unn


@pytest.mark.parametrize("total,letter,points", [
    (100, "A", 5), (70, "A", 5), (69, "B", 4), (60, "B", 4), (59, "C", 3), (50, "C", 3),
    (49, "D", 2), (45, "D", 2), (44, "E", 1), (40, "E", 1), (39, "F", 0), (0, "F", 0),
])
def test_grade_band_edges(total, letter, points):
    assert unn.grade_for_total(total) == (letter, points)


def test_half_marks_round_up_before_banding():
    assert unn.grade_for_total(69.5) == ("A", 5)
    assert unn.grade_for_total(69.4) == ("B", 4)
    assert unn.grade_for_total(44.5) == ("D", 2)


def test_total_needs_both_parts_and_checks_ranges():
    assert unn.total_score(20, None) is None
    assert unn.total_score(20, 45) == 65
    assert unn.grade_for(25, 50) == ("A", 5)
    for ca, exam in [(31, 10), (-1, 10), (10, 71), (10, -3), (float("nan"), 10)]:
        with pytest.raises(unn.GradingError):
            unn.total_score(ca, exam)
    with pytest.raises(unn.GradingError):
        unn.grade_for_total(101)


def test_gpa_hand_example():
    # 3u A(5), 2u B(4), 4u C(3), 1u F(0): (15 + 8 + 12 + 0) / 10 = 3.5
    assert unn.gpa([(3, 5), (2, 4), (4, 3), (1, 0)]) == 3.5
    assert unn.gpa([]) is None


def test_gpa_rounds_half_up_not_bankers():
    # 2.345 must become 2.35. (Python's round(2.345, 2) gives 2.35 or 2.34 depending on float error.)
    assert unn.round_half_up(2.345) == 2.35
    assert unn.round_half_up(2.355) == 2.36
    assert unn.round_half_up(0.125) == 0.13


def test_cgpa_is_weighted_by_units():
    # Before: 3.00 over 60 units = 180 points. Now 20 units at GPA 4.00 = 80 points. 260/80 = 3.25
    assert unn.cumulative(3.0, 60, [(10, 4), (10, 4)]) == 3.25
    # First semester: no history
    assert unn.cumulative(None, 0, [(3, 4), (3, 2)]) == 3.0
    assert unn.cumulative(None, 0, []) is None


def test_degree_classes_at_boundaries():
    assert unn.degree_class(5.0) == "First Class"
    assert unn.degree_class(4.50) == "First Class"
    assert unn.degree_class(4.49) == "Second Class Upper"
    assert unn.degree_class(3.50) == "Second Class Upper"
    assert unn.degree_class(3.49) == "Second Class Lower"
    assert unn.degree_class(2.40) == "Second Class Lower"
    assert unn.degree_class(2.39) == "Third Class"
    assert unn.degree_class(1.50) == "Third Class"
    assert unn.degree_class(1.49) == unn.BELOW_CLASS
    assert unn.degree_class(None) is None


def test_exam_needed_for_each_grade():
    # CA 20/30: need total 70 for A -> exam 50; B 60 -> 40; C 50 -> 30; D 45 -> 25; E 40 -> 20
    assert [unn.exam_needed_for(20, g) for g in "ABCDE"] == [50, 40, 30, 25, 20]
    assert unn.exam_needed_for(20, "F") == 0
    # CA alone can secure a lower grade
    assert unn.exam_needed_for(30, "E") == 10
    assert unn.exam_needed_for(0, "A") == 70
    # CA 0 and an A needs the full 70, but a CA that makes it impossible returns None
    assert unn.exam_needed_for(0, "A") == 70


def test_exam_needed_matches_grade_for_exhaustively():
    for ca in range(0, 31):
        for letter in "ABCDE":
            need = unn.exam_needed_for(ca, letter)
            if need is None:
                assert unn.grade_for(ca, 70)[1] < unn.GRADE_POINTS[letter]
                continue
            assert unn.grade_for(ca, need)[1] >= unn.GRADE_POINTS[letter]
            if need > 0:
                assert unn.grade_for(ca, need - 1)[1] < unn.GRADE_POINTS[letter]


def test_required_semester_gpa():
    # Have 3.00 over 60 units, 20 units this semester, target 3.50 over 80 units:
    # need (3.5*80 - 180)/20 = 5.0
    result = unn.required_semester_gpa(3.0, 60, 20, 3.5)
    assert result == {"needed": 5.0, "feasible": True, "already_secured": False}
    # Target 3.51 would need 5.05: impossible
    assert unn.required_semester_gpa(3.0, 60, 20, 3.51)["feasible"] is False
    # A target already below what any result could drop us to is secured
    assert unn.required_semester_gpa(4.5, 60, 2, 2.0)["already_secured"] is True
    with pytest.raises(unn.GradingError):
        unn.required_semester_gpa(3.0, 60, 0, 3.5)


def test_uniform_exam_search_is_the_minimum():
    courses = [{"units": 3, "ca": 20}, {"units": 2, "ca": 15}]
    exam = unn.uniform_exam_for_gpa(courses, 4.0)

    def gpa_at(e):
        return unn.gpa([(c["units"], unn.grade_for_total(c["ca"] + e)[1]) for c in courses])
    assert gpa_at(exam) >= 4.0 and gpa_at(exam - 1) < 4.0
    assert unn.uniform_exam_for_gpa([{"units": 3, "ca": 0}], 5.0) == 70
    assert unn.uniform_exam_for_gpa([{"units": 3, "ca": 0}], 6.0) is None


def test_uniform_exam_counts_finished_courses():
    # A finished 3-unit A (5 points) already helps: with one pending 3-unit course at CA 20,
    # a 4.0 GPA needs (15 + 3p)/6 >= 4 -> p >= 3 (C) -> total 50 -> exam 30.
    exam = unn.uniform_exam_for_gpa([{"units": 3, "ca": 20}], 4.0, fixed=[(3, 5)])
    assert exam == 30
