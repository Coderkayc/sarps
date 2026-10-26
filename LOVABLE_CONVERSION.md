# Lovable (TypeScript) to Flask (Python) conversion map

A browser interface cannot be written in Python, so the design and pages were
rebuilt as Flask templates, CSS and a little JavaScript. Every page now comes
from Python routes (`sarps/routes/`) and Jinja templates (`sarps/templates/`).

| Lovable file | Now |
|---|---|
| `src/styles.css` (tokens, glass, blobs, buttons) | `static/css/style.css`, `static/css/app.css` |
| `routes/index.tsx` (landing) | `templates/index.html` |
| `routes/login.tsx`, `AuthShell`, `Blobs` | `templates/auth/login.html`, `layout_auth.html`, blob markup in `base.html` |
| `RegisterForm`, `PasswordField` | `auth/register.html`, `password_field` macro, `static/js/password.js`, `password_problems()` in `security.py` |
| `RiskGauge` | `_result.html`, `static/js/gauge.js` (Chart.js) |
| `DashShell` | header in `base.html` |
| `dashboard`, `advisor`, `hod`, `admin` routes | `templates/student|staff|admin/*.html` (existing role-checked pages, restyled) |
| `assessment.tsx` | `student/assess.html` (your original five inputs) |
| Supabase / TanStack / shadcn / Tailwind | Replaced by Flask, MySQL, Flask-Login, plain CSS |

## Deliberately NOT ported
- `lib/risk.ts`: a hand-written formula, not a trained model. SARPS only shows real model output.
- Staff self-registration: anyone could make themselves an adviser. Staff accounts are admin-created.
- The fake 78% sample result, dated "What's new" posts, "six questions" and "advisor notified right away" copy: not true of this app, so reworded.
- Notifications/messaging, avatar profile, username login, HOD-assigned advisers: not in your specification.

## Changed on purpose
- Small text colours darkened for readability; fonts are bundled locally (no external requests).
- Passwords now need 8+ characters, an uppercase letter, a number and a special character (existing accounts are unaffected).
- The institution name comes from `INSTITUTION` in `.env`. The logo is a simple original mark, because the zip had no logo or images.
