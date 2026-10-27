"""Make a SYNTHETIC (made-up) training dataset that covers every SARPS input.

    python -m ml.make_synthetic                      (writes ml/data/synthetic_training.csv)
    python -m ml.make_synthetic --rows 5000 --seed 7

These students do not exist. The file lets the whole system work, and be trained, with every
input in use, until real data is available. Every rule used to invent a student is written
below and in ml/SYNTHETIC.md, so it can be stated honestly in the report.

How a student is invented
  1. Two hidden traits are drawn for each student (bell-curve random numbers):
       diligence  - how engaged and capable they are
       means      - how well off they are financially
  2. Each answer on the form is made from those traits PLUS random noise, so no answer is a
     perfect copy of a trait (real students are inconsistent too).
  3. The outcome (At Risk or not) is then drawn by chance, with the odds set by the traits.
     It is NOT a fixed if/then rule on the inputs, so the model cannot simply memorise a rule
     and its scores stay realistic instead of near-perfect.

ASSUMPTIONS (invented, not measured on real students):
  - Diligence is the main driver of doing well. Financial means has a smaller effect, and money
    affecting school ("financial pressure") hurts a little on top of that.
  - More attendance, more submitted assignments, better test results, more study hours and a
    higher CGPA all go with higher diligence.
  - More financial comfort goes with better means; money affecting school often goes with worse means.
  - About 30% of students end up At Risk.
  - About 20% have no CGPA yet; some have no assignments or tests recorded.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ml.features import FEATURE_COLUMNS, LABEL_COLUMN

DEFAULT_OUT = Path(__file__).resolve().parent / "data" / "synthetic_training.csv"

# Share of students at each level, lowest level first. These are the assumed shapes.
ATTENDANCE_SHARE = [0.03, 0.05, 0.08, 0.14, 0.24, 0.28, 0.18]            # levels 0..6
STUDY_SHARE = [0.03, 0.12, 0.22, 0.20, 0.15, 0.10, 0.07, 0.05, 0.03, 0.03]  # levels 0..9
COMFORT_SHARE = [0.08, 0.22, 0.35, 0.25, 0.10]                           # 1..5
IMPACT_SHARE = [0.25, 0.30, 0.22, 0.15, 0.08]                            # 1..5

TARGET_AT_RISK = 0.30
# Strength of each hidden trait on the outcome (assumption).
DILIGENCE_EFFECT = 1.1
MEANS_EFFECT = 0.4
PRESSURE_EFFECT = 0.3   # money affecting school hurts results beyond comfort alone (assumption)


def _levels_from_scores(scores, shares, first_level):
    """Turn a continuous score into whole levels so the share at each level matches `shares`."""
    cuts = np.quantile(scores, np.cumsum(shares)[:-1])
    return np.digitize(scores, cuts) + first_level


def _sigmoid(x):
    return 1 / (1 + np.exp(-x))


def generate(rows=2000, seed=2026):
    rng = np.random.default_rng(seed)
    n = rows
    diligence = rng.normal(size=n)
    means = rng.normal(size=n)

    # ---- the form answers ----
    attendance = _levels_from_scores(0.75 * diligence + 0.65 * rng.normal(size=n), ATTENDANCE_SHARE, 0)
    study = _levels_from_scores(0.55 * diligence + 0.85 * rng.normal(size=n), STUDY_SHARE, 0)

    assigned = rng.integers(3, 16, n)
    assigned[rng.random(n) < 0.05] = 0                     # some have no assignments yet
    p_submit = _sigmoid(0.9 + 1.0 * (0.65 * diligence + 0.35 * rng.normal(size=n)))
    submitted = rng.binomial(assigned, p_submit)
    submission_rate = np.where(assigned > 0, 100.0 * submitted / np.maximum(assigned, 1), np.nan)

    tests = rng.integers(2, 9, n)
    tests[rng.random(n) < 0.05] = 0                        # some have no tests yet
    skill = 0.65 * diligence + 0.35 * rng.normal(size=n)
    weights = np.exp(np.column_stack([-0.2 + 1.1 * skill, -0.4 - 1.1 * skill, np.zeros(n)]))
    weights /= weights.sum(axis=1, keepdims=True)           # chance of: above 70, below 50, in between
    high = np.zeros(n, dtype=int)
    low = np.zeros(n, dtype=int)
    for i in range(n):
        if tests[i]:
            draw = rng.multinomial(tests[i], weights[i])
            high[i], low[i] = draw[0], draw[1]
    ca_high = np.where(tests > 0, 100.0 * high / np.maximum(tests, 1), np.nan)
    ca_low = np.where(tests > 0, 100.0 * low / np.maximum(tests, 1), np.nan)

    comfort_score = 0.8 * means + 0.6 * rng.normal(size=n)
    comfort = _levels_from_scores(comfort_score, COMFORT_SHARE, 1)
    pressure_score = -0.6 * comfort_score + 0.8 * rng.normal(size=n)   # higher = money affects school more
    impact = _levels_from_scores(pressure_score, IMPACT_SHARE, 1)

    cgpa = np.clip(2.9 + 0.8 * (0.6 * diligence + 0.4 * rng.normal(size=n)), 0.5, 5.0).round(2)
    cgpa = np.where(rng.random(n) < 0.20, np.nan, cgpa)    # first-years have no CGPA yet

    # ---- the outcome: chance, with odds set by the hidden traits ----
    signal = (DILIGENCE_EFFECT * diligence + MEANS_EFFECT * means
              - PRESSURE_EFFECT * pressure_score + 0.5 * rng.normal(size=n))
    low_b, high_b = -10.0, 10.0                              # find the offset that gives ~30% At Risk
    for _ in range(60):
        mid = (low_b + high_b) / 2
        if (1 - _sigmoid(mid + signal)).mean() > TARGET_AT_RISK:
            low_b = mid
        else:
            high_b = mid
    p_not_at_risk = _sigmoid((low_b + high_b) / 2 + signal)
    not_at_risk = (rng.random(n) < p_not_at_risk).astype(int)

    frame = pd.DataFrame({
        "attendance_level": attendance,
        "assignment_submission_rate": np.round(submission_rate, 1),
        "ca_high_rate": np.round(ca_high, 1),
        "ca_low_rate": np.round(ca_low, 1),
        "study_hours_level": study,
        "financial_comfort": comfort,
        "financial_impact": impact,
        "previous_cgpa": cgpa,
        LABEL_COLUMN: not_at_risk,
    })
    assert list(frame.columns) == FEATURE_COLUMNS + [LABEL_COLUMN]
    return frame


def main(argv=None):
    parser = argparse.ArgumentParser(description="Make a synthetic (made-up) SARPS training dataset.")
    parser.add_argument("--rows", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)
    if args.rows < 100:
        print("Use at least 100 rows.", file=sys.stderr)
        return 1
    frame = generate(args.rows, args.seed)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.out, index=False)
    share = 1 - frame[LABEL_COLUMN].mean()
    print(f"Wrote {len(frame)} SYNTHETIC students to {args.out} ({share:.0%} At Risk).")
    print("These students are made up. Say so wherever you show results from them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
