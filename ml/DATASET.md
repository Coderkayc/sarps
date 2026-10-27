# Dataset format for training SARPS

SARPS can only make genuine predictions from a real dataset of past students. This file says exactly what that dataset must look like.

## File
A CSV file, one row per student, with a header row.

## Columns (exact names)
The columns hold the same NUMBERS the web form produces, so training and prediction always agree. The rules are in `ml/features.py`.

| Column | Meaning |
|---|---|
| `attendance_level` | **Required.** 0 = Never (0%), 1 = 1-20%, 2 = 21-40%, 3 = 41-60%, 4 = 61-80%, 5 = 81-95%, 6 = 96-100% |
| `assignment_submission_rate` | Assignments submitted divided by assigned, as 0-100. Blank if none were assigned |
| `ca_high_rate` | Share of tests/CAs the student felt they scored above 70% in, 0-100. Blank if none done |
| `ca_low_rate` | Share of tests/CAs the student felt they scored below 50% in, 0-100. Blank if none done |
| `study_hours_level` | 0 = none, 1 = below 5 h, 2 = 5-10, 3 = 10-15, 4 = 15-20, 5 = 20-25, 6 = 25-30, 7 = 30-35, 8 = 35-40, 9 = over 40 (hours per week) |
| `financial_comfort` | 1 = Severely Struggling, 2 = Somewhat Struggling, 3 = Fairly Comfortable, 4 = Comfortable, 5 = Very Comfortable |
| `financial_impact` | How often money affects taking part in school: 1 = Never ... 5 = Almost always |
| `previous_cgpa` | Current CGPA on your scale (0-5). Blank if the student had none |
| `not_at_risk` | **Required.** The real outcome: **1 = Not at Risk, 0 = At Risk** |

All columns must exist in the file, but any except `attendance_level` and `not_at_risk` may be blank. Blank values are filled with the training median, never with zero. If your data genuinely lacks a column, leave it empty and train with `--unused` (below), so the model ignores it and the app says so.

## Deciding the label (the most important choice)
You must decide, and be able to defend in your project report, what "At Risk" means in your data. Examples: final-semester GPA below a threshold, a failed course, or a probation outcome. The label must describe **what happened later**, not something computed from the inputs above, otherwise the model just learns your formula.

## Minimum size
At least 60 usable rows and at least 10 students in each class. More is much better, and a balanced mix helps.

## Training
```bash
python -m ml.train --data path/to/dataset.csv
```
Options: `--algorithm forest`, `--balanced` (if At Risk students are rare), `--cgpa-max 5.0`, `--unused COLUMN ...`.

The script prints accuracy, ROC AUC, and especially **at_risk_recall** (the share of truly At Risk students the model catches). It saves the model to `ml/models/sarps_model.joblib` plus a `.json` report you can cite. The CGPA scale in the dataset must match `CGPA_MAX` in `.env`, otherwise the app refuses the model.

## The models currently included (read before you present them)
The default `ml/models/sarps_model.joblib` is trained on SYNTHETIC students (see `ml/SYNTHETIC.md`) so that every input is used.
The section below describes the real-data model, now saved as `ml/models/sarps_model_iubat.joblib`.

`ml/models/sarps_model_iubat.joblib` was trained on the public IUBAT (Bangladesh) survey, 894 CS students, using `ml/prepare_iubat.py`:
```bash
python -m ml.prepare_iubat --raw IUBAT_Student_Performance_Dataset.csv --out ml/data/iubat_training.csv
python -m ml.train --data ml/data/iubat_training.csv --algorithm logistic --balanced \
  --unused assignment_submission_rate ca_high_rate ca_low_rate financial_impact
```
State these limits in your report:
- **Label:** At Risk = the student ever fell on academic probation (26% of students). A real outcome, but "ever" does not say when.
- **Four inputs are collected but ignored by the model**: assignment submission, test/CA perception, and "how often money affects participation". That dataset has no such columns, and inventing them would be fake. They are saved and used for the advice, and the app says so on the form and the result.
- **Proxies:** CGPA = the student's current CGPA rescaled from 4.0 to 5.0. Financial comfort = family income split into five equal groups. Attendance % and daily study hours are put into the same bands as the form dropdowns.
- **Different country and university** from yours, so treat results as a demonstration. Retrain with your own records when you can.
- **Accuracy on unseen students:** about 72% accuracy, ROC AUC 0.76 (5-fold cross-validated 0.72); it catches about 68% of At Risk students while wrongly flagging about 27% of the others. `--balanced` leans the model towards At Risk, so the percentage is a risk score, not a calibrated probability.
