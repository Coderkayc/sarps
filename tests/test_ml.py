"""Training pipeline and the prediction service.

The data used here is synthetic and exists only to check the code works.
"""
import joblib
import numpy as np
import pandas as pd
import pytest
from flask import Flask

from ml.features import FEATURE_COLUMNS, features_from_inputs, financial_to_number
from ml.train import DatasetError, load_and_check_dataset, main, train_model
from sarps.services.prediction import ModelNotAvailable, PredictionService
from tests.conftest import write_synthetic_dataset


def service_for(path):
    app = Flask("t")
    app.config["MODEL_PATH"] = str(path)
    service = PredictionService()
    service.init_app(app)
    return service


@pytest.fixture
def csv_path(tmp_path):
    path = tmp_path / "data.csv"
    write_synthetic_dataset(path)
    return path


# ---------- features ----------
def test_features_handle_missing_optionals():
    row = features_from_inputs(80, 70)
    assert row["attendance_pct"] == 80 and row["assignment_completion_pct"] == 70
    assert all(np.isnan(row[c]) for c in ("previous_cgpa", "financial_capability", "study_hours_per_week"))


def test_financial_mapping():
    assert financial_to_number("Low") == 1 and financial_to_number("high") == 3
    assert financial_to_number(2) == 2 and financial_to_number("2") == 2
    assert np.isnan(financial_to_number(None)) and np.isnan(financial_to_number(""))
    for bad in ("rich", 7, "0"):
        with pytest.raises(ValueError):
            financial_to_number(bad)


# ---------- training ----------
def test_training_saves_a_usable_model_with_honest_metrics(csv_path, tmp_path):
    out = tmp_path / "m.joblib"
    bundle = train_model(csv_path, out)
    assert out.exists() and out.with_suffix(".json").exists()
    assert bundle["feature_columns"] == FEATURE_COLUMNS
    assert bundle["positive_class"] == "not_at_risk"
    metrics = bundle["metrics"]
    for key in ("accuracy", "roc_auc", "at_risk_recall", "confusion_matrix", "cv_roc_auc_mean"):
        assert key in metrics
    assert 0.5 < metrics["roc_auc"] <= 1.0  # the synthetic data has real signal to learn


def test_both_algorithms_work(csv_path, tmp_path):
    for algorithm in ("logistic", "forest"):
        train_model(csv_path, tmp_path / f"{algorithm}.joblib", algorithm=algorithm, balanced=True)


def test_prediction_is_a_valid_percentage_and_makes_sense(csv_path, tmp_path):
    out = tmp_path / "m.joblib"
    train_model(csv_path, out)
    service = service_for(out)
    strong = service.predict(features_from_inputs(95, 95, 4.5, "high", 25))
    weak = service.predict(features_from_inputs(30, 20, 1.5, "low", 2))
    assert 0 <= weak.prob_not_at_risk <= 100 and 0 <= strong.prob_not_at_risk <= 100
    assert strong.prob_not_at_risk > weak.prob_not_at_risk
    assert strong.model_version == weak.model_version != "unknown"


def test_prediction_works_with_every_optional_input_missing(csv_path, tmp_path):
    out = tmp_path / "m.joblib"
    train_model(csv_path, out)
    result = service_for(out).predict(features_from_inputs(70, 60))
    assert 0 <= result.prob_not_at_risk <= 100


def test_same_inputs_give_same_prediction(csv_path, tmp_path):
    out = tmp_path / "m.joblib"
    train_model(csv_path, out)
    service = service_for(out)
    features = features_from_inputs(70, 60, 3.0, "medium", 10)
    assert service.predict(features).prob_not_at_risk == service.predict(features).prob_not_at_risk


# ---------- dataset checks ----------
def write(tmp_path, frame):
    path = tmp_path / "bad.csv"
    frame.to_csv(path, index=False)
    return path


def good_frame(tmp_path):
    path = tmp_path / "good.csv"
    return write_synthetic_dataset(path)


@pytest.mark.parametrize("mutate, message", [
    (lambda f: f.drop(columns=["attendance_pct"]), "Missing column"),
    (lambda f: f.assign(not_at_risk=f["not_at_risk"].replace({1: 2})), "only 0 or 1"),
    (lambda f: f.assign(attendance_pct=f["attendance_pct"] + 100), "outside 0-100"),
    (lambda f: f.assign(previous_cgpa=f["previous_cgpa"] + 10), "previous_cgpa"),
    (lambda f: f.assign(financial_capability="rich"), "Unknown financial_capability"),
    (lambda f: f.head(30), "usable rows"),
    (lambda f: f.assign(not_at_risk=0), "'Not at Risk' rows"),
])
def test_bad_datasets_are_refused_with_a_clear_message(tmp_path, mutate, message):
    frame = good_frame(tmp_path)
    with pytest.raises(DatasetError) as error:
        load_and_check_dataset(write(tmp_path, mutate(frame)))
    assert message in str(error.value)


def test_unreadable_file_is_refused(tmp_path):
    with pytest.raises(DatasetError):
        load_and_check_dataset(tmp_path / "nope.csv")


def test_rows_missing_required_inputs_are_dropped_and_reported(tmp_path):
    frame = good_frame(tmp_path)
    frame.loc[:4, "attendance_pct"] = np.nan
    x, y, notes = load_and_check_dataset(write(tmp_path, frame))
    assert len(x) == len(frame) - 5
    assert any("missing attendance" in n for n in notes)


def test_training_command_exit_codes(csv_path, tmp_path, capsys):
    assert main(["--data", str(csv_path), "--out", str(tmp_path / "m.joblib")]) == 0
    assert "at_risk_recall" in capsys.readouterr().out
    assert main(["--data", str(tmp_path / "missing.csv"), "--out", str(tmp_path / "x.joblib")]) == 1


# ---------- the prediction service ----------
def test_no_model_file_means_unavailable_and_no_prediction(tmp_path):
    service = service_for(tmp_path / "absent.joblib")
    assert service.is_available() is False
    with pytest.raises(ModelNotAvailable):
        service.predict(features_from_inputs(80, 70))


def test_corrupt_model_file_does_not_crash(tmp_path):
    path = tmp_path / "bad.joblib"
    path.write_bytes(b"this is not a model")
    service = service_for(path)
    status = service.status()
    assert status["available"] is False and status["error"]
    with pytest.raises(ModelNotAvailable):
        service.predict(features_from_inputs(80, 70))


def test_model_trained_on_other_inputs_is_refused(csv_path, tmp_path):
    out = tmp_path / "m.joblib"
    train_model(csv_path, out)
    bundle = joblib.load(out)
    bundle["feature_columns"] = ["something_else"]
    joblib.dump(bundle, out)
    assert service_for(out).is_available() is False


def test_model_with_wrong_class_order_is_refused(tmp_path):
    from sklearn.linear_model import LogisticRegression
    x = pd.DataFrame(np.random.default_rng(0).uniform(0, 1, (40, 5)), columns=FEATURE_COLUMNS)
    y = np.array([2, 3] * 20)
    path = tmp_path / "odd.joblib"
    joblib.dump({"pipeline": LogisticRegression().fit(x, y), "feature_columns": FEATURE_COLUMNS,
                 "model_version": "odd"}, path)
    assert service_for(path).is_available() is False


def test_new_model_file_is_picked_up_without_restart(csv_path, tmp_path):
    out = tmp_path / "later.joblib"
    service = service_for(out)
    assert service.is_available() is False
    train_model(csv_path, out)
    assert service.is_available() is True
