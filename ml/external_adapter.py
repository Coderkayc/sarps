"""
"""
import numpy as np

ATTENDANCE_MIDPOINTS = [0.0, 10.0, 30.0, 50.0, 70.0, 88.0, 98.0]
STUDY_MIDPOINTS = [0.0, 2.5, 7.5, 12.5, 17.5, 22.5, 27.5, 32.5, 37.5, 42.0]

STANDALONE_COLUMNS = ["attendance_pct", "submission_rate", "test_performance_score",
                      "study_hours_midpoint", "financial_composite", "cgpa"]


def _clean(value, neutral):
    return neutral if value is None or not np.isfinite(value) else float(value)


def translate_row(row, cgpa_median):
    """."""
    attendance = ATTENDANCE_MIDPOINTS[int(round(row["attendance_level"]))]
    submission = _clean(row["assignment_submission_rate"], 50.0) / 100.0
    high, low = row["ca_high_rate"], row["ca_low_rate"]
    if np.isfinite(high) and np.isfinite(low):
        performance = float(np.clip(((high - low) / 100.0 + 1) / 2, 0, 1))
    else:
        performance = 0.5
    study = STUDY_MIDPOINTS[int(round(row["study_hours_level"]))]
    comfort = float(row["financial_comfort"])
    impact_good_direction = 6.0 - float(row["financial_impact"])
    composite = (comfort + impact_good_direction) / 2
    cgpa = _clean(row["previous_cgpa"], cgpa_median)
    return [attendance, submission, performance, study, composite, cgpa]


class ExternalModelPipeline:
    """"""

    classes_ = np.array([0, 1])

    def __init__(self, scaler, model, cgpa_median):
        self.scaler = scaler
        self.model = model
        self.cgpa_median = float(cgpa_median)

    def predict_proba(self, frame):
        rows = [translate_row(r, self.cgpa_median) for _, r in frame.iterrows()]
        import pandas as pd
        scaled = self.scaler.transform(pd.DataFrame(rows, columns=STANDALONE_COLUMNS))
        at_risk = self.model.predict_proba(scaled)[:, 1]
        return np.column_stack([at_risk, 1.0 - at_risk])
