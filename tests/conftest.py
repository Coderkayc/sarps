"""Shared test tools.

IMPORTANT: the synthetic data below exists ONLY so the tests can check that the
training and prediction code works. It is random, made up, and never used by
the real app. Real predictions need your real dataset (see ml/DATASET.md).
"""
import numpy as np
import pandas as pd
import pytest

from config import TestConfig
from ml.train import train_model
from sarps import create_app
from sarps.extensions import db


def write_synthetic_dataset(path, n=300, seed=0):
    """Random made-up students in the model's input format (levels and rates)."""
    rng = np.random.default_rng(seed)
    attendance = rng.integers(0, 7, n)
    assignments = rng.uniform(0, 100, n)
    ca_high = rng.uniform(0, 100, n)
    ca_low = rng.uniform(0, 100, n)
    hours = rng.integers(0, 10, n)
    comfort = rng.integers(1, 6, n)
    impact = rng.integers(1, 6, n)
    cgpa = rng.uniform(1, 5, n)
    score = (0.5 * attendance + 0.02 * assignments + 0.3 * hours + 0.5 * cgpa
             + 0.1 * comfort - 0.1 * impact - 4.5 + rng.normal(0, 1, n))
    frame = pd.DataFrame({
        "attendance_level": attendance,
        "assignment_submission_rate": assignments.round(1),
        "ca_high_rate": ca_high.round(1),
        "ca_low_rate": ca_low.round(1),
        "study_hours_level": hours,
        "financial_comfort": comfort,
        "financial_impact": impact,
        "previous_cgpa": cgpa.round(2),
        "not_at_risk": (score > 0).astype(int),
    })
    # Real students leave some answers out, so the test data does too.
    frame.loc[rng.random(n) < 0.3, "previous_cgpa"] = np.nan
    frame.loc[rng.random(n) < 0.1, "assignment_submission_rate"] = np.nan
    frame.loc[rng.random(n) < 0.1, "ca_high_rate"] = np.nan
    frame.loc[rng.random(n) < 0.1, "ca_low_rate"] = np.nan
    frame.to_csv(path, index=False)
    return frame


@pytest.fixture(scope="session")
def model_file(tmp_path_factory):
    folder = tmp_path_factory.mktemp("model")
    csv = folder / "synthetic_test_data.csv"
    frame = write_synthetic_dataset(csv)
    assert frame["not_at_risk"].nunique() == 2
    out = folder / "test_model.joblib"
    train_model(csv, out)
    return str(out)


def _build(config):
    app = create_app(config)

    # The tests keep one app context open so they can create users directly in
    # the database. Flask then reuses that context for every request, which
    # would let "who is signed in" leak between different test browsers.
    # This forgets the cached user before each request, like a real server would.
    @app.before_request
    def forget_cached_user():
        from flask import g
        g.pop("_login_user", None)

    ctx = app.app_context()
    ctx.push()
    db.create_all()
    return app, ctx


@pytest.fixture
def app():
    """An app with an empty throw-away database and NO trained model."""
    app, ctx = _build(TestConfig)
    yield app
    db.session.remove()
    db.drop_all()
    ctx.pop()


@pytest.fixture
def model_app(model_file):
    """An app with an empty database and a (synthetic, test-only) trained model."""
    config = type("ModelConfig", (TestConfig,), {"MODEL_PATH": model_file})
    app, ctx = _build(config)
    yield app
    db.session.remove()
    db.drop_all()
    ctx.pop()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def model_client(model_app):
    return model_app.test_client()
