"""The synthetic full-feature dataset and the model shipped from it."""
from pathlib import Path

import joblib
import numpy as np
import pytest

from config import TestConfig
from ml.features import FEATURE_COLUMNS, features_from_inputs
from ml.make_synthetic import generate
from ml.train import load_and_check_dataset, train_model
from sarps.extensions import db
from tests.conftest import _build
from tests.helpers import VALID_ASSESSMENT, login, make_department, make_student

SHIPPED = Path(__file__).resolve().parents[1] / "ml" / "models" / "sarps_model.joblib"


@pytest.fixture(scope="module")
def csv_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("syn") / "synthetic.csv"
    generate(1500, seed=3).to_csv(path, index=False)
    return path


def test_dataset_passes_the_same_checks_as_real_data(csv_path):
    x, y, notes = load_and_check_dataset(csv_path)
    assert list(x.columns) == FEATURE_COLUMNS
    assert 0.2 < 1 - y.mean() < 0.4                  # roughly 30% At Risk
    for column in FEATURE_COLUMNS:                   # every input genuinely varies
        assert x[column].nunique() > 3, column


def test_blanks_exist_where_real_students_have_them(csv_path):
    x, _, _ = load_and_check_dataset(csv_path)
    assert x["previous_cgpa"].isna().mean() > 0.1
    assert x["assignment_submission_rate"].isna().any()


def test_same_seed_gives_the_same_students():
    assert generate(300, seed=5).equals(generate(300, seed=5))
    assert not generate(300, seed=5).equals(generate(300, seed=6))


def test_training_uses_every_input_and_marks_the_model_synthetic(csv_path, tmp_path):
    bundle = train_model(csv_path, tmp_path / "m.joblib", balanced=True, synthetic=True)
    assert bundle["synthetic"] is True and bundle["model_version"].startswith("synthetic-")
    assert bundle["unused_features"] == []
    weights = dict(zip(FEATURE_COLUMNS, bundle["pipeline"].named_steps["model"].coef_[0][:8]))
    assert weights["previous_cgpa"] > 0 and weights["attendance_level"] > 0
    assert weights["financial_impact"] < 0           # money affecting school lowers the score
    assert weights["ca_high_rate"] > weights["ca_low_rate"]
    assert bundle["metrics"]["roc_auc"] < 0.97       # not a model that merely memorised a rule


def test_real_training_is_not_marked_synthetic(csv_path, tmp_path):
    bundle = train_model(csv_path, tmp_path / "m.joblib")
    assert bundle["synthetic"] is False and not bundle["model_version"].startswith("synthetic-")


def test_several_files_can_be_stacked_for_later_retraining(tmp_path):
    first, second = tmp_path / "a.csv", tmp_path / "b.csv"
    generate(400, seed=1).to_csv(first, index=False)
    generate(300, seed=2).to_csv(second, index=False)
    bundle = train_model([first, second], tmp_path / "m.joblib")
    assert bundle["n_rows"] == 700


def test_the_shipped_default_model_is_the_full_synthetic_one():
    bundle = joblib.load(SHIPPED)
    assert bundle["synthetic"] is True and bundle["unused_features"] == []
    assert bundle["feature_columns"] == FEATURE_COLUMNS
    from ml.features import to_frame
    weak = features_from_inputs(1, 10, 2, 5, 0, 4, 1, 1, 5, 1.5)
    strong = features_from_inputs(6, 10, 10, 5, 5, 0, 7, 5, 1, 4.6)
    p = bundle["pipeline"].predict_proba(to_frame([weak, strong]))[:, 1]
    assert p[0] < 0.5 < p[1]


def test_the_template_for_real_data_has_the_right_header():
    header = (Path(__file__).resolve().parents[1] / "ml" / "data" / "real_students_template.csv").read_text().strip()
    assert header.split(",") == FEATURE_COLUMNS + ["not_at_risk"]


def test_all_inputs_count_and_the_result_says_demo():
    config = type("ShippedConfig", (TestConfig,), {"MODEL_PATH": str(SHIPPED)})
    app, ctx = _build(config)
    try:
        client = app.test_client()
        make_student("stu@x.com", make_department())
        login(client, "stu@x.com")
        response = client.post("/student/assess", data=dict(VALID_ASSESSMENT), follow_redirects=True)
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "Demo result" in html and "DEMO MODEL" in html
        assert "not used by the current model" not in html     # nothing is ignored now
    finally:
        db.session.remove()
        db.drop_all()
        ctx.pop()
