"""Train the SARPS model from YOUR real dataset.

    python -m ml.train --data path/to/your_dataset.csv

What it does, in plain words:
  1. Reads your CSV and checks it carefully (see ml/DATASET.md for the format).
  2. Sets aside 20% of the students as a "test set" the model never sees while learning.
  3. Teaches the model on the other 80%, then scores it on the test set.
  4. Prints honest results, including how many At Risk students it catches.
  5. Re-teaches the final model on all rows and saves it for the web app.

The saved file goes to ml/models/sarps_model.joblib. The web app notices it
automatically; you do not have to change any code.
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml.features import FEATURE_COLUMNS, LABEL_COLUMN, financial_to_number

import joblib
import warnings

# Expected when --unused is used: that column is intentionally empty.
warnings.filterwarnings("ignore", message="Skipping features without any observed values")

DEFAULT_OUT = Path(__file__).resolve().parent / "models" / "sarps_model.joblib"
MIN_ROWS = 60
MIN_PER_CLASS = 10


class DatasetError(Exception):
    """The dataset has a problem the user must fix. The message says what."""


def load_and_check_dataset(csv_path, cgpa_max=5.0, unused=()):
    """Read the CSV, validate it, and return (features DataFrame, labels Series, notes).

    `unused` lists input columns the dataset does not really contain (for example
    assignment completion). They are blanked out so the model cannot learn from
    them, and they are not required to be filled in.
    """
    unused = list(unused)
    unknown = [c for c in unused if c not in FEATURE_COLUMNS]
    if unknown:
        raise DatasetError(f"Unknown column(s) in --unused: {', '.join(unknown)}.")
    try:
        raw = pd.read_csv(csv_path)
    except Exception as exc:
        raise DatasetError(f"Could not read the CSV file: {exc}")

    raw.columns = [str(c).strip() for c in raw.columns]
    needed = FEATURE_COLUMNS + [LABEL_COLUMN]
    missing = [c for c in needed if c not in raw.columns]
    if missing:
        raise DatasetError(
            f"Missing column(s): {', '.join(missing)}. "
            f"Required columns are: {', '.join(needed)}."
        )

    df = raw[needed].copy()
    notes = []
    for col in unused:
        df[col] = np.nan
        notes.append(f"'{col}' is not in this dataset. The model does not use it.")

    # Convert text to numbers. Anything unreadable becomes blank (NaN) and is reported.
    for col in ["attendance_pct", "assignment_completion_pct", "previous_cgpa",
                "study_hours_per_week", LABEL_COLUMN]:
        before = df[col].notna().sum()
        df[col] = pd.to_numeric(df[col], errors="coerce")
        lost = int(before - df[col].notna().sum())
        if lost:
            notes.append(f"{lost} unreadable value(s) in '{col}' were treated as blank.")
    try:
        df["financial_capability"] = df["financial_capability"].map(financial_to_number)
    except ValueError as exc:
        raise DatasetError(str(exc))

    # Labels must be exactly 0 or 1.
    unlabeled = int(df[LABEL_COLUMN].isna().sum())
    if unlabeled:
        notes.append(f"Dropped {unlabeled} row(s) with no outcome label.")
        df = df[df[LABEL_COLUMN].notna()]
    if not df[LABEL_COLUMN].isin([0, 1]).all():
        raise DatasetError(f"'{LABEL_COLUMN}' must contain only 0 or 1 (1 = Not at Risk, 0 = At Risk).")

    # The two required inputs must be present.
    required = [c for c in ["attendance_pct", "assignment_completion_pct"] if c not in unused]
    required_blank = df[required].isna().any(axis=1)
    if required_blank.any():
        notes.append(f"Dropped {int(required_blank.sum())} row(s) missing a required input ({', '.join(required)}).")
        df = df[~required_blank]

    # Impossible values mean the data has a mistake. Stop instead of guessing.
    problems = []
    for col in required:
        bad = int(((df[col] < 0) | (df[col] > 100)).sum())
        if bad:
            problems.append(f"{bad} row(s) have '{col}' outside 0-100")
    bad = int(((df["previous_cgpa"] < 0) | (df["previous_cgpa"] > cgpa_max)).sum())
    if bad:
        problems.append(f"{bad} row(s) have 'previous_cgpa' outside 0-{cgpa_max}")
    bad = int(((df["study_hours_per_week"] < 0) | (df["study_hours_per_week"] > 100)).sum())
    if bad:
        problems.append(f"{bad} row(s) have 'study_hours_per_week' outside 0-100")
    if problems:
        raise DatasetError("Impossible values found: " + "; ".join(problems) + ". Fix the dataset and try again.")

    counts = df[LABEL_COLUMN].value_counts()
    if len(df) < MIN_ROWS:
        raise DatasetError(f"Only {len(df)} usable rows. At least {MIN_ROWS} are needed for a meaningful model.")
    for value, name in [(0, "At Risk"), (1, "Not at Risk")]:
        if int(counts.get(value, 0)) < MIN_PER_CLASS:
            raise DatasetError(
                f"Only {int(counts.get(value, 0))} '{name}' rows. At least {MIN_PER_CLASS} are needed."
            )

    return df[FEATURE_COLUMNS].astype(float), df[LABEL_COLUMN].astype(int), notes


def build_pipeline(algorithm="logistic", balanced=False, seed=42):
    """Missing values are filled with the median, and the model is told which were missing."""
    weight = "balanced" if balanced else None
    if algorithm == "logistic":
        classifier = LogisticRegression(max_iter=1000, class_weight=weight)
        steps = [("impute", SimpleImputer(strategy="median", add_indicator=True)),
                 ("scale", StandardScaler()), ("model", classifier)]
    elif algorithm == "forest":
        classifier = RandomForestClassifier(n_estimators=300, random_state=seed, class_weight=weight)
        steps = [("impute", SimpleImputer(strategy="median", add_indicator=True)), ("model", classifier)]
    else:
        raise DatasetError(f"Unknown algorithm '{algorithm}'. Use 'logistic' or 'forest'.")
    return Pipeline(steps)


def evaluate(pipeline, x_test, y_test):
    """Score on unseen students, using the same rule as the app (above 50% = Not at Risk)."""
    proba = pipeline.predict_proba(x_test)[:, 1]
    predicted = (proba > 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test, predicted, labels=[0, 1]).ravel()
    return {
        "test_rows": int(len(y_test)),
        "accuracy": round(float(accuracy_score(y_test, predicted)), 4),
        "roc_auc": round(float(roc_auc_score(y_test, proba)), 4),
        "at_risk_recall": round(float(recall_score(y_test, predicted, pos_label=0, zero_division=0)), 4),
        "at_risk_precision": round(float(precision_score(y_test, predicted, pos_label=0, zero_division=0)), 4),
        "not_at_risk_recall": round(float(recall_score(y_test, predicted, pos_label=1, zero_division=0)), 4),
        "f1_not_at_risk": round(float(f1_score(y_test, predicted, pos_label=1, zero_division=0)), 4),
        "confusion_matrix": {"true_at_risk_predicted_at_risk": int(tn),
                             "true_at_risk_predicted_not_at_risk": int(fp),
                             "true_not_at_risk_predicted_at_risk": int(fn),
                             "true_not_at_risk_predicted_not_at_risk": int(tp)},
    }


def train_model(csv_path, out_path=DEFAULT_OUT, algorithm="logistic", balanced=False,
                test_size=0.2, seed=42, cgpa_max=5.0, unused=()):
    """Run the whole training procedure. Returns the saved bundle."""
    x, y, notes = load_and_check_dataset(csv_path, cgpa_max=cgpa_max, unused=unused)

    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=test_size, random_state=seed, stratify=y)

    pipeline = build_pipeline(algorithm, balanced, seed)
    pipeline.fit(x_train, y_train)
    metrics = evaluate(pipeline, x_test, y_test)

    # Cross-validation gives a steadier estimate than a single split.
    folds = int(min(5, y.value_counts().min()))
    if folds >= 2:
        scores = cross_val_score(build_pipeline(algorithm, balanced, seed), x, y,
                                 cv=StratifiedKFold(folds, shuffle=True, random_state=seed),
                                 scoring="roc_auc")
        metrics["cv_roc_auc_mean"] = round(float(scores.mean()), 4)
        metrics["cv_roc_auc_std"] = round(float(scores.std()), 4)
        metrics["cv_folds"] = folds

    # Final model learns from every row, so no student's data is wasted.
    final = build_pipeline(algorithm, balanced, seed)
    final.fit(x, y)

    data_hash = hashlib.sha256(Path(csv_path).read_bytes()).hexdigest()[:8]
    stamp = datetime.now(timezone.utc)
    bundle = {
        "pipeline": final,
        "feature_columns": list(FEATURE_COLUMNS),
        "unused_features": list(unused),
        "cgpa_max": cgpa_max,
        "positive_class": "not_at_risk",
        "model_version": f"{algorithm}-{stamp:%Y%m%d-%H%M%S}-{data_hash}",
        "trained_at": stamp.isoformat(),
        "algorithm": algorithm,
        "balanced": balanced,
        "n_rows": int(len(y)),
        "class_counts": {"at_risk": int((y == 0).sum()), "not_at_risk": int((y == 1).sum())},
        "metrics": metrics,
        "data_notes": notes,
        "sklearn_version": sklearn.__version__,
    }

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temp = out_path.with_suffix(".tmp")
    joblib.dump(bundle, temp)
    os.replace(temp, out_path)  # swap in one step so the app never reads a half-written file
    report = {k: v for k, v in bundle.items() if k != "pipeline"}
    out_path.with_suffix(".json").write_text(json.dumps(report, indent=2))
    return bundle


def main(argv=None):
    from config import Config

    parser = argparse.ArgumentParser(description="Train the SARPS risk model from a real dataset.")
    parser.add_argument("--data", required=True, help="Path to your dataset CSV (see ml/DATASET.md)")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Where to save the model")
    parser.add_argument("--algorithm", choices=["logistic", "forest"], default="logistic")
    parser.add_argument("--balanced", action="store_true",
                        help="Give the smaller class more weight (useful if At Risk students are rare)")
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cgpa-max", type=float, default=Config.CGPA_MAX)
    parser.add_argument("--unused", nargs="*", default=[], metavar="COLUMN",
                        help="Input columns missing from your dataset, e.g. assignment_completion_pct")
    args = parser.parse_args(argv)

    try:
        bundle = train_model(args.data, args.out, args.algorithm, args.balanced,
                             args.test_size, args.seed, args.cgpa_max, args.unused)
    except DatasetError as exc:
        print(f"\nDataset problem: {exc}", file=sys.stderr)
        return 1

    print(f"\nModel saved to {args.out}")
    print(f"Version: {bundle['model_version']}")
    print(f"Rows used: {bundle['n_rows']}  {bundle['class_counts']}")
    for note in bundle["data_notes"]:
        print(f"Note: {note}")
    print("\nResults on students the model never saw during learning:")
    print(json.dumps(bundle["metrics"], indent=2))
    print("\nRead 'at_risk_recall' first: it is the share of truly At Risk students the model catches.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
