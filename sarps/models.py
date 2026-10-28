"""Database tables. Each class below is one MySQL table."""
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from sarps.constants import ROLE_LABELS, Role
from sarps.extensions import db, login_manager


def utcnow():
    return datetime.now(timezone.utc)


class Department(db.Model):
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)

    def __repr__(self):
        return f"<Department {self.name}>"


class User(UserMixin, db.Model):
    """Everyone who can sign in: students, staff and administrators."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(190), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False, index=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)
    matric_number = db.Column(db.String(40), unique=True, nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    # Google's permanent id for this person, set the first time they sign in with Google.
    google_sub = db.Column(db.String(64), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    department = db.relationship("Department")

    # Flask-Login asks every user object whether the account may sign in.
    @property
    def is_active(self):
        return bool(self.active)

    @property
    def role_label(self):
        return ROLE_LABELS.get(self.role, self.role)

    @property
    def is_student(self):
        return self.role == Role.STUDENT

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


class StaffAssignment(db.Model):
    """Links an adviser or lecturer to a student they are authorised to see."""

    __tablename__ = "staff_assignments"
    __table_args__ = (db.UniqueConstraint("staff_id", "student_id", name="uq_staff_student"),)

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    staff = db.relationship("User", foreign_keys=[staff_id])
    student = db.relationship("User", foreign_keys=[student_id])


class Assessment(db.Model):
    """One submitted assessment: the inputs, the model's output and the consent given."""

    __tablename__ = "assessments"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    # Inputs, exactly as the student answered. Levels are the numbers defined in ml/features.py.
    attendance_level = db.Column(db.Integer, nullable=True)           # 0-6 (dropdown)
    assignments_assigned = db.Column(db.Integer, nullable=True)
    assignments_submitted = db.Column(db.Integer, nullable=True)
    tests_done = db.Column(db.Integer, nullable=True)
    tests_high = db.Column(db.Integer, nullable=True)                 # felt they scored above 70%
    tests_low = db.Column(db.Integer, nullable=True)                  # felt they scored below 50%
    study_hours_level = db.Column(db.Integer, nullable=True)          # 0-9 (dropdown)
    financial_comfort = db.Column(db.Integer, nullable=True)          # 1-5
    financial_impact = db.Column(db.Integer, nullable=True)           # 1-5
    previous_cgpa = db.Column(db.Double, nullable=True)
    cgpa_unavailable = db.Column(db.Boolean, nullable=False, default=False)

    # Older assessments (made before the inputs were redesigned) used these columns.
    # New assessments leave them empty. They are kept so old results can still be shown.
    attendance_pct = db.Column(db.Double, nullable=True)
    assignment_completion_pct = db.Column(db.Double, nullable=True)
    financial_capability = db.Column(db.String(10), nullable=True)
    study_hours_per_week = db.Column(db.Double, nullable=True)

    # Output of the trained model (percent, 0 to 100, two decimals).
    prob_not_at_risk = db.Column(db.Double, nullable=False)
    risk_label = db.Column(db.String(20), nullable=False)
    is_flagged = db.Column(db.Boolean, nullable=False, default=False, index=True)
    model_version = db.Column(db.String(80), nullable=False)

    # Proof the student agreed to the sharing arrangement before submitting.
    consent_given = db.Column(db.Boolean, nullable=False)
    consent_version = db.Column(db.String(20), nullable=False)

    student = db.relationship("User", foreign_keys=[student_id])


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
