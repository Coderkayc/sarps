"""Loads the REAL trained model and turns student inputs into a probability.

If no trained model file exists, this service says so and refuses to predict.
It never invents a number.
"""
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np

from ml.features import FEATURE_COLUMNS, to_frame
from sarps.services.classification import normalise_percent

log = logging.getLogger(__name__)


class PredictionError(Exception):
    """Prediction could not be made."""


class ModelNotAvailable(PredictionError):
    """There is no usable trained model."""


@dataclass
class Prediction:
    prob_not_at_risk: float  # percent, 0-100, two decimals
    model_version: str


class PredictionService:
    def __init__(self):
        self._path = None
        self._bundle = None
        self._stamp = None
        self._error = None
        self._lock = threading.Lock()

    def init_app(self, app):
        self._path = Path(app.config["MODEL_PATH"])
        app.extensions["prediction"] = self

    # The file is re-checked on each use, so a newly trained model is picked up
    # without restarting the app. Re-loading only happens if the file changed.
    def _refresh(self):
        with self._lock:
            try:
                stat = self._path.stat()
            except FileNotFoundError:
                self._bundle, self._stamp, self._error = None, None, None
                return
            stamp = (stat.st_mtime_ns, stat.st_size)
            if stamp == self._stamp:
                return
            self._stamp = stamp
            try:
                bundle = joblib.load(self._path)
                self._validate(bundle)
                self._bundle, self._error = bundle, None
            except Exception as exc:  # a broken file must never crash the website
                log.exception("Could not load the model file")
                self._bundle, self._error = None, str(exc)

    @staticmethod
    def _validate(bundle):
        if not isinstance(bundle, dict) or "pipeline" not in bundle:
            raise ValueError("File is not a SARPS model bundle.")
        if bundle.get("feature_columns") != FEATURE_COLUMNS:
            raise ValueError("Model was trained on different inputs than this app collects.")
        pipeline = bundle["pipeline"]
        if not hasattr(pipeline, "predict_proba"):
            raise ValueError("Model cannot output probabilities.")
        if list(pipeline.classes_) != [0, 1]:
            raise ValueError("Model classes must be exactly 0 (At Risk) and 1 (Not at Risk).")

    def status(self):
        self._refresh()
        if self._bundle is None:
            return {"available": False, "error": self._error}
        return {
            "available": True,
            "error": None,
            "version": self._bundle.get("model_version", "unknown"),
            "trained_at": self._bundle.get("trained_at"),
            "n_rows": self._bundle.get("n_rows"),
            "metrics": self._bundle.get("metrics"),
        }

    def is_available(self):
        return self.status()["available"]

    def predict(self, features):
        """`features` is a dict from ml.features.features_from_inputs."""
        self._refresh()
        if self._bundle is None:
            raise ModelNotAvailable("No trained model is available.")
        try:
            proba = self._bundle["pipeline"].predict_proba(to_frame([features]))[0][1]
        except Exception as exc:
            raise PredictionError(f"Model failed to predict: {exc}") from exc
        if not np.isfinite(proba):
            raise PredictionError("Model returned an invalid probability.")
        return Prediction(
            prob_not_at_risk=normalise_percent(float(proba) * 100),
            model_version=self._bundle.get("model_version", "unknown"),
        )
