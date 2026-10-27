# SARPS: Student Academic Risk Prediction System

Flask + MySQL + scikit-learn web app. Students enter their academic details, receive a probability of being **Not at Risk** and a classification (At Risk / Not at Risk), and can submit new assessments any time.

**Classification rule:** probability of Not at Risk below 50% = At Risk, exactly 50% = At Risk, above 50% = Not at Risk.

See `LOVABLE_CONVERSION.md` for how the Lovable design was ported.

## Frontend (Tailwind CSS + Chart.js)
Pages are HTML (Jinja templates) styled with Tailwind CSS v4, with plain JavaScript and Chart.js for the meter and history chart. The built stylesheet `sarps/static/css/tailwind.css` is included, so you do NOT need Node just to run the app. Only if you change styles or template classes:
```bash
cd frontend
npm install
npm run build      # or: npm run watch
```
Source styles live in `frontend/src/input.css`.

## Google sign-in
The "Sign in with Google" and "Sign up with Google" buttons need a Google OAuth client. Only you can create it (it is tied to your Google account):
1. Go to https://console.cloud.google.com/ and create a project.
2. **APIs & Services > OAuth consent screen**: choose External, fill in the app name and your email. While the app is in "Testing", add the Google accounts that should be allowed to sign in under **Test users**.
3. **APIs & Services > Credentials > Create credentials > OAuth client ID > Web application**.
4. Under **Authorised redirect URIs** add exactly: `http://127.0.0.1:5000/auth/google/callback` (and `http://localhost:5000/auth/google/callback` if you also browse by `localhost`). The address must match the one in your browser's address bar.
5. Copy the Client ID and Client secret into `.env` as `GOOGLE_CLIENT_ID=` and `GOOGLE_CLIENT_SECRET=`, save, and restart `python app.py`.

How it behaves: Google only proves the person's verified email. An existing account with that email is signed in. A new person is asked once for their matriculation number and department, and gets a student account. Staff accounts are still created by the administrator. The computer running SARPS needs internet access to reach Google. Without the two keys, the button explains that Google sign-in is not set up.

## About the included model
The app never invents predictions. It ships with a model trained on a real public dataset (Bangladesh, 894 students) so you can demonstrate it. That model has real limits (no assignment data, a different country, modest accuracy), listed in `ml/DATASET.md`. Replace it with your own university's data when you have it: `python -m ml.train --data your.csv`. Without any model file, the form is disabled and the server refuses submissions.

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
