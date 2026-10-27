"""Lets SARPS use the standalone Random Forest trained on SYNTHETIC data (the "sarps_model" package).

That package was trained on made-up students, so its results are a DEMONSTRATION, not evidence.
The website shows a banner on every page while it is switched on.

This file only translates. The website collects the answers in ml/features.py; the
standalone model expects six differently-shaped numbers. Every translation rule is below,
each one written down so it can be stated honestly in the report and at the defense.

    Website answer (ml/features.py)         ->  standalone model input
    attendance_level 0..6                   ->  attendance_pct: the middle of the chosen band
    assignment_submission_rate 0..100       ->  submission_rate 0..1  (blank -> 0.5, neutral)
    ca_high_rate, ca_low_rate (0..100)      ->  test_performance_score 0..1, same formula the
                                                standalone predict.py uses (blank -> 0.5, neutral)
    study_hours_level 0..9                  ->  study_hours_midpoint: the middle of the chosen band
    financial_comfort 1..5 + impact 1..5    ->  financial_composite = (comfort + (6 - impact)) / 2
    previous_cgpa 0..5                      ->  cgpa (blank -> the median saved with the model)

ASSUMPTION worth stating: on the website a HIGH "financial impact" answer means money affects the
student OFTEN (bad). In the standalone model's training data a high impact number meant GOOD
(it rose together with comfort). So the website's answer is flipped (6 - answer) before use.
"""
import numpy as np

# Middle of each attendance band: 0%, 1-20%, 21-40%, 41-60%, 61-80%, 81-95%, 96-100%.
ATTENDANCE_MIDPOINTS = [0.0, 10.0, 30.0, 50.0, 70.0, 88.0, 98.0]
# The same midpoints the standalone model's own generator used for study hours.
STUDY_MIDPOINTS = [0.0, 2.5, 7.5, 12.5, 17.5, 22.5, 27.5, 32.5, 37.5, 42.0]

STANDALONE_COLUMNS = ["attendance_pct", "submission_rate", "test_performance_score",
                      "study_hours_midpoint", "financial_composite", "cgpa"]


def _clean(value, neutral):
    return neutral if value is None or not np.isfinite(value) else float(value)


def translate_row(row, cgpa_median):
    """One website feature row (dict-like) -> the six standalone inputs, in order."""
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
    """Looks like a scikit-learn model to SARPS: predict_proba with classes 0 (At Risk), 1 (Not at Risk)."""

    classes_ = np.array([0, 1])

    def __init__(self, scaler, model, cgpa_median):
        self.scaler = scaler
        self.model = model
        self.cgpa_median = float(cgpa_median)

    def predict_proba(self, frame):
        rows = [translate_row(r, self.cgpa_median) for _, r in frame.iterrows()]
        import pandas as pd
        scaled = self.scaler.transform(pd.DataFrame(rows, columns=STANDALONE_COLUMNS))
        # The standalone model's class 1 means "at risk"; SARPS wants [At Risk, Not at Risk] = [0, 1].
        at_risk = self.model.predict_proba(scaled)[:, 1]
        return np.column_stack([at_risk, 1.0 - at_risk])
