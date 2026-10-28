"""The synthetic-data demo model: translation rules, honesty banners, and that it really predicts.

The "standalone" model files built here are random and made up. They exist only so the tests
can check that the wrapper works.
"""
import json
import pickle

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from config import TestConfig
from ml.external_adapter import STANDALONE_COLUMNS, translate_row
from ml.features import features_from_inputs
from ml.import_external_model import build_bundle
from sarps.extensions import db
from tests.conftest import _build
from tests.helpers import VALID_ASSESSMENT, count_assessments, login, make_department, make_student
import joblib


@pytest.fixture(scope="module")
def standalone_folder(tmp_path_factory):
    folder = tmp_path_factory.mktemp("standalone")
    rng = np.random.default_rng(1)
    n = 400
    latent = rng.uniform(0, 1, n)
    frame = pd.DataFrame({
        "attendance_pct": latent * 100, "submission_rate": latent,
        "test_performance_score": latent, "study_hours_midpoint": latent * 40,
        "financial_composite": 1 + latent * 4, "cgpa": 0.5 + latent * 4.5})
    at_risk = (latent + rng.normal(0, 0.1, n) < 0.45).astype(int)
    scaler = StandardScaler().fit(frame)
    model = RandomForestClassifier(n_estimators=30, random_state=0).fit(scaler.transform(frame), at_risk)
    for name, obj in (("sarps_model.pkl", model), ("sarps_scaler.pkl", scaler),
                      ("sarps_imputer.pkl", {"cgpa_median": 2.9})):
        with open(folder / name, "wb") as f:
            pickle.dump(obj, f)
    (folder / "model_metadata.json").write_text(json.dumps({
        "selected_model": "random_forest", "training_data": "synthetic_students.csv",
        "metrics": {"random_forest": {"accuracy": 0.97, "recall": 0.92}},
        "training_samples": 400, "test_samples": 100}))
    return folder


@pytest.fixture(scope="module")
def demo_file(standalone_folder, tmp_path_factory):
    out = tmp_path_factory.mktemp("demo") / "demo.joblib"
    joblib.dump(build_bundle(standalone_folder), out)
    return str(out)


def row(**kw):
    base = dict(attendance_level=4, assignments_assigned=10, assignments_submitted=8, tests_done=4,
                tests_high=2, tests_low=1, study_hours_level=3, financial_comfort=3,
                financial_impact=2, previous_cgpa=3.5)
    base.update(kw)
    return features_from_inputs(base["attendance_level"], base["assignments_assigned"],
                                base["assignments_submitted"], base["tests_done"], base["tests_high"],
                                base["tests_low"], base["study_hours_level"], base["financial_comfort"],
                                base["financial_impact"], base["previous_cgpa"])


def test_translation_rules():
    values = dict(zip(STANDALONE_COLUMNS, translate_row(row(), 2.9)))
    assert values["attendance_pct"] == 70.0          # band 61-80% -> its middle
    assert values["submission_rate"] == pytest.approx(0.8)
    assert values["test_performance_score"] == pytest.approx(0.5 + (0.5 - 0.25) / 2)
    assert values["study_hours_midpoint"] == 12.5
    assert values["cgpa"] == 3.5


def test_financial_impact_is_flipped_so_that_money_problems_lower_the_score():
    often_affected = dict(zip(STANDALONE_COLUMNS, translate_row(row(financial_impact=5), 2.9)))
    never_affected = dict(zip(STANDALONE_COLUMNS, translate_row(row(financial_impact=1), 2.9)))
    assert often_affected["financial_composite"] < never_affected["financial_composite"]
    assert never_affected["financial_composite"] == (3 + 5) / 2


def test_blank_answers_become_neutral_never_zero():
    values = dict(zip(STANDALONE_COLUMNS, translate_row(
        row(assignments_assigned=0, assignments_submitted=0, tests_done=0, tests_high=0, tests_low=0,
            previous_cgpa=None), 2.9)))
    assert values["submission_rate"] == 0.5
    assert values["test_performance_score"] == 0.5
    assert values["cgpa"] == 2.9


def test_bundle_is_marked_synthetic_and_predicts_in_the_right_order(demo_file):
    bundle = joblib.load(demo_file)
    assert bundle["synthetic"] is True and bundle["model_version"].startswith("synthetic-demo")
    from ml.features import to_frame
    weak = row(attendance_level=1, assignments_submitted=1, tests_high=0, tests_low=4,
               study_hours_level=1, financial_comfort=1, financial_impact=5, previous_cgpa=1.2)
    strong = row(attendance_level=6, assignments_submitted=10, tests_high=4, tests_low=0,
                 study_hours_level=8, financial_comfort=5, financial_impact=1, previous_cgpa=4.7)
    p = bundle["pipeline"].predict_proba(to_frame([weak, strong]))[:, 1]
    assert p[0] < 0.5 < p[1]
    assert list(bundle["pipeline"].classes_) == [0, 1]


@pytest.fixture
def demo_client(demo_file):
    config = type("DemoConfig", (TestConfig,), {"MODEL_PATH": demo_file})
    app, ctx = _build(config)
    yield app.test_client(), app
    db.session.remove()
    db.drop_all()
    ctx.pop()


def test_the_site_states_plainly_that_the_training_data_is_synthetic(demo_client):
    client, app = demo_client
    assert b"DEMO MODEL" not in client.get("/login").data         # no alarming banner
    assert b"trained on synthetic data" in client.get("/assumptions").data  # but the fact is still stated
    assert b"synthetic (generated) students" in client.get("/assumptions").data
    assert b"IUBAT" not in client.get("/assumptions").data.split(b"How each answer")[0]


def test_a_submission_works_and_the_result_is_labelled_demo(demo_client):
    client, app = demo_client
    make_student("stu@x.com", make_department())
    login(client, "stu@x.com")
    response = client.post("/student/assess", data=dict(VALID_ASSESSMENT), follow_redirects=True)
    assert response.status_code == 200
    assert count_assessments() == 1
    assert b"Demo result" not in response.data
    assert b"synthetic-demo" in response.data
    assert b"trained on synthetic data" in response.data


def test_the_real_model_shows_no_demo_banner(model_app, model_client):
    assert b"DEMO MODEL" not in model_client.get("/").data
