"""Role guard and small safety helpers."""
from functools import wraps
from urllib.parse import urlparse

from flask import abort
from flask_login import current_user, login_required

from sarps.constants import STAFF_ROLES, Role


def password_problems(password, minimum):
    """List what is wrong with a new password (empty list = acceptable).

    Same four rules the sign-up form shows live: length, an uppercase letter,
    a number and a special character. The browser hint (password.js) is only
    a convenience; this server-side check is the one that counts.
    """
    password = password or ""
    problems = []
    if len(password) < minimum:
        problems.append(f"at least {minimum} characters")
    if not any(c.isupper() for c in password):
        problems.append("one uppercase letter")
    if not any(c.isdigit() for c in password):
        problems.append("one number")
    if password.isalnum() or not password:
        problems.append("one special character (@, #, !, $ ...)")
    return problems


def role_required(*roles):
    """Allow only signed-in users with one of `roles`. Others get 403 (or the login page)."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return decorator


def home_endpoint(user):
    """The dashboard each role lands on after signing in."""
    if user.role == Role.STUDENT:
        return "student.dashboard"
    if user.role in STAFF_ROLES:
        return "staff.dashboard"
    return "admin.dashboard"


def is_safe_next_url(target):
    """Only allow redirects to pages on this same site (blocks open-redirect tricks)."""
    if not target or "\\" in target:
        return False
    parts = urlparse(target)
    return not parts.scheme and not parts.netloc and target.startswith("/") and not target.startswith("//")
