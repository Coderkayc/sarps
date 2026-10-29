""""""


class Role:
    STUDENT = "student"
    ADVISER = "academic_adviser"
    LECTURER = "lecturer"
    HOD = "head_of_department"
    ADMIN = "administrator"


ROLE_LABELS = {
    Role.STUDENT: "Student",
    Role.ADVISER: "Academic adviser",
    Role.LECTURER: "Lecturer",
    Role.HOD: "Head of Department",
    Role.ADMIN: "Administrator",
}

STAFF_ROLES = (Role.ADVISER, Role.LECTURER, Role.HOD)
ASSIGNABLE_ROLES = (Role.ADVISER, Role.LECTURER)

RISK_AT = "At Risk"
RISK_NOT = "Not at Risk"
THRESHOLD_PERCENT = 50.0

FINANCIAL_CHOICES = [("low", "Low"), ("medium", "Medium"), ("high", "High")]
CONSENT_VERSION = "v1"
CONSENT_TEXT = (
    "I understand that my assessment results will be stored and shared with "
    "academic staff who are authorised to view them: my assigned academic "
    "adviser(s), my assigned lecturer(s), and the Head of my department. "
    "If an assessment is classified as At Risk, it will be flagged to these "
    "staff so that support can be offered to me."
)
