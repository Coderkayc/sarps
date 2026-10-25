"""Application settings.

All settings live here. Private values (passwords, secret key) are read from
environment variables or from a local `.env` file, never written in code.
"""
import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DEV_SECRET = "dev-only-change-me"


def _database_uri():
    """Use DATABASE_URL if given, otherwise build a MySQL address from DB_* values."""
    explicit = os.environ.get("DATABASE_URL")
    if explicit:
        return explicit
    user = quote_plus(os.environ.get("DB_USER", "sarps"))
    password = quote_plus(os.environ.get("DB_PASSWORD", ""))
    host = os.environ.get("DB_HOST", "127.0.0.1")
    port = os.environ.get("DB_PORT", "3306")
    name = os.environ.get("DB_NAME", "sarps")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", DEV_SECRET)

    APP_NAME = "SARPS"
    APP_FULL_NAME = "Student Academic Risk Prediction System"

    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    # Login cookie safety. Set SESSION_COOKIE_SECURE=1 once the site uses HTTPS.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE") == "1"

    # Where the trained model file is expected. It does not exist until you
    # run `python -m ml.train` with your real dataset.
    MODEL_PATH = os.environ.get(
        "MODEL_PATH", str(BASE_DIR / "ml" / "models" / "sarps_model.joblib")
    )

    # Highest possible CGPA at your university (5.0 or 4.0). This MUST match
    # the scale used in your training dataset.
    CGPA_MAX = float(os.environ.get("CGPA_MAX", "5.0"))

    MIN_PASSWORD_LENGTH = 8
    PER_PAGE = 20


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret"
    # Tests use a throw-away in-memory database by default. To run the same tests
    # against real MySQL, set TEST_DATABASE_URL to an EMPTY test database
    # (the tests create and delete tables in it, so never point it at real data).
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite://")
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    MODEL_PATH = str(BASE_DIR / "tests" / "no-such-model.joblib")
