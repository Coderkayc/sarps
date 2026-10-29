import argparse
import json
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np

from ml.external_adapter import ExternalModelPipeline
from ml.features import FEATURE_COLUMNS, features_from_inputs, to_frame

OUT = Path(__file__).resolve().parent / "models" / "sarps_demo_model.joblib"


def build_bundle(folder):
    folder = Path(folder)
    for name in ("sarps_model.pkl", "sarps_scaler.pkl", "sarps_imputer.pkl", "model_metadata.json"):
        if not (folder / name).is_file():
            raise SystemExit(f"Missing {name} in {folder}. Run train_model.py there first.")
    with open(folder / "sarps_model.pkl", "rb") as f:
        model = pickle.load(f)
    with open(folder / "sarps_scaler.pkl", "rb") as f:
        scaler = pickle.load(f)
    with open(folder / "sarps_imputer.pkl", "rb") as f:
        imputer = pickle.load(f)
    meta = json.loads((folder / "model_metadata.json").read_text(encoding="utf-8"))
    if meta.get("training_data") != "synthetic_students.csv":
        print("Note: this model's metadata does not say it used the synthetic file. "
              "It is still labelled as a demo model because that is what this importer is for.")
    chosen = meta.get("selected_model", "unknown")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    pipeline = ExternalModelPipeline(scaler, model, imputer["cgpa_median"])
    chosen_scores = meta.get("metrics", {}).get(chosen, {})
    return {
        "pipeline": pipeline,
        "feature_columns": FEATURE_COLUMNS,
        "model_version": f"synthetic-demo-{chosen}-{stamp}",
        "trained_at": stamp,
        "n_rows": meta.get("training_samples", 0) + meta.get("test_samples", 0),
        "unused_features": [],
        "cgpa_max": 5.0,
        "synthetic": True,
        "metrics": {"accuracy": chosen_scores.get("accuracy"), "roc_auc": None,
                    "at_risk_recall": chosen_scores.get("recall")},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", help="the standalone model folder (the one holding the .pkl files)")
    args = parser.parse_args(argv)
    bundle = build_bundle(args.folder)
    weak = features_from_inputs(1, 10, 2, 5, 0, 4, 1, 1, 1, 1.5)
    strong = features_from_inputs(6, 10, 10, 5, 5, 0, 7, 5, 1, 4.6)
    p = bundle["pipeline"].predict_proba(to_frame([weak, strong]))[:, 1] * 100
    if not np.all(np.isfinite(p)):
        raise SystemExit("The model gave an invalid number. Nothing was saved.")
    print(f"Check: weak student -> {p[0]:.1f}% Not at Risk, strong student -> {p[1]:.1f}% Not at Risk")
    if not p[0] < p[1]:
        raise SystemExit("The weak student scored higher than the strong one. Something is wrong; nothing was saved.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, OUT)
    print(f"Saved {OUT}")
    print(f"Version: {bundle['model_version']}")
    print("To use it, put this line in .env and restart the app:")
    print("  MODEL_PATH=ml/models/sarps_demo_model.joblib")
    print("To go back to the real model, delete that line.")


if __name__ == "__main__":
    sys.exit(main())
