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


class Course(db.Model):
    """A course in the catalogue. Credit units come from here, so students cannot invent them."""

    __tablename__ = "courses"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    title = db.Column(db.String(150), nullable=False)
    units = db.Column(db.Integer, nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)

    department = db.relationship("Department")

    @property
    def label(self):
        return f"{self.code} - {self.title} ({self.units}u)"


class CourseRecord(db.Model):
    """One student's figures for one course in one semester.

    Two sets of columns on purpose:
      *_official  entered by authorised staff (lecturer, ICT officer, class rep). Trusted.
      *_claimed   entered by the student, for when a record is missing or looks wrong.
    Official values always win. A claim that differs from an official value is shown as
    a discrepancy so staff can look into it.
    """

    __tablename__ = "course_records"
    __table_args__ = (db.UniqueConstraint("student_id", "course_id", "session", "semester",
                                          name="uq_record_student_course_term"),)

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    session = db.Column(db.String(9), nullable=False)      # e.g. "2026/2027"
    semester = db.Column(db.Integer, nullable=False)        # 1 or 2

    attendance_official = db.Column(db.Double, nullable=True)   # percent
    attendance_claimed = db.Column(db.Double, nullable=True)
    ca_official = db.Column(db.Double, nullable=True)            # out of 30
    ca_claimed = db.Column(db.Double, nullable=True)
    exam_official = db.Column(db.Double, nullable=True)          # out of 70
    exam_claimed = db.Column(db.Double, nullable=True)

    attendance_official_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    scores_official_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    student = db.relationship("User", foreign_keys=[student_id])
    course = db.relationship("Course")
    attendance_official_by = db.relationship("User", foreign_keys=[attendance_official_by_id])
    scores_official_by = db.relationship("User", foreign_keys=[scores_official_by_id])


class StudentGoal(db.Model):
    """What a student is aiming for, so advice is about THEIR target and not a guess."""

    __tablename__ = "student_goals"

    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    target_cgpa = db.Column(db.Double, nullable=True)
    cgpa_before_semester = db.Column(db.Double, nullable=True)
    units_before_semester = db.Column(db.Integer, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class AssessmentMeta(db.Model):
    """Extra facts about one assessment. A separate table so existing databases need no ALTER."""

    __tablename__ = "assessment_meta"

    assessment_id = db.Column(db.Integer, db.ForeignKey("assessments.id"), primary_key=True)
    # "records" = taken from course records, "student_override" = student typed a different
    # value than the records, "manual" = no records existed.
    attendance_source = db.Column(db.String(20), nullable=False, default="manual")
    attendance_records_value = db.Column(db.Double, nullable=True)
    target_cgpa = db.Column(db.Double, nullable=True)

    assessment = db.relationship("Assessment", backref=db.backref("meta", uselist=False))


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
