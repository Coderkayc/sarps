"""The five student inputs, defined once and shared by training and prediction.

Training and prediction MUST use exactly the same columns, in the same order,
with the same number conventions. Keeping that in one file prevents the two
from drifting apart.
"""
import math

import numpy as np
import pandas as pd

# Column names, both in the training CSV and inside the model.
FEATURE_COLUMNS = [
    "attendance_pct",             # required, 0-100
    "assignment_completion_pct",  # required, 0-100
    "previous_cgpa",              # optional, blank = not available
    "financial_capability",       # optional: low / medium / high, blank = not given
    "study_hours_per_week",       # optional, blank = not given
]

# The column holding the real outcome in your dataset.
#   1 = the student was Not at Risk,  0 = the student was At Risk
# The model's "probability of class 1" is therefore the probability of Not at Risk.
LABEL_COLUMN = "not_at_risk"

FINANCIAL_ORDINAL = {"low": 1.0, "medium": 2.0, "high": 3.0}


def financial_to_number(value):
    """Turn low/medium/high (or 1/2/3) into a number. Blank becomes NaN."""
    if value is None:
        return np.nan
    if isinstance(value, float) and math.isnan(value):
        return np.nan
    if isinstance(value, str):
        text = value.strip().lower()
        if text == "":
            return np.nan
        if text in FINANCIAL_ORDINAL:
            return FINANCIAL_ORDINAL[text]
        try:
            value = float(text)
        except ValueError:
            raise ValueError(f"Unknown financial_capability value: {value!r}")
    number = float(value)
    if number not in (1.0, 2.0, 3.0):
        raise ValueError(f"financial_capability must be low/medium/high or 1/2/3, got {value!r}")
    return number


def _number_or_nan(value):
    return np.nan if value is None else float(value)


def features_from_inputs(attendance_pct, assignment_completion_pct, previous_cgpa=None,
                         financial_capability=None, study_hours_per_week=None):
    """Build one row of model inputs. Missing optional values become NaN."""
    return {
        "attendance_pct": float(attendance_pct),
        "assignment_completion_pct": float(assignment_completion_pct),
        "previous_cgpa": _number_or_nan(previous_cgpa),
        "financial_capability": financial_to_number(financial_capability),
        "study_hours_per_week": _number_or_nan(study_hours_per_week),
    }


def to_frame(rows):
    """A list of feature dicts as a DataFrame with the exact column order the model expects."""
    return pd.DataFrame(rows, columns=FEATURE_COLUMNS).astype(float)
