"""
"""
import math
from decimal import ROUND_HALF_UP, Decimal

from sarps.constants import RISK_AT, RISK_NOT, THRESHOLD_PERCENT


def normalise_percent(value):
    """"""
    if isinstance(value, bool) or value is None:
        raise ValueError("Probability must be a number.")
    value = float(value)
    if not math.isfinite(value) or value < 0 or value > 100:
        raise ValueError("Probability must be between 0 and 100.")
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def classify(prob_not_at_risk_percent):
    """"""
    percent = normalise_percent(prob_not_at_risk_percent)
    return RISK_NOT if percent > THRESHOLD_PERCENT else RISK_AT
