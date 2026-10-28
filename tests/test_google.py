"""Sign in with Google. Google itself is replaced by a stand-in that returns what Google returns."""
import pytest
from authlib.integrations.base_client import OAuthError
from flask import redirect
from sqlalchemy import select

from sarps.constants import Role
from sarps.extensions import db
from sarps.models import User
from tests.helpers import login, make_department, make_user, make_student

INFO = {"sub": "g-123", "email": "Ada.Obi@Gmail.com", "email_verified": True, "name": "Ada Obi"}


class FakeGoogle:
    def __init__(self, info=INFO, error=False):
        self.info, self.error, self.redirect_uri = info, error, None

    def authorize_redirect(self, redirect_uri):
        self.redirect_uri = redirect_uri
        return redirect("https://accounts.google.com/o/oauth2/v2/auth?fake=1")

    def authorize_access_token(self):
        if self.error:
            raise OAuthError("access_denied")
        return {"userinfo": self.info}


@pytest.fixture
def google(app, client, monkeypatch):
    """Google switched on, with a stand-in client the test can control."""
    app.config["GOOGLE_CLIENT_ID"], app.config["GOOGLE_CLIENT_SECRET"] = "id", "secret"
    fake = FakeGoogle()
    monkeypatch.setattr("sarps.routes.auth.google_client", lambda: fake)
    fake.client = client
    return fake


def signed_in(client):
    return client.get("/student/").status_code == 200


# ---------- buttons are on both pages ----------
def test_google_button_on_login_and_register_pages(client):
    make_department()
    assert "Sign in with Google" in client.get("/login").get_data(as_text=True)
    assert "Sign up with Google" in client.get("/register").get_data(as_text=True)


# ---------- not configured: honest, no crash ----------
def test_not_configured_explains_instead_of_pretending(client):
    response = client.get("/auth/google", follow_redirects=True)
    html = response.get_data(as_text=True)
    assert "not set up on this server yet" in html
    assert client.get("/auth/google/callback", follow_redirects=True).status_code == 200


# ---------- the redirect to Google ----------
def test_login_redirects_to_google_with_our_callback(google, client):
    response = client.get("/auth/google")
    assert response.status_code == 302 and response.headers["Location"].startswith("https://accounts.google.com/")
    assert google.redirect_uri.endswith("/auth/google/callback")


# ---------- existing accounts ----------
def test_existing_student_is_signed_in_by_verified_email(google, client):
    student = make_student("ada.obi@gmail.com", make_department())
    response = client.get("/auth/google/callback")
    assert response.status_code == 302 and response.headers["Location"].endswith("/student/")
    assert signed_in(client)
    assert db.session.get(User, student.id).google_sub == "g-123"      # linked for next time


def test_staff_account_can_use_google_too(google, client):
    make_user(Role.ADVISER, "ada.obi@gmail.com")
    response = client.get("/auth/google/callback")
    assert response.headers["Location"].endswith("/staff/")


def test_returning_user_is_found_by_google_id_even_if_email_changed(google, client):
    student = make_student("old@x.com", make_department())
    student.google_sub = "g-123"
    db.session.commit()
    assert client.get("/auth/google/callback").headers["Location"].endswith("/student/")


def test_deactivated_account_cannot_sign_in(google, client):
    student = make_student("ada.obi@gmail.com", make_department())
    student.active = False
    db.session.commit()
    html = client.get("/auth/google/callback", follow_redirects=True).get_data(as_text=True)
    assert "deactivated" in html and not signed_in(client)


def test_account_linked_to_another_google_id_is_refused(google, client):
    student = make_student("ada.obi@gmail.com", make_department())
    student.google_sub = "someone-else"
    db.session.commit()
    html = client.get("/auth/google/callback", follow_redirects=True).get_data(as_text=True)
    assert "different Google account" in html and not signed_in(client)


@pytest.mark.parametrize("info", [
    {**INFO, "email_verified": False},
    {**INFO, "email_verified": "true"},          # must be the real boolean True
    {**INFO, "email": ""},
    {**INFO, "sub": ""},
    {},
])
def test_unverified_or_incomplete_google_answers_are_refused(google, client, info):
    make_student("ada.obi@gmail.com", make_department())
    google.info = info
    html = client.get("/auth/google/callback", follow_redirects=True).get_data(as_text=True)
    assert "did not confirm your email" in html and not signed_in(client)


