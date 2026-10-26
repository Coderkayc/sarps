# Dataset format for training SARPS

SARPS can only make genuine predictions from a real dataset of past students. This file says exactly what that dataset must look like.

## File
A CSV file, one row per student, with a header row.

## Columns (exact names)

| Column | Required? | Meaning |
|---|---|---|
| `attendance_pct` | yes | Class attendance, 0 to 100 |
| `assignment_completion_pct` | yes | Share of assignments completed, 0 to 100 |
| `previous_cgpa` | no | Previous CGPA on your university's scale. Leave blank if the student had none |
| `financial_capability` | no | `low`, `medium` or `high` (or 1, 2, 3). Leave blank if unknown |
| `study_hours_per_week` | no | Average study hours per week, 0 to 100. Leave blank if unknown |
| `not_at_risk` | yes | The real outcome: **1 = Not at Risk, 0 = At Risk** |

Rows missing `attendance_pct`, `assignment_completion_pct` or `not_at_risk` are dropped (and reported). Blank optional values are fine: the model is built to handle them, because real students will leave them blank too.

## Deciding the label (the most important choice)
You must decide, and be able to defend in your project report, what "At Risk" means in your data. Examples: final-semester GPA below a threshold, a failed course, or a probation outcome. The label must describe **what happened later**, not something computed from the five inputs above, otherwise the model just learns your formula.

## Minimum size
At least 60 usable rows and at least 10 students in each class. More is much better, and a balanced mix helps.

## Training
```bash
python -m ml.train --data path/to/dataset.csv
```
Optional: `--algorithm forest`, `--balanced` (if At Risk students are rare), `--cgpa-max 4.0`.

The CGPA scale in the dataset must match `CGPA_MAX` in `.env`, otherwise students will be compared on a different scale from the one the model learned.

The script prints accuracy, ROC AUC, and especially **at_risk_recall** (the share of truly At Risk students the model catches). It saves the model to `ml/models/sarps_model.joblib` plus a `.json` report of the results, which you can cite in your project report.

## Honest limits to state in your report
- A model is only as good as its data: a small or biased dataset gives an unreliable model.
- The percentage shown to students is the model's estimated probability, not a certainty.
- Retrain whenever you get new data. The app picks up the new model file automatically.

## The model currently included (read before you present it)
`ml/models/sarps_model.joblib` was trained on the public IUBAT (Bangladesh) survey, 894 CS students, using `ml/prepare_iubat.py`. Command used:
```bash
python -m ml.train --data ml/data/iubat_training.csv --unused assignment_completion_pct --algorithm logistic --balanced
```
Be upfront about these limits in your report:
- **Label:** At Risk = the student ever fell on academic probation (26% of students). It is a real outcome, but "ever" does not say when.
- **Assignment completion is not in that dataset.** The form still collects it, but the model ignores it (the app says so on the form and result).
- **Proxies:** previous CGPA = the student's current CGPA, rescaled from 4.0 to 5.0. Financial capability = family-income thirds (low/medium/high) from that sample.
- **Different country and university** from yours, so treat results as a demonstration. Retrain with your own records when you can.
- **Accuracy on unseen students:** about 73% accuracy, ROC AUC 0.77 (5-fold cross-validated 0.73), and it catches about 68% of At Risk students while wrongly flagging about 26% of the others. `--balanced` makes the model lean towards At Risk, so the percentage is a risk score, not a calibrated probability.
- **CGPA scale:** the model was trained on a 5.0 scale. `CGPA_MAX` in `.env` must stay 5.0, otherwise the app refuses to use the model.
