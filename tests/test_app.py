"""Landing page, error pages, security headers."""
from config import TestConfig
from sarps import create_app
from sarps.extensions import db


def test_landing_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "SARPS" in html and "Student Academic Risk Prediction System" in html


def test_landing_page_has_no_status_lines_under_the_buttons(client, model_client):
    for c in (client, model_client):
        html = c.get("/").get_data(as_text=True)
        assert "model is installed" not in html and "has not been installed yet" not in html
        assert "50% or below" not in html.split('id="about"')[0]


def test_static_files_are_served(client):
    for path in ["css/tailwind.css", "js/main.js", "js/gauge.js", "js/charts.js",
                 "js/assess_form.js", "vendor/chart.umd.min.js"]:
        assert client.get(f"/static/{path}").status_code == 200, path


def test_unknown_page_returns_custom_404(client):
    response = client.get("/this-page-does-not-exist")
    assert response.status_code == 404
    assert "Page not found" in response.get_data(as_text=True)


def test_security_headers_present(client):
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"] == "no-store"


def test_no_inline_scripts_or_styles_that_the_policy_would_block(client):
    # The Content-Security-Policy only allows this site's own files.
    html = client.get("/login").get_data(as_text=True)
    assert " style=" not in html
    assert "onclick=" not in html


def test_csrf_protection_is_enforced_when_enabled():
    config = type("CsrfOn", (TestConfig,), {"WTF_CSRF_ENABLED": True})
    app = create_app(config)
    with app.app_context():
        db.create_all()
        response = app.test_client().post("/login", data={"email": "a@b.com", "password": "x"})
        assert response.status_code == 400
        assert "Form expired" in response.get_data(as_text=True)


def test_logout_requires_post(client):
    assert client.get("/logout").status_code in (302, 405)
