# Employee Attendance & Analytics API

FastAPI + MongoDB (Motor). Punch-in/out with business rules, corrections with an audit trail, and analytics via aggregation pipelines.

## Run

PowerShell (Windows):

```bash
docker compose up -d
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Run `python seed.py` only if you want to clear and repopulate the configured database with sample data. **Seeding is destructive** to the `employees`, `attendance`, and `audit_log` collections.

The dashboard is served at `http://127.0.0.1:8000/`; API docs are at `http://127.0.0.1:8000/docs`. Run tests with `python -m pytest`. API integration tests require a reachable MongoDB and use the separate `attendance_test` database.

MongoDB Compass connection URI: `mongodb://127.0.0.1:27017`. The app defaults to this same URI and uses the `attendance` database. The database and collections appear after the app initializes or data is inserted.

Env vars: `MONGO_URI`, `DB_NAME`. Note: `python seed.py` clears and repopulates the `employees`, `attendance`, and `audit_log` collections in the configured database.

## Endpoints

| Method | Path                          | Purpose                                             |
| ------ | ----------------------------- | --------------------------------------------------- |
| GET    | /attendance/employees         | List employees for the dashboard and punch controls |
| POST   | /attendance/punch-in          | Start a shift                                       |
| POST   | /attendance/punch-out         | End the open shift                                  |
| GET    | /attendance                   | List (filter by employee, IST date range, paginate) |
| POST   | /attendance/{id}/corrections  | Correct times, requires reason + corrected_by       |
| GET    | /attendance/{id}/audit        | Audit trail for a record                            |
| GET    | /analytics/daily-hours        | Hours per day for an employee                       |
| GET    | /analytics/monthly-summary    | Days present, hours, late days per employee         |
| GET    | /analytics/department-summary | Hours/headcount per department                      |
| GET    | /analytics/late-arrivals      | Top late employees                                  |

## Business rules (my assumptions, adjust to the problem statement)

- One open shift per employee, enforced by a **partial unique index** (race-safe, not just an app check).
- Punch-out needs an open shift; shift length is 1 minute to 16 hours.
- Server sets punch times (UTC); `work_date` is the **IST** calendar date.
- Corrections: reason mandatory, no future times, no overlap with other records, records older than 31 days locked.
- Lateness = first punch-in after the employee's `shift_start_minutes` (IST).

## Design decisions

- **Optimistic concurrency** via a `version` field on corrections; punch-out filters on `status:"open"`.
- **Audit log** is a separate append-only collection storing before/after, actor, reason, timestamp. The API has no update/delete for it.
- Correction + audit entry commit in **one transaction** when the server is a replica set/Atlas (auto-detected at startup). On a standalone server they are written sequentially (update, then audit), so a crash between them could leave an unaudited change. Known trade-off.
- `scripts/audit_role.js` creates a DB role with insert-only access to `audit_log` for defence in depth.
- Time zones: store UTC, convert with `$dateToParts` + `timezone` in pipelines.

## Submission guide

The submitted project includes the application, dashboard, database seed script, audit-role script, and tests:

- `app/main.py`, `app/config.py`, `app/db.py`: FastAPI app, configuration, MongoDB lifecycle, indexes, and health route.
- `app/routers/attendance.py`, `app/routers/analytics.py`: attendance and analytics API endpoints.
- `app/rules.py`, `app/schemas.py`: time-zone/business rules and request validation models.
- `app/static/`: browser dashboard HTML, CSS, and JavaScript; dashboard values are loaded from the API.
- `seed.py`, `scripts/audit_role.js`: optional sample-data setup and MongoDB audit-role setup.
- `tests/test_rules.py`, `tests/test_api.py`: rules unit tests and MongoDB integration tests.
- `requirements.txt`, `docker-compose.yml`: Python dependencies and local MongoDB service.

Changes made during the 2026-10-09 development session:

- Fixed dashboard startup by invoking `loadDashboard()` from the deferred browser script rather than using top-level `await`.
- Added a package docstring to `tests/__init__.py`.
- Verified the full test suite (**8 passed**), Python compilation, dashboard JavaScript syntax, and local HTTP endpoints.
- Ran the app locally at `http://127.0.0.1:8001/` and verified it fetched dashboard data from MongoDB.

Live dashboard data fetched from MongoDB for October 2026 during that session:

| Employee | Department | Days present | Hours | Late days |
| --- | --- | ---: | ---: | ---: |
| Asha Verma | Engineering | 5 | 42.95 | 1 |
| Rohan Gupta | Engineering | 5 | 44.32 | 1 |
| Meera Nair | HR | 5 | 43.72 | 2 |
| Imran Khan | Sales | 6 | 44.95 | 4 |
| Priya Singh | Sales | 6 | 52.93 | 3 |

Dashboard totals at that time: **5 active team members**, **228.9 hours**, **27 days present**, and **11 late days**. These are a dated data snapshot, not fixed application values; the dashboard fetches current values from MongoDB when loaded or refreshed.

For submission, include the source and configuration files above. Do not include virtual environments, Python cache files, or local database files. Configure `MONGO_URI` and `DB_NAME` through environment variables when using a non-default database; do not commit credentials.

## Not done / TODO

- Not aligned to the official OpenAPI contract (kit not reviewed): rename routes/fields to match.
- No auth; no code-review / design-answer templates filled in.
