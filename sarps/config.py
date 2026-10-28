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
    # Shown on the landing page and footer. Taken from your Lovable design;
    # change it in .env (INSTITUTION=...) if your university is different.
    INSTITUTION = os.environ.get("INSTITUTION", "University of Nigeria, Nsukka")

    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}
    if os.environ.get("DB_SSL") == "1":
        # Hosted MySQL services (TiDB Cloud, Aiven and others) only accept encrypted connections.
        import certifi
        SQLALCHEMY_ENGINE_OPTIONS = {**SQLALCHEMY_ENGINE_OPTIONS, "connect_args": {"ssl": {"ca": certifi.where()}}}

    # Login cookie safety. Set SESSION_COOKIE_SECURE=1 once the site uses HTTPS.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE") == "1"

    # Where the trained model file is expected. It does not exist until you
    # run `python -m ml.train` with your real dataset.
    MODEL_PATH = os.environ.get(
        "MODEL_PATH", str(BASE_DIR / "ml" / "models" / "sarps_model.joblib")
    )

    # Behind a hosting proxy (Vercel, Render, nginx) the app must trust the proxy's "this was https"
    # header, or Google sign-in builds an http:// callback address and Google rejects it.
    # Vercel sets VERCEL automatically; on other hosts set TRUST_PROXY=1.
    TRUST_PROXY = os.environ.get("TRUST_PROXY") == "1" or bool(os.environ.get("VERCEL"))

    # Highest possible CGPA at your university (5.0 or 4.0). This MUST match
    # the scale used in your training dataset.
    CGPA_MAX = float(os.environ.get("CGPA_MAX", "5.0"))

    # The semester the "My courses" and "Plan" pages work on. Change in .env each semester.
    CURRENT_SESSION = os.environ.get("CURRENT_SESSION", "2026/2027")
    CURRENT_SEMESTER = int(os.environ.get("CURRENT_SEMESTER", "1"))

    # Google sign-in. Create an OAuth client in Google Cloud Console (see README) and put
    # its ID and secret in .env. Without them the Google button explains it is not set up.
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID") or None
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET") or None

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
    GOOGLE_CLIENT_ID = None
    GOOGLE_CLIENT_SECRET = None
    SESSION_COOKIE_SECURE = False
    MODEL_PATH = str(BASE_DIR / "tests" / "no-such-model.joblib")