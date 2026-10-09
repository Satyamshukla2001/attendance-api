"""Integration tests.

Requires a real MongoDB (docker compose up -d); skipped otherwise.
"""

import os
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

# pyright: reportMissingImports=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownParameterType=false
# pyright: reportUntypedFunctionDecorator=false
import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

from app.main import app

URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
os.environ["DB_NAME"] = "attendance_test"

_c: MongoClient | None = None

try:
    mongo_client = MongoClient(
        URI,
        serverSelectionTimeoutMS=1000,
        tz_aware=True,
    )
    mongo_client.admin.command("ping")
    _c = mongo_client
except ServerSelectionTimeoutError:
    pytest.skip("MongoDB not reachable", allow_module_level=True)

assert _c is not None
raw = _c["attendance_test"]


@pytest.fixture
def client() -> Iterator[TestClient]:
    assert _c is not None
    _c.drop_database("attendance_test")
    raw.employees.insert_many(
        [
            {
                "_id": "E1",
                "name": "A",
                "department": "Eng",
                "shift_start_minutes": 570,
            },
            {
                "_id": "E2",
                "name": "B",
                "department": "HR",
                "shift_start_minutes": 570,
            },
        ]
    )
    with TestClient(app) as c:
        yield c


def test_list_employees(client: TestClient) -> None:
    response = client.get("/attendance/employees")
    assert response.status_code == 200
    assert response.json() == [
        {"employee_id": "E1", "name": "A", "department": "Eng"},
        {"employee_id": "E2", "name": "B", "department": "HR"},
    ]


def seed_shift(
    emp: str,
    start: datetime,
    hours: float,
    wd: str | None = None,
) -> None:
    end = start + timedelta(hours=hours)
    ist = timezone(timedelta(hours=5, minutes=30))
    insert_date = wd or start.astimezone(ist).date().isoformat()
    raw.attendance.insert_one(
        {
            "employee_id": emp,
            "work_date": insert_date,
            "punch_in": start,
            "punch_out": end,
            "status": "closed",
            "duration_minutes": int(hours * 60),
            "version": 1,
            "corrected": False,
        }
    )


def test_punch_flow_and_rules(client: TestClient) -> None:
    punch_out_response = client.post(
        "/attendance/punch-out",
        json={"employee_id": "E1"},
    )
    assert punch_out_response.status_code == 409

    missing_employee_response = client.post(
        "/attendance/punch-in",
        json={"employee_id": "NOPE"},
    )
    assert missing_employee_response.status_code == 404

    first_in = client.post(
        "/attendance/punch-in",
        json={"employee_id": "E1"},
    )
    assert first_in.status_code == 201

    duplicate_in = client.post(
        "/attendance/punch-in",
        json={"employee_id": "E1"},
    )
    assert duplicate_in.status_code == 409

    second_employee_in = client.post(
        "/attendance/punch-in",
        json={"employee_id": "E2"},
    )
    assert second_employee_in.status_code == 201


def test_correction_and_audit(client: TestClient) -> None:
    start = datetime.now(timezone.utc) - timedelta(days=2)
    seed_shift("E1", start, 8)
    rec = client.get("/attendance", params={"employee_id": "E1"}).json()[0]
    new_out = (start + timedelta(hours=9)).isoformat()

    bad_correction = client.post(
        f"/attendance/{rec['id']}/corrections",
        json={
            "punch_out": new_out,
            "reason": "bad",
            "corrected_by": "hr",
        },
    )
    assert bad_correction.status_code == 422

    correction = client.post(
        f"/attendance/{rec['id']}/corrections",
        json={
            "punch_out": new_out,
            "reason": "forgot to punch out",
            "corrected_by": "hr",
        },
    )
    assert correction.status_code == 200
    payload = correction.json()
    assert payload["duration_minutes"] == 540
    assert payload["corrected"] is True
    assert payload["version"] == 2

    log = client.get(f"/attendance/{rec['id']}/audit").json()
    assert len(log) == 1
    assert log[0]["by"] == "hr"
    assert log[0]["before"]["punch_out"] != log[0]["after"]["punch_out"]


def test_correction_rejects_overlap_and_future(client: TestClient) -> None:
    s = datetime.now(timezone.utc) - timedelta(days=3)
    seed_shift("E1", s, 8)
    seed_shift("E1", s + timedelta(hours=9), 2)
    first = client.get(
        "/attendance",
        params={"employee_id": "E1"},
    ).json()[-1]
    body = {
        "punch_out": (s + timedelta(hours=10)).isoformat(),
        "reason": "extend too far",
        "corrected_by": "hr",
    }
    overlap = client.post(
        f"/attendance/{first['id']}/corrections",
        json=body,
    )
    assert overlap.status_code == 409

    body["punch_out"] = (
        datetime.now(timezone.utc) + timedelta(days=1)
    ).isoformat()
    future = client.post(
        f"/attendance/{first['id']}/corrections",
        json=body,
    )
    assert future.status_code == 422


def test_analytics(client: TestClient) -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    month = datetime.now(ist).strftime("%Y-%m")

    def make_day(day_number: int, hour: int, minute: int) -> datetime:
        return datetime(
            int(month[:4]),
            int(month[5:]),
            day_number,
            hour,
            minute,
            tzinfo=ist,
        ).astimezone(timezone.utc)

    seed_shift("E1", make_day(1, 9, 0), 8, f"{month}-01")
    seed_shift("E1", make_day(2, 10, 0), 8, f"{month}-02")
    seed_shift("E1", make_day(2, 19, 0), 1, f"{month}-02")
    seed_shift("E2", make_day(1, 9, 45), 7, f"{month}-01")

    monthly = client.get(
        "/analytics/monthly-summary",
        params={"month": month},
    ).json()
    summary = {record["employee_id"]: record for record in monthly}
    assert summary["E1"]["days_present"] == 2
    assert summary["E1"]["total_hours"] == 17
    assert summary["E1"]["late_days"] == 1
    assert summary["E2"]["late_days"] == 1

    late = client.get(
        "/analytics/late-arrivals",
        params={"month": month},
    ).json()
    assert {record["employee_id"] for record in late} == {"E1", "E2"}
    assert next(
        record for record in late if record["employee_id"] == "E1"
    )["avg_minutes_late"] == 30

    department_summary = client.get(
        "/analytics/department-summary",
        params={"month": month},
    ).json()
    departments = {
        record["department"]: record for record in department_summary
    }
    assert departments["Eng"]["total_hours"] == 17
    assert departments["HR"]["headcount_active"] == 1

    daily_hours = client.get(
        "/analytics/daily-hours",
        params={
            "employee_id": "E1",
            "date_from": f"{month}-01",
            "date_to": f"{month}-02",
        },
    ).json()
    assert [record["hours"] for record in daily_hours] == [8, 9]

    bad_month_response = client.get(
        "/analytics/monthly-summary",
        params={"month": "2026-13"},
    )
    assert bad_month_response.status_code == 422
