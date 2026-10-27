"""Training pipeline and the prediction service.

The data used here is synthetic and exists only to check the code works.
"""
import joblib
import numpy as np
import pandas as pd
import pytest
from flask import Flask

from ml.features import (ATTENDANCE_OPTIONS, FEATURE_COLUMNS, FINANCIAL_COMFORT_OPTIONS, FINANCIAL_IMPACT_OPTIONS,
                         STUDY_HOURS_OPTIONS, attendance_level_from_pct, features_from_inputs,
                         study_level_from_weekly_hours)
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
def feat(attendance=4, assigned=5, submitted=4, done=4, high=1, low=1, study=3, comfort=3, impact=2, cgpa=3.5):
    return features_from_inputs(attendance, assigned, submitted, done, high, low, study, comfort, impact, cgpa)


def test_rates_are_computed_from_the_counts():
    row = feat(assigned=5, submitted=4, done=10, high=3, low=2)
    assert row["assignment_submission_rate"] == 80
    assert row["ca_high_rate"] == 30 and row["ca_low_rate"] == 20


def test_zero_assigned_or_zero_tests_is_missing_not_a_crash_and_not_zero():
    row = feat(assigned=0, submitted=0, done=0, high=0, low=0, cgpa=None)
    for name in ("assignment_submission_rate", "ca_high_rate", "ca_low_rate", "previous_cgpa"):
        assert np.isnan(row[name]), name


def test_attendance_bands_match_the_dropdown():
    pairs = [(0, 0), (1, 1), (20, 1), (21, 2), (40, 2), (41, 3), (60, 3), (61, 4), (80, 4), (81, 5), (95, 5),
             (96, 6), (100, 6)]
    for percent, level in pairs:
        assert attendance_level_from_pct(percent) == level, percent
    assert np.isnan(attendance_level_from_pct(101)) and np.isnan(attendance_level_from_pct(-1))


def test_study_hour_bands_match_the_dropdown():
    pairs = [(0, 0), (0.5, 1), (4.9, 1), (5, 2), (10, 2), (10.1, 3), (15, 3), (20, 4), (25, 5), (30, 6),
             (35, 7), (40, 8), (40.1, 9), (80, 9)]
    for hours, level in pairs:
        assert study_level_from_weekly_hours(hours) == level, hours


def test_dropdown_wording_is_exactly_as_specified():
    assert [t for _, t in ATTENDANCE_OPTIONS] == [
        "Never (0%)", "Very Rarely (1\u201320%)", "Rarely (21\u201340%)", "A Few Times (41\u201360%)",
        "Often (61\u201380%)", "Most of the Time (81\u201395%)", "I Attend Every Class (96\u2013100%)"]
    assert [t for _, t in STUDY_HOURS_OPTIONS] == [
        "0 hours (I do not study outside class)", "Below 5 hours", "5\u201310 hours", "10\u201315 hours",
        "15\u201320 hours", "20\u201325 hours", "25\u201330 hours", "30\u201335 hours", "35\u201340 hours",
        "Over 40 hours"]
    assert [t for _, t in FINANCIAL_COMFORT_OPTIONS] == [
        "Very Comfortable", "Comfortable", "Fairly Comfortable", "Somewhat Struggling", "Severely Struggling"]
    assert [t for _, t in FINANCIAL_IMPACT_OPTIONS] == [
        "Never affects me", "Rarely affects me", "Sometimes affects me", "Often affects me",
        "Almost always affects me"]


def test_encodings_move_in_the_expected_direction():
    # more comfortable = higher number; more impact = higher number; more attendance = higher level
    assert dict(FINANCIAL_COMFORT_OPTIONS)[5] == "Very Comfortable" and dict(FINANCIAL_COMFORT_OPTIONS)[1] == "Severely Struggling"
    assert dict(FINANCIAL_IMPACT_OPTIONS)[1] == "Never affects me" and dict(FINANCIAL_IMPACT_OPTIONS)[5] == "Almost always affects me"
    assert dict(ATTENDANCE_OPTIONS)[0].startswith("Never") and dict(ATTENDANCE_OPTIONS)[6].startswith("I Attend Every")


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
    strong = service.predict(feat(attendance=6, assigned=10, submitted=10, done=5, high=4, low=0, study=7, comfort=5, impact=1, cgpa=4.5))
    weak = service.predict(feat(attendance=1, assigned=10, submitted=2, done=5, high=0, low=4, study=1, comfort=1, impact=5, cgpa=1.5))
    assert 0 <= weak.prob_not_at_risk <= 100 and 0 <= strong.prob_not_at_risk <= 100
    assert strong.prob_not_at_risk > weak.prob_not_at_risk
    assert strong.model_version == weak.model_version != "unknown"


