"""Convert the public IUBAT dataset (Mendeley Data, CC BY 4.0) into SARPS training format.

Source: "Dataset on Academic Performance of Computer Science Students at Selected
Universities in Bangladesh", file IUBAT_Student_Performance_Dataset.csv.

    python -m ml.prepare_iubat --raw path/to/IUBAT_Student_Performance_Dataset.csv --out ml/data/iubat_training.csv

Every choice below is a judgement call. State them in your project report.

  not_at_risk                 1 if the student answered "No" to "Did you ever fall in
                              probation?", 0 if "Yes". Probation is a real academic outcome.
  attendance_level            "Average attendance on class (Percentage)" put into the same 7 bands
                              as the form dropdown (0, 1-20, 21-40, 41-60, 61-80, 81-95, 96-100).
  study_hours_level           daily study hours x 7, put into the same 10 bands as the form.
                              Blank if daily hours are above 16 (typing errors such as 30).
  financial_comfort           PROXY from monthly family income (BDT): the sample is split into five
                              equal groups, lowest income = 1 (severely struggling) up to
                              highest = 5 (very comfortable). Income of 0 = blank.
  previous_cgpa               "current CGPA" (the student's cumulative GPA at survey time, which
                              is what a student would enter as their CGPA). Blank if 0 (first-semester
                              students have none) or above the dataset's 4.0 scale (typing errors such
                              as 310). Multiplied by (cgpa_max / 4.0) to move it to your scale.
  assignment_submission_rate,
  ca_high_rate, ca_low_rate,
  financial_impact            NOT IN THIS DATASET. Left blank. Train with
                              --unused assignment_submission_rate ca_high_rate ca_low_rate financial_impact
                              so the model ignores them.
"""
import argparse
import sys

import pandas as pd

from ml.features import (FEATURE_COLUMNS, attendance_level_from_pct,
                         study_level_from_weekly_hours)

SOURCE_CGPA_MAX = 4.0


def find(df, keyword):
    matches = [c for c in df.columns if keyword.lower() in c.lower()]
    if len(matches) != 1:
        raise SystemExit(f"Expected exactly one column containing '{keyword}', found {matches}.")
    return matches[0]


def prepare(raw_csv, cgpa_max=5.0):
    raw = pd.read_csv(raw_csv)
    att, cg = find(raw, "Average attendance"), find(raw, "current CGPA")
    prob, hrs, inc = find(raw, "probation"), find(raw, "study daily"), find(raw, "Family Income")

    out = pd.DataFrame(index=raw.index)
    answer = raw[prob].astype(str).str.strip().str.lower()
    out["not_at_risk"] = answer.map({"no": 1, "yes": 0})
    out["attendance_level"] = pd.to_numeric(raw[att], errors="coerce").map(attendance_level_from_pct)

    daily = pd.to_numeric(raw[hrs], errors="coerce")
    daily = daily.where((daily >= 0) & (daily <= 16))
    out["study_hours_level"] = (daily * 7).map(study_level_from_weekly_hours)

    income = pd.to_numeric(raw[inc], errors="coerce")
    income = income.where(income > 0)
    groups = pd.qcut(income.dropna().rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
    out["financial_comfort"] = groups.astype(float).reindex(raw.index)
    edges = income.quantile([0.2, 0.4, 0.6, 0.8]).tolist()

    cgpa = pd.to_numeric(raw[cg], errors="coerce")
    cgpa = cgpa.where((cgpa > 0) & (cgpa <= SOURCE_CGPA_MAX))
    out["previous_cgpa"] = (cgpa * (cgpa_max / SOURCE_CGPA_MAX)).round(2)

    for column in ("assignment_submission_rate", "ca_high_rate", "ca_low_rate", "financial_impact"):
        out[column] = float("nan")

    out = out.dropna(subset=["not_at_risk", "attendance_level"])
    out["not_at_risk"] = out["not_at_risk"].astype(int)
    return out[FEATURE_COLUMNS + ["not_at_risk"]], {"income_quintile_edges": edges}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--cgpa-max", type=float, default=5.0, help="Your university's CGPA scale")
    args = parser.parse_args(argv)
    data, cuts = prepare(args.raw, args.cgpa_max)
    data.to_csv(args.out, index=False)
    print(f"Wrote {len(data)} rows to {args.out}")
    print(f"Not at Risk (no probation): {int(data.not_at_risk.sum())}, At Risk (probation): {int((data.not_at_risk == 0).sum())}")
    print(f"Blank counts: {data.isna().sum().to_dict()}")
    print(f"Income cut-offs used for the five comfort groups: {cuts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
