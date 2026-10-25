# SARPS: Student Academic Risk Prediction System

Flask + MySQL + scikit-learn web app. Students enter their academic details, receive a probability of being **Not at Risk** and a classification (At Risk / Not at Risk), and can submit new assessments any time.

**Classification rule:** probability of Not at Risk below 50% = At Risk, exactly 50% = At Risk, above 50% = Not at Risk.

## Important: no model is included
The app never invents predictions. Until you train a model from a real dataset, the assessment form is disabled and the server refuses submissions. See `ml/DATASET.md`.

## 1. Install
```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then edit .env (Windows: copy)
```

## 2. Create the MySQL database
In the MySQL shell:
```sql
CREATE DATABASE sarps CHARACTER SET utf8mb4;
CREATE USER 'sarps'@'localhost' IDENTIFIED BY 'your-password';
GRANT ALL ON sarps.* TO 'sarps'@'localhost';
```
Put the same user, password and database name in `.env`.

## 3. Create tables, a department and the first administrator
```bash
flask --app app init-db
flask --app app add-department "Computer Science"
flask --app app create-admin
```

## 4. Run
```bash
python app.py
```
Open http://127.0.0.1:5000 and sign in as the administrator. Then:
1. Add more departments (Departments page).
2. Create staff accounts (Users page). Students register themselves.
3. Assign advisers and lecturers to students (Assignments page). Heads of Department automatically see their department.

## 5. Train the real model (when you have a dataset)
```bash
python -m ml.train --data path/to/dataset.csv
```
The app detects the new model automatically. The admin overview shows its version and test results.

## Who can see what
| Role | Sees |
|---|---|
| Student | Own assessments only |
| Academic adviser / Lecturer | Students assigned by the administrator |
| Head of Department | All students in their department |
| Administrator | Manages accounts, departments, assignments. Cannot see assessments |

An At Risk assessment is flagged and appears in the "Flagged only" list of every staff member authorised to see that student.

## Tests
```bash
pytest -v
```
To run them against MySQL, create an EMPTY database `sarps_test` and set `TEST_DATABASE_URL=mysql+pymysql://user:pass@127.0.0.1:3306/sarps_test`.

## Not built yet (be honest in your report)
Password reset, forced password change for admin-created accounts, login rate limiting, email notifications, database migrations (tables are created with `init-db`), production server setup (use HTTPS and a WSGI server such as gunicorn; set `SECRET_KEY` and `SESSION_COOKIE_SECURE=1`).
