"""The 50% rule, tested at its edges."""
import pytest

from sarps.services.classification import classify, normalise_percent


@pytest.mark.parametrize("value, expected", [
    (0, "At Risk"),
    (49.99, "At Risk"),
    (50, "At Risk"),            # exactly 50% is At Risk
    (50.0, "At Risk"),
    (50.004, "At Risk"),        # rounds to 50.00, which is what the student sees
    (50.005, "Not at Risk"),    # rounds to 50.01
    (50.01, "Not at Risk"),
    (73.2, "Not at Risk"),
    (100, "Not at Risk"),
])
def test_classification_rule(value, expected):
    assert classify(value) == expected


@pytest.mark.parametrize("bad", [-0.01, 100.01, float("nan"), float("inf"), None, True, "abc"])
def test_invalid_probabilities_are_rejected(bad):
    with pytest.raises(ValueError):
        classify(bad)


def test_rounding_is_to_two_decimals_half_up():
    assert normalise_percent(12.345) == 12.35
    assert normalise_percent(12.344) == 12.34
