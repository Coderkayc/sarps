"""
"""
import math

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "attendance_level",
    "assignment_submission_rate",
    "ca_high_rate",
    "ca_low_rate",
    "study_hours_level",
    "financial_comfort",
    "financial_impact",
    "previous_cgpa",
]

LABEL_COLUMN = "not_at_risk"

ATTENDANCE_OPTIONS = [
    (0, "Never (0%)"),
    (1, "Very Rarely (1–20%)"),
    (2, "Rarely (21–40%)"),
    (3, "A Few Times (41–60%)"),
    (4, "Often (61–80%)"),
    (5, "Most of the Time (81–95%)"),
    (6, "I Attend Every Class (96–100%)"),
]
ATTENDANCE_UPPER_EDGES = [0, 20, 40, 60, 80, 95, 100]

STUDY_HOURS_OPTIONS = [
    (0, "0 hours (I do not study outside class)"),
    (1, "Below 5 hours"),
    (2, "5–10 hours"),
    (3, "10–15 hours"),
    (4, "15–20 hours"),
    (5, "20–25 hours"),
    (6, "25–30 hours"),
    (7, "30–35 hours"),
    (8, "35–40 hours"),
    (9, "Over 40 hours"),
]
STUDY_UPPER_EDGES = [10, 15, 20, 25, 30, 35, 40]

FINANCIAL_COMFORT_OPTIONS = [
    (5, "Very Comfortable"),
    (4, "Comfortable"),
    (3, "Fairly Comfortable"),
    (2, "Somewhat Struggling"),
    (1, "Severely Struggling"),
]

FINANCIAL_IMPACT_OPTIONS = [
    (1, "Never affects me"),
    (2, "Rarely affects me"),
    (3, "Sometimes affects me"),
    (4, "Often affects me"),
    (5, "Almost always affects me"),
]


def option_label(options, level):
    """"""
    for value, text in options:
        if value == level:
            return text
    return None


def valid_levels(options):
    return {value for value, _ in options}

def attendance_level_from_pct(pct):
    """"""
    if pct is None or (isinstance(pct, float) and math.isnan(pct)):
        return np.nan
    if pct < 0 or pct > 100:
        return np.nan
    if pct <= 0:
        return 0
    for level, edge in enumerate(ATTENDANCE_UPPER_EDGES[1:], start=1):
        if pct <= edge:
            return level
    return 6


def study_level_from_weekly_hours(hours):
    """"""
    if hours is None or (isinstance(hours, float) and math.isnan(hours)) or hours < 0:
        return np.nan
    if hours == 0:
        return 0
    if hours < 5:
        return 1
    for level, edge in enumerate(STUDY_UPPER_EDGES, start=2):
        if hours <= edge:
            return level
    return 9

def rate_or_nan(part, total):
    """."""
    if total is None or part is None or total == 0:
        return np.nan
    return 100.0 * float(part) / float(total)


def features_from_inputs(attendance_level, assignments_assigned, assignments_submitted,
                         tests_done, tests_high, tests_low, study_hours_level,
                         financial_comfort, financial_impact, previous_cgpa=None):
    """"""
    return {
        "attendance_level": float(attendance_level),
        "assignment_submission_rate": rate_or_nan(assignments_submitted, assignments_assigned),
        "ca_high_rate": rate_or_nan(tests_high, tests_done),
        "ca_low_rate": rate_or_nan(tests_low, tests_done),
        "study_hours_level": float(study_hours_level),
        "financial_comfort": float(financial_comfort),
        "financial_impact": float(financial_impact),
        "previous_cgpa": np.nan if previous_cgpa is None else float(previous_cgpa),
    }


def to_frame(rows):
    """"""
    return pd.DataFrame(rows, columns=FEATURE_COLUMNS).astype(float)