def test_cancelled_google_sign_in_is_handled(google, client):
    google.error = True
    response = client.get("/auth/google/callback", follow_redirects=True)
    assert "cancelled or could not be completed" in response.get_data(as_text=True)


# ---------- new accounts ----------
def test_new_person_completes_profile_and_gets_a_student_account(google, client):
    dept = make_department()
    response = client.get("/auth/google/callback")
    assert response.headers["Location"].endswith("/auth/google/profile")
    page = client.get("/auth/google/profile").get_data(as_text=True)
    assert "ada.obi@gmail.com" in page and 'value="Ada Obi"' in page
    response = client.post("/auth/google/profile", data={
        "full_name": "Ada Obi", "matric_number": "csc/2022/014", "department_id": str(dept.id)})
    assert response.status_code == 302 and signed_in(client)
    user = db.session.scalar(select(User).where(User.email == "ada.obi@gmail.com"))
    assert user.role == Role.STUDENT and user.matric_number == "CSC/2022/014"
    assert user.google_sub == "g-123" and user.department_id == dept.id
    assert not user.check_password("")                               # no usable password
    fresh = client.application.test_client()                           # a different browser
    assert "Incorrect email or password" in login(fresh, "ada.obi@gmail.com", "anything", follow_redirects=True).get_data(as_text=True)


def test_profile_page_needs_a_google_sign_in_first(client):
    response = client.get("/auth/google/profile", follow_redirects=True)
    assert "start again with the Google button" in response.get_data(as_text=True)
    assert client.post("/auth/google/profile", data={"full_name": "x"}).status_code == 302


def test_profile_rejects_duplicate_matric_and_bad_department(google, client):
    dept = make_department()
    make_student("other@x.com", dept).matric_number = "CSC/1"
    db.session.commit()
    client.get("/auth/google/callback")
    html = client.post("/auth/google/profile", data={
        "full_name": "Ada", "matric_number": "csc/1", "department_id": str(dept.id)}).get_data(as_text=True)
    assert "already registered" in html
    assert db.session.scalar(select(User).where(User.email == "ada.obi@gmail.com")) is None
    html = client.post("/auth/google/profile", data={
        "full_name": "Ada", "matric_number": "CSC/9", "department_id": "999"}).get_data(as_text=True)
    assert db.session.scalar(select(User).where(User.email == "ada.obi@gmail.com")) is None


def test_signed_in_users_skip_google(google, client):
    make_student("s@x.com", make_department())
    login(client, "s@x.com")
    assert client.get("/auth/google").headers["Location"].endswith("/student/")


def test_next_page_is_kept_but_only_if_safe(google, client):
    make_student("ada.obi@gmail.com", make_department())
    client.get("/auth/google?next=/student/history")
    assert client.get("/auth/google/callback").headers["Location"].endswith("/student/history")


def test_unsafe_next_is_ignored(google, client):
    make_student("ada.obi@gmail.com", make_department())
    client.get("/auth/google?next=https://evil.example.com/")
    assert client.get("/auth/google/callback").headers["Location"].endswith("/student/")


def test_google_unreachable_shows_a_friendly_message_not_an_error_page(app, client, monkeypatch):
    import requests
    app.config["GOOGLE_CLIENT_ID"], app.config["GOOGLE_CLIENT_SECRET"] = "id", "secret"

    class Offline:
        def authorize_redirect(self, uri):
            raise requests.ConnectionError("no internet")

        def authorize_access_token(self):
            raise requests.ConnectionError("no internet")
    monkeypatch.setattr("sarps.routes.auth.google_client", lambda: Offline())
    for path in ("/auth/google", "/auth/google/callback"):
        response = client.get(path, follow_redirects=True)
        assert response.status_code == 200 and "could not reach Google" in response.get_data(as_text=True)


def test_behind_a_proxy_the_callback_address_is_https():
    """On Vercel the proxy says the visitor used https; the app must believe it, or Google rejects the address."""
    from flask import url_for
    from config import TestConfig
    from sarps import create_app
    config = type("ProxyConfig", (TestConfig,), {"TRUST_PROXY": True})
    app = create_app(config)

    @app.route("/_callback_address")
    def callback_address():
        return url_for("auth.google_callback", _external=True)

    response = app.test_client().get("/_callback_address", base_url="http://internal/",
                                     headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "sarps.vercel.app"})
    assert response.get_data(as_text=True) == "https://sarps.vercel.app/auth/google/callback"
