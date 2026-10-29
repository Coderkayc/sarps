"""
"""
import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DEV_SECRET = "dev-only-change-me"


def _database_uri():
    """"""
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
    INSTITUTION = os.environ.get("INSTITUTION", "University of Nigeria, Nsukka")

    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}
    if os.environ.get("DB_SSL") == "1":
        import certifi
        SQLALCHEMY_ENGINE_OPTIONS = {**SQLALCHEMY_ENGINE_OPTIONS, "connect_args": {"ssl": {"ca": certifi.where()}}}
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE") == "1"

    MODEL_PATH = os.environ.get(
        "MODEL_PATH", str(BASE_DIR / "ml" / "models" / "sarps_model.joblib")
    )

    TRUST_PROXY = os.environ.get("TRUST_PROXY") == "1" or bool(os.environ.get("VERCEL"))

    CGPA_MAX = float(os.environ.get("CGPA_MAX", "5.0"))

    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID") or None
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET") or None

    MIN_PASSWORD_LENGTH = 8
    PER_PAGE = 20


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite://")
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    GOOGLE_CLIENT_ID = None
    GOOGLE_CLIENT_SECRET = None
    SESSION_COOKIE_SECURE = False
    MODEL_PATH = str(BASE_DIR / "tests" / "no-such-model.joblib")
