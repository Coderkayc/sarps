"""The student inputs and how each answer becomes a number for the model.

This one file is shared by the web form, by training and by prediction, so the
three can never disagree. Every encoding below is a fixed, documented rule.

Inputs (what the student answers)            Model feature (what the model sees)
-------------------------------------------  ----------------------------------------
Class attendance dropdown (7 options)        attendance_level            0 to 6
Assignments assigned / submitted             assignment_submission_rate  0 to 100, blank if none assigned
Tests/CAs done / above 70% / below 50%       ca_high_rate, ca_low_rate   0 to 100, blank if none done
Study hours per week dropdown (10 options)   study_hours_level           0 to 9
Financial comfort dropdown (5 options)       financial_comfort           1 (severely struggling) to 5 (very comfortable)
Money affects participation dropdown         financial_impact            1 (never) to 5 (almost always)
Current CGPA (only if the student has one)   previous_cgpa               0 to 5, blank if not available

A blank feature is filled with the training median by the model pipeline. It is never treated as zero.
"""
import math

import numpy as np
import pandas as pd

# Column names, both in the training CSV and inside the model.
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

# The column holding the real outcome in the dataset.
#   1 = the student was Not at Risk,  0 = the student was At Risk
LABEL_COLUMN = "not_at_risk"

# ---- dropdown options: (level, text shown to the student). The text is exactly as specified. ----
ATTENDANCE_OPTIONS = [
    (0, "Never (0%)"),
    (1, "Very Rarely (1–20%)"),
    (2, "Rarely (21–40%)"),
    (3, "A Few Times (41–60%)"),
    (4, "Often (61–80%)"),
    (5, "Most of the Time (81–95%)"),
    (6, "I Attend Every Class (96–100%)"),
]
# Upper edge of each attendance band, used to turn a percentage (training data) into a level.
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
# Upper edge (in hours) of each study band from level 2 upwards. Level 1 is 0 < hours < 5.
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
    """The text for a stored level, or None if the level is unknown."""
    for value, text in options:
        if value == level:
            return text
    return None


def valid_levels(options):
    return {value for value, _ in options}


# ---- turning a number from a dataset into the same levels the form uses ----
def attendance_level_from_pct(pct):
    """0 -> 0, 1-20 -> 1, 21-40 -> 2, 41-60 -> 3, 61-80 -> 4, 81-95 -> 5, 96-100 -> 6."""
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
    """0 -> 0, under 5 -> 1, then 5-10 -> 2, over 10-15 -> 3 ... 35-40 -> 8, over 40 -> 9."""
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


# ---- rates from the counts the student types ----
def rate_or_nan(part, total):
    """part/total as a percentage, or NaN when total is 0 (never divide by zero)."""
    if total is None or part is None or total == 0:
        return np.nan
    return 100.0 * float(part) / float(total)


def features_from_inputs(attendance_level, assignments_assigned, assignments_submitted,
                         tests_done, tests_high, tests_low, study_hours_level,
                         financial_comfort, financial_impact, previous_cgpa=None):
    """Build one row of model inputs from the form answers. Missing values become NaN."""
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
    """A list of feature dicts as a DataFrame with the exact column order the model expects."""
    return pd.DataFrame(rows, columns=FEATURE_COLUMNS).astype(float)
