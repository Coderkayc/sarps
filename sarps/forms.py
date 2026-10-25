"""Forms. Each form lists its fields and the rules the server enforces.

Browser-side hints (like min and max) are only a convenience. These rules are
the real protection, because a browser can be bypassed.
"""
import math

from flask import current_app
from flask_wtf import FlaskForm
from sqlalchemy import select
from wtforms import BooleanField, FloatField, PasswordField, SelectField, StringField
from wtforms.validators import (DataRequired, Email, EqualTo, InputRequired, Length,
                                NumberRange, Optional, ValidationError)

from sarps.constants import CONSENT_TEXT, FINANCIAL_CHOICES, ROLE_LABELS, Role
from sarps.extensions import db
from sarps.models import Department, User
from sarps.security import password_problems


# ---------- small helpers ----------
def _strip(value):
    return value.strip() if isinstance(value, str) else value


def _clean_email(value):
    return value.strip().lower() if isinstance(value, str) else value


def _clean_matric(value):
    return value.strip().upper() if isinstance(value, str) else value


def finite_number(form, field):
    """Reject 'nan' and 'inf', which Python would otherwise accept as numbers."""
    if field.data is not None and not math.isfinite(field.data):
        raise ValidationError("Enter a valid number.")


def password_rules(form, field):
    problems = password_problems(field.data, current_app.config["MIN_PASSWORD_LENGTH"])
    if problems:
        raise ValidationError("Password needs: " + ", ".join(problems) + ".")


def _email_not_taken(form, field):
    if db.session.scalar(select(User.id).where(User.email == field.data)):
        raise ValidationError("An account with this email already exists.")


# ---------- sign in / registration ----------
class LoginForm(FlaskForm):
    email = StringField("Email", filters=[_clean_email], validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])


class StudentRegistrationForm(FlaskForm):
    full_name = StringField("Full name", filters=[_strip],
                            validators=[DataRequired(), Length(min=2, max=150)])
    matric_number = StringField("Matriculation number", filters=[_clean_matric],
                                validators=[DataRequired(), Length(min=3, max=40)])
    email = StringField("Email", filters=[_clean_email],
                        validators=[DataRequired(), Email(), Length(max=190), _email_not_taken])
    department_id = SelectField("Department", coerce=int)
    password = PasswordField("Password", validators=[DataRequired(), password_rules, Length(max=128)])
    confirm = PasswordField("Confirm password",
                            validators=[DataRequired(), EqualTo("password", message="Passwords do not match.")])

    def validate_matric_number(self, field):
        if db.session.scalar(select(User.id).where(User.matric_number == field.data)):
            raise ValidationError("This matriculation number is already registered.")


# ---------- the assessment ----------
class AssessmentForm(FlaskForm):
    # Mandatory
    attendance_pct = FloatField(
        "Class attendance (%)",
        validators=[InputRequired(message="Attendance is required."), finite_number,
                    NumberRange(0, 100, message="Enter a value from 0 to 100.")])
    assignment_completion_pct = FloatField(
        "Assignment completion (%)",
        validators=[InputRequired(message="Assignment completion is required."), finite_number,
                    NumberRange(0, 100, message="Enter a value from 0 to 100.")])

    # Optional
    previous_cgpa = FloatField("Previous CGPA", validators=[Optional(), finite_number])
    cgpa_unavailable = BooleanField("I have no previous CGPA")
    financial_capability = SelectField(
        "Financial capability", choices=[("", "Prefer not to say")] + FINANCIAL_CHOICES,
        validators=[Optional()])
    study_hours_per_week = FloatField(
        "Average study hours per week",
        validators=[Optional(), finite_number, NumberRange(0, 100, message="Enter a value from 0 to 100.")])

    consent = BooleanField(
        CONSENT_TEXT,
        validators=[DataRequired(message="You must agree to the sharing arrangement before submitting.")])

    def validate_previous_cgpa(self, field):
        maximum = current_app.config["CGPA_MAX"]
        if field.data is not None and not (0 <= field.data <= maximum):
            raise ValidationError(f"CGPA must be between 0 and {maximum:g}.")

    def validate(self, extra_validators=None):
        valid = super().validate(extra_validators)
        if self.cgpa_unavailable.data and self.previous_cgpa.data is not None:
            self.previous_cgpa.errors = list(self.previous_cgpa.errors) + [
                "Either enter a CGPA or tick 'I have no previous CGPA', not both."]
            valid = False
        return valid


# ---------- administrator forms ----------
class CreateStaffForm(FlaskForm):
    full_name = StringField("Full name", filters=[_strip],
                            validators=[DataRequired(), Length(min=2, max=150)])
    email = StringField("Email", filters=[_clean_email],
                        validators=[DataRequired(), Email(), Length(max=190), _email_not_taken])
    role = SelectField("Role", choices=[
        (Role.ADVISER, ROLE_LABELS[Role.ADVISER]),
        (Role.LECTURER, ROLE_LABELS[Role.LECTURER]),
        (Role.HOD, ROLE_LABELS[Role.HOD])])
    department_id = SelectField("Department", coerce=int)
    password = PasswordField("Temporary password",
                             validators=[DataRequired(), password_rules, Length(max=128)])

    def validate_department_id(self, field):
        if self.role.data == Role.HOD and field.data == 0:
            raise ValidationError("A Head of Department must be linked to a department.")


class DepartmentForm(FlaskForm):
    name = StringField("Department name", filters=[_strip],
                       validators=[DataRequired(), Length(min=2, max=150)])

    def validate_name(self, field):
        if db.session.scalar(select(Department.id).where(Department.name == field.data)):
            raise ValidationError("This department already exists.")


class AssignmentForm(FlaskForm):
    staff_id = SelectField("Adviser or lecturer", coerce=int)
    student_id = SelectField("Student", coerce=int)
