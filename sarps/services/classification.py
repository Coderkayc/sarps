"""The 50% rule.

The model gives the probability (in percent) that a student is NOT at risk.
    below 50   -> At Risk
    exactly 50 -> At Risk
    above 50   -> Not at Risk

The probability is first rounded to two decimals. That rounded number is the
one stored, shown to the student, and used for the decision, so what the
student sees is always exactly what was classified.
"""
import math
from decimal import ROUND_HALF_UP, Decimal

from sarps.constants import RISK_AT, RISK_NOT, THRESHOLD_PERCENT


def normalise_percent(value):
    """Validate a 0-100 percentage and round it to two decimals."""
    if isinstance(value, bool) or value is None:
        raise ValueError("Probability must be a number.")
    value = float(value)
    if not math.isfinite(value) or value < 0 or value > 100:
        raise ValueError("Probability must be between 0 and 100.")
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def classify(prob_not_at_risk_percent):
    """Return 'At Risk' or 'Not at Risk' for a Not-at-Risk probability in percent."""
    percent = normalise_percent(prob_not_at_risk_percent)
    return RISK_NOT if percent > THRESHOLD_PERCENT else RISK_AT
