"""F
"""
import math

from flask import current_app
from flask_wtf import FlaskForm
from sqlalchemy import select
from wtforms import (BooleanField, FloatField, IntegerField, PasswordField, RadioField,
                     SelectField, StringField)
from wtforms.validators import (DataRequired, Email, EqualTo, InputRequired, Length,
                                NumberRange, Optional, ValidationError)

from ml.features import (ATTENDANCE_OPTIONS, FINANCIAL_COMFORT_OPTIONS, FINANCIAL_IMPACT_OPTIONS,
                         STUDY_HOURS_OPTIONS, valid_levels)
from sarps.constants import CONSENT_TEXT, ROLE_LABELS, Role
from sarps.extensions import db
from sarps.models import Department, User
from sarps.security import password_problems


def _strip(value):
    return value.strip() if isinstance(value, str) else value


def _clean_email(value):
    return value.strip().lower() if isinstance(value, str) else value


def _clean_matric(value):
    return value.strip().upper() if isinstance(value, str) else value


def finite_number(form, field):
    """"""
    if field.data is not None and not math.isfinite(field.data):
        raise ValidationError("Enter a valid number.")


def password_rules(form, field):
    problems = password_problems(field.data, current_app.config["MIN_PASSWORD_LENGTH"])
    if problems:
        raise ValidationError("Password needs: " + ", ".join(problems) + ".")


def _email_not_taken(form, field):
    if db.session.scalar(select(User.id).where(User.email == field.data)):
        raise ValidationError("An account with this email already exists.")

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


class GoogleProfileForm(FlaskForm):
    """"""
    full_name = StringField("Full name", filters=[_strip],
                            validators=[DataRequired(), Length(min=2, max=150)])
    matric_number = StringField("Matriculation number", filters=[_clean_matric],
                                validators=[DataRequired(), Length(min=3, max=40)])
    department_id = SelectField("Department", coerce=int)

    def validate_matric_number(self, field):
        if db.session.scalar(select(User.id).where(User.matric_number == field.data)):
            raise ValidationError("This matriculation number is already registered.")


def _coerce_level(value):
    """"""
    if value in (None, ""):
        return None
    return int(value)


def _chosen(options, message):
    """"""
    allowed = valid_levels(options)

    def check(form, field):
        if field.data is None or field.data not in allowed:
            raise ValidationError(message)
    return check


def _dropdown(label, options, message):
    return SelectField(label, coerce=_coerce_level, validate_choice=False,
                       choices=[("", "Select an option")] + list(options),
                       validators=[_chosen(options, message)])


class WholeNumberField(IntegerField):
    """"""

    def process_formdata(self, valuelist):
        if not valuelist or valuelist[0].strip() == "":
            self.data = None
            return
        try:
            self.data = int(valuelist[0].strip())
        except ValueError:
            self.data = None
            raise ValueError("Enter a whole number, zero or more.")


def _count(label, required_message):
    return WholeNumberField(label, validators=[
        InputRequired(message=required_message),
        NumberRange(0, MAX_COUNT, message=f"Enter a whole number from 0 to {MAX_COUNT}.")])


MAX_COUNT = 1000


class AssessmentForm(FlaskForm):
    attendance_level = _dropdown("How often have you attended class so far this semester?",
                                 ATTENDANCE_OPTIONS, "Choose the option that best describes your attendance.")

    assignments_assigned = _count("How many assignments have been assigned to you so far this semester?",
                                  "Enter how many assignments were assigned (0 if none).")
    assignments_submitted = _count("Out of those, how many have you submitted?",
                                   "Enter how many you have submitted (0 if none).")

    tests_done = _count("How many tests or CAs have you done so far this semester?",
                        "Enter how many tests or CAs you have done (0 if none).")
    tests_high = _count("Out of those, how many do you think you scored above 70% in?",
                        "Enter a number (0 if none).")
    tests_low = _count("How many do you think you scored below 50% in?",
                       "Enter a number (0 if none).")

    study_hours_level = _dropdown("How many hours do you typically study outside class in a week?",
                                  STUDY_HOURS_OPTIONS, "Choose your typical weekly study hours.")

    financial_comfort = _dropdown("How financially comfortable would you consider yourself as a student?",
                                  FINANCIAL_COMFORT_OPTIONS, "Choose how financially comfortable you are.")
    financial_impact = _dropdown(
        "How often does your financial situation affect your ability to participate in school activities? "
        "(e.g. buying textbooks, paying dues, transport, data for studying)",
        FINANCIAL_IMPACT_OPTIONS, "Choose how often money affects you.")

    has_cgpa = RadioField(
        "Do you have your current CGPA?",
        choices=[("yes", "Yes, I have my current CGPA"), ("no", "No, I do not have my CGPA yet")],
        validate_choice=False,
        validators=[InputRequired(message="Please say whether you have a CGPA.")])
    previous_cgpa = FloatField("Your current CGPA", validators=[Optional(), finite_number])

    consent = BooleanField(
        CONSENT_TEXT,
        validators=[DataRequired(message="You must agree to the sharing arrangement before submitting.")])

    @property
    def cgpa_unavailable(self):
        return self.has_cgpa.data == "no"

    def validate_has_cgpa(self, field):
        if field.data not in ("yes", "no"):
            raise ValidationError("Please say whether you have a CGPA.")

    def validate(self, extra_validators=None):
        valid = super().validate(extra_validators)

        def fail(field, message):
            field.errors = list(field.errors) + [message]
            return False

        if self.has_cgpa.data == "yes":
            maximum = current_app.config["CGPA_MAX"]
            value = self.previous_cgpa.data
            if value is None:
                if not self.previous_cgpa.errors:
                    valid = fail(self.previous_cgpa, "Enter your CGPA.")
                else:
                    valid = False
            elif not (0 <= value <= maximum):
                valid = fail(self.previous_cgpa, f"CGPA must be between 0 and {maximum:g}.")
        elif self.has_cgpa.data == "no":
            self.previous_cgpa.errors = []
            self.previous_cgpa.data = None

        assigned, submitted = self.assignments_assigned.data, self.assignments_submitted.data
        if assigned is not None and submitted is not None and submitted > assigned:
            valid = fail(self.assignments_submitted,
                         f"You cannot have submitted more assignments ({submitted}) than were assigned ({assigned}).")
        done, high, low = self.tests_done.data, self.tests_high.data, self.tests_low.data
        if done is not None and high is not None and high > done:
            valid = fail(self.tests_high, f"This cannot be more than the number of tests or CAs you have done ({done}).")
        if done is not None and low is not None and low > done:
            valid = fail(self.tests_low, f"This cannot be more than the number of tests or CAs you have done ({done}).")
        if (done is not None and high is not None and low is not None
                and high <= done and low <= done and high + low > done):
            valid = fail(self.tests_low,
                         f"A test cannot be both above 70% and below 50%, so these two cannot add up to more than {done}.")
        return valid

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