def test_prediction_works_with_every_optional_input_missing(csv_path, tmp_path):
    out = tmp_path / "m.joblib"
    train_model(csv_path, out)
    result = service_for(out).predict(feat(assigned=0, submitted=0, done=0, high=0, low=0, cgpa=None))
    assert 0 <= result.prob_not_at_risk <= 100


def test_same_inputs_give_same_prediction(csv_path, tmp_path):
    out = tmp_path / "m.joblib"
    train_model(csv_path, out)
    service = service_for(out)
    features = feat(cgpa=3.0)
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
    (lambda f: f.drop(columns=["attendance_level"]), "Missing column"),
    (lambda f: f.assign(not_at_risk=f["not_at_risk"].replace({1: 2})), "only 0 or 1"),
    (lambda f: f.assign(attendance_level=f["attendance_level"] + 10), "attendance_level"),
    (lambda f: f.assign(ca_high_rate=f["ca_high_rate"] + 200), "outside 0-100"),
    (lambda f: f.assign(previous_cgpa=f["previous_cgpa"] + 10), "previous_cgpa"),
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
    frame.loc[:4, "attendance_level"] = np.nan
    x, y, notes = load_and_check_dataset(write(tmp_path, frame))
    assert len(x) == len(frame) - 5
    assert any("missing a required input" in n and "attendance_level" in n for n in notes)


def test_training_command_exit_codes(csv_path, tmp_path, capsys):
    assert main(["--data", str(csv_path), "--out", str(tmp_path / "m.joblib")]) == 0
    assert "at_risk_recall" in capsys.readouterr().out
    assert main(["--data", str(tmp_path / "missing.csv"), "--out", str(tmp_path / "x.joblib")]) == 1


# ---------- the prediction service ----------
def test_no_model_file_means_unavailable_and_no_prediction(tmp_path):
    service = service_for(tmp_path / "absent.joblib")
    assert service.is_available() is False
    with pytest.raises(ModelNotAvailable):
        service.predict(feat())


def test_corrupt_model_file_does_not_crash(tmp_path):
    path = tmp_path / "bad.joblib"
    path.write_bytes(b"this is not a model")
    service = service_for(path)
    status = service.status()
    assert status["available"] is False and status["error"]
    with pytest.raises(ModelNotAvailable):
        service.predict(feat())


def test_model_trained_on_other_inputs_is_refused(csv_path, tmp_path):
    out = tmp_path / "m.joblib"
    train_model(csv_path, out)
    bundle = joblib.load(out)
    bundle["feature_columns"] = ["something_else"]
    joblib.dump(bundle, out)
    assert service_for(out).is_available() is False


def test_model_with_wrong_class_order_is_refused(tmp_path):
    from sklearn.linear_model import LogisticRegression
    x = pd.DataFrame(np.random.default_rng(0).uniform(0, 1, (40, len(FEATURE_COLUMNS))), columns=FEATURE_COLUMNS)
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


# ---- training without an input the dataset does not have (e.g. assignments) ----
UNUSED = ["assignment_submission_rate", "ca_high_rate", "ca_low_rate", "financial_impact"]


def _csv_without_some_inputs(tmp_path):
    frame = write_synthetic_dataset(tmp_path / "full.csv")
    for column in UNUSED:
        frame[column] = np.nan
    path = tmp_path / "partial.csv"
    frame.to_csv(path, index=False)
    return path


def test_unused_input_is_recorded_and_cannot_change_the_result(tmp_path):
    out = tmp_path / "m.joblib"
    bundle = train_model(_csv_without_some_inputs(tmp_path), out, unused=UNUSED)
    assert bundle["unused_features"] == UNUSED
    service = service_for(out)
    low = service.predict(feat(assigned=10, submitted=0, done=10, high=0, low=10, impact=5))
    high = service.predict(feat(assigned=10, submitted=10, done=10, high=10, low=0, impact=1))
    assert low.prob_not_at_risk == high.prob_not_at_risk
    assert service.status()["unused_features"] == UNUSED


def test_a_model_that_uses_an_input_does_react_to_it(csv_path, tmp_path):
    out = tmp_path / "m.joblib"
    train_model(csv_path, out)
    service = service_for(out)
    assert service.predict(feat(attendance=6)).prob_not_at_risk > service.predict(feat(attendance=0)).prob_not_at_risk


def test_unknown_unused_column_is_rejected(tmp_path):
    with pytest.raises(DatasetError):
        train_model(_csv_without_some_inputs(tmp_path), tmp_path / "m.joblib", unused=["nonsense"])


def test_model_with_different_cgpa_scale_is_refused(tmp_path):
    out = tmp_path / "m.joblib"
    train_model(_csv_without_some_inputs(tmp_path), out, unused=UNUSED, cgpa_max=5.0)
    app = Flask("t")
    app.config.update(MODEL_PATH=str(out), CGPA_MAX=4.0)
    service = PredictionService()
    service.init_app(app)
    status = service.status()
    assert not status["available"] and "CGPA" in status["error"]
