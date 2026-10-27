# The synthetic training data: what is made up

`ml/data/synthetic_training.csv` (2,000 rows) is produced by `python -m ml.make_synthetic`. **These students do not exist.**
It lets every input on the assessment form be used by the model before real data is available.

## How a student is invented
1. Two hidden traits are drawn per student: **diligence** and **financial means** (bell-curve random numbers).
2. Each form answer is built from those traits plus random noise, so no answer perfectly copies a trait.
3. The outcome (At Risk / Not at Risk) is drawn by chance, with odds set by the traits. It is not a fixed if/then
   rule on the inputs, so the model cannot just memorise a rule.

## Assumptions (invented, not measured on real students)
| Assumption | Where |
|---|---|
| Diligence is the main driver of results; financial means matters less; money affecting school hurts a little more on top | `DILIGENCE_EFFECT`, `MEANS_EFFECT`, `PRESSURE_EFFECT` |
| Attendance, assignments, tests, study hours and CGPA all rise with diligence | `generate()` |
| Comfort rises with means; "money affects school" rises when comfort is low | `generate()` |
| About 30% of students end up At Risk | `TARGET_AT_RISK` |
| Share of students at each attendance, study-hours and financial level | `ATTENDANCE_SHARE`, `STUDY_SHARE`, `COMFORT_SHARE`, `IMPACT_SHARE` |
| 3-15 assignments and 2-8 tests per student; 5% have none yet | `generate()` |
| About 20% have no CGPA yet; CGPA is on the 5.0 scale | `generate()` |

## What the scores mean
The model scores about 71% accuracy and ROC AUC about 0.78 on held-out synthetic students (it catches about 78% of At Risk
ones). Those numbers describe how well the model learned the **invented** patterns. They say nothing about how well it
predicts real UNN students. Do not present them as real-world performance.

## Replacing it
Collect real students with a known outcome, keep them in `ml/data/real_students.csv` (header in `ml/data/real_students_template.csv`),
and run `python -m ml.train --data ml/data/real_students.csv --balanced`. See the README, "Retrain later".
