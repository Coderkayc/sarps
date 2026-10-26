"""Convert the public IUBAT dataset (Mendeley Data, CC BY 4.0) into SARPS training format.

Source: "Dataset on Academic Performance of Computer Science Students at Selected
Universities in Bangladesh", file IUBAT_Student_Performance_Dataset.csv.

    python -m ml.prepare_iubat --raw path/to/IUBAT_Student_Performance_Dataset.csv --out ml/data/iubat_training.csv

Every choice below is a judgement call. State them in your project report.

  not_at_risk                 1 if the student answered "No" to "Did you ever fall in
                              probation?", 0 if "Yes". Probation is a real academic outcome.
  attendance_pct              "Average attendance on class (Percentage)", used as is (0-100).
  assignment_completion_pct   NOT IN THIS DATASET. Left blank. Train with
                              --unused assignment_completion_pct so the model ignores it.
  previous_cgpa               "current CGPA" (the student's cumulative GPA at survey time, which
                              is what a student would enter as their previous CGPA).
                              Blank if 0 (first-semester students have none) or above the
                              dataset's 4.0 scale (typing errors such as 310). Multiplied by
                              (cgpa_max / 4.0) to move it to your university's scale.
  financial_capability        PROXY from monthly family income (BDT): lowest third = low,
                              middle third = medium, top third = high. Income of 0 = blank.
  study_hours_per_week        daily study hours x 7. Blank if daily hours are above 16.
"""
import argparse
import sys

import pandas as pd

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
    out["attendance_pct"] = pd.to_numeric(raw[att], errors="coerce")
    out["assignment_completion_pct"] = float("nan")

    cgpa = pd.to_numeric(raw[cg], errors="coerce")
    cgpa = cgpa.where((cgpa > 0) & (cgpa <= SOURCE_CGPA_MAX))
    out["previous_cgpa"] = (cgpa * (cgpa_max / SOURCE_CGPA_MAX)).round(2)

    income = pd.to_numeric(raw[inc], errors="coerce")
    income = income.where(income > 0)
    low, high = income.quantile([1 / 3, 2 / 3])
    out["financial_capability"] = pd.cut(income, [-float("inf"), low, high, float("inf")],
                                         labels=["low", "medium", "high"]).astype("object")

    daily = pd.to_numeric(raw[hrs], errors="coerce")
    daily = daily.where((daily >= 0) & (daily <= 16))
    out["study_hours_per_week"] = daily * 7

    out = out.dropna(subset=["not_at_risk", "attendance_pct"])
    out["not_at_risk"] = out["not_at_risk"].astype(int)
    columns = ["attendance_pct", "assignment_completion_pct", "previous_cgpa",
               "financial_capability", "study_hours_per_week", "not_at_risk"]
    return out[columns], {"income_low_cut": float(low), "income_high_cut": float(high)}


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
    print(f"Income cut-offs used for low/medium/high: {cuts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
