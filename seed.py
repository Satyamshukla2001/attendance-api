"""Seed employees and ~3 weeks of sample attendance. Usage: python seed.py"""
import asyncio
import random
from datetime import datetime, timedelta, timezone

from app.config import IST
from app.db import close_db, db, init_db

rng = random.SystemRandom()

EMPLOYEES = [
    ("E001", "Asha Verma", "Engineering"),
    ("E002", "Rohan Gupta", "Engineering"),
    ("E003", "Meera Nair", "HR"),
    ("E004", "Imran Khan", "Sales"),
    ("E005", "Priya Singh", "Sales"),
]


async def main():
    await init_db()
    try:
        await db.employees.delete_many({})
        await db.attendance.delete_many({})
        await db.audit_log.delete_many({})
        await db.employees.insert_many([
            {
                "_id": i,
                "name": n,
                "department": d,
                "shift_start_minutes": 9 * 60 + 30,
            }
            for i, n, d in EMPLOYEES
        ])
        today = datetime.now(IST).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        rows = []
        for back in range(1, 22):
            day = today - timedelta(days=back)
            if day.weekday() >= 5:
                continue
            for eid, *_ in EMPLOYEES:
                if rng.random() < 0.08:
                    continue
                start = day + timedelta(
                    hours=9, minutes=rng.randint(0, 55)
                )
                end = start + timedelta(
                    hours=8, minutes=rng.randint(0, 90)
                )
                rows.append(
                    {
                        "employee_id": eid,
                        "work_date": start.date().isoformat(),
                        "punch_in": start.astimezone(timezone.utc),
                        "punch_out": end.astimezone(timezone.utc),
                        "status": "closed",
                        "duration_minutes": int(
                            (end - start).total_seconds() // 60
                        ),
                        "version": 1,
                        "corrected": False,
                    }
                )
        await db.attendance.insert_many(rows)
        print(
            f"seeded {len(EMPLOYEES)} employees, "
            f"{len(rows)} attendance rows"
        )
    finally:
        await close_db()


asyncio.run(main())
