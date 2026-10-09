# pyright: reportMissingImports=false
import re
from typing import Annotated, Any, Callable, TypeVar, cast

from ..config import TZ_NAME
from ..db import db

F = TypeVar("F", bound=Callable[..., Any])

# FastAPI is provided by the project environment; when it is not installed,
# keep the module importable so static analysis and editor tooling still work.
try:
    from fastapi import (
        APIRouter as APIRouter,  # pyright: ignore
        HTTPException as HTTPException,  # pyright: ignore
        Query as Query,  # pyright: ignore
    )
except ImportError:  # pragma: no cover
    class _FallbackAPIRouter:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            # This stub exists only for static analysis / editor tooling when
            # no project venv has been selected. In that environment FastAPI
            # is not importable, so the router intentionally stays inert
            # instead of crashing at import time.
            pass

        def get(
            self, *args: Any, **kwargs: Any
        ) -> Callable[[F], F]:
            def decorator(func: F) -> F:
                return func

            return decorator

    class _FallbackHTTPException(Exception):
        def __init__(self, status_code: int, detail: Any = None) -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    def _fallback_query(*args: Any, **kwargs: Any) -> Any:
        return None

    APIRouter = _FallbackAPIRouter
    HTTPException = _FallbackHTTPException
    Query = _fallback_query

# Make the fallback explicit for pyright in environments without FastAPI type
# information, without changing runtime behavior.
APIRouter: Any
HTTPException: Any
Query: Any

PROJECT = "$project"
DIVIDE = "$divide"
ROUND = "$round"
MATCH = "$match"
GROUP = "$group"
SORT = "$sort"
LOOKUP = "$lookup"
UNWIND = "$unwind"
ADD_FIELDS = "$addFields"
MULTIPLY = "$multiply"
DURATION_MINUTES = "$duration_minutes"
TOTAL_MINUTES = "$total_minutes"
EMPLOYEE_ID = "$employee_id"
FIRST = "$first"
WORK_DATE = "$work_date"

router: Any = cast(Any, APIRouter)(prefix="/analytics", tags=["analytics"])
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def month_range(month: str) -> dict[str, Any]:
    if not MONTH_RE.match(month):
        raise HTTPException(422, "month must be YYYY-MM")
    # work_date is an ISO string so lexicographic prefix matching works.
    return {"work_date": {"$regex": f"^{month}-"}, "status": "closed"}


@router.get("/daily-hours")
async def daily_hours(
    employee_id: Annotated[str, Query(...)],
    date_from: Annotated[str, Query(...)],
    date_to: Annotated[str, Query(...)],
) -> list[dict[str, Any]]:
    """Total hours per IST day for one employee."""
    pipeline: list[dict[str, Any]] = [
        {
            MATCH: {
                "employee_id": employee_id,
                "status": "closed",
                "work_date": {"$gte": date_from, "$lte": date_to},
            }
        },
        {
            GROUP: {
                "_id": WORK_DATE,
                "minutes": {"$sum": DURATION_MINUTES},
                "punches": {"$sum": 1},
            }
        },
        {SORT: {"_id": 1}},
        {
            PROJECT: {
                "_id": 0,
                "date": "$_id",
                "punches": 1,
                "hours": {ROUND: [{DIVIDE: ["$minutes", 60]}, 2]},
            }
        },
    ]
    return await db.attendance.aggregate(pipeline).to_list(None)


@router.get(
    "/monthly-summary",
    responses={422: {"description": "Invalid month format"}},
)
async def monthly_summary(
    month: Annotated[str, Query(...)],
    employee_id: Annotated[str | None, Query()] = None,
) -> list[dict[str, Any]]:
    """Per employee: days present, total/avg hours, late arrivals."""
    match: dict[str, Any] = month_range(month)
    if employee_id:
        match["employee_id"] = employee_id
    pipeline: list[dict[str, Any]] = [
        {MATCH: match},
        {
            LOOKUP: {
                "from": "employees",
                "localField": "employee_id",
                "foreignField": "_id",
                "as": "emp",
            }
        },
        {UNWIND: "$emp"},
        {
            ADD_FIELDS: {
                "parts": {
                    "$dateToParts": {
                        "date": "$punch_in",
                        "timezone": TZ_NAME,
                    }
                }
            }
        },
        {
            ADD_FIELDS: {
                "is_late": {
                    "$gt": [
                        {
                            "$add": [
                                {MULTIPLY: ["$parts.hour", 60]},
                                "$parts.minute",
                            ]
                        },
                        "$emp.shift_start_minutes",
                    ]
                }
            }
        },
        # first collapse to one row per employee-day, then per employee
        {
            GROUP: {
                "_id": {"e": EMPLOYEE_ID, "d": WORK_DATE},
                "minutes": {"$sum": DURATION_MINUTES},
                "late": {"$max": "$is_late"},
                "name": {FIRST: "$emp.name"},
                "department": {FIRST: "$emp.department"},
            }
        },
        {
            GROUP: {
                "_id": "$_id.e",
                "name": {FIRST: "$name"},
                "department": {FIRST: "$department"},
                "days_present": {"$sum": 1},
                "total_minutes": {"$sum": "$minutes"},
                "late_days": {"$sum": {"$cond": ["$late", 1, 0]}},
            }
        },
        {
            PROJECT: {
                "_id": 0,
                "employee_id": "$_id",
                "name": 1,
                "department": 1,
                "days_present": 1,
                "late_days": 1,
                "total_hours": {ROUND: [{DIVIDE: [TOTAL_MINUTES, 60]}, 2]},
                "avg_hours_per_day": {
                    ROUND: [
                        {
                            DIVIDE: [
                                TOTAL_MINUTES,
                                {MULTIPLY: ["$days_present", 60]},
                            ]
                        },
                        2,
                    ]
                },
            }
        },
        {SORT: {"employee_id": 1}},
    ]
    return await db.attendance.aggregate(pipeline).to_list(None)


@router.get(
    "/department-summary",
    responses={422: {"description": "Invalid month format"}},
)
async def department_summary(
    month: Annotated[str, Query(...)],
) -> list[dict[str, Any]]:
    pipeline: list[dict[str, Any]] = [
        {MATCH: month_range(month)},
        {
            LOOKUP: {
                "from": "employees",
                "localField": "employee_id",
                "foreignField": "_id",
                "as": "emp",
            }
        },
        {UNWIND: "$emp"},
        {
            GROUP: {
                "_id": "$emp.department",
                "total_minutes": {"$sum": DURATION_MINUTES},
                "employees": {"$addToSet": EMPLOYEE_ID},
                "shifts": {"$sum": 1},
            }
        },
        {
            PROJECT: {
                "_id": 0,
                "department": "$_id",
                "shifts": 1,
                "headcount_active": {"$size": "$employees"},
                "total_hours": {ROUND: [{DIVIDE: [TOTAL_MINUTES, 60]}, 2]},
                "avg_hours_per_employee": {
                    ROUND: [
                        {
                            DIVIDE: [
                                TOTAL_MINUTES,
                                {MULTIPLY: [{"$size": "$employees"}, 60]},
                            ]
                        },
                        2,
                    ]
                },
            }
        },
        {SORT: {"total_hours": -1}},
    ]
    return await db.attendance.aggregate(pipeline).to_list(None)


@router.get(
    "/late-arrivals",
    responses={422: {"description": "Invalid month format"}},
)
async def late_arrivals(
    month: Annotated[str, Query(...)],
    top: Annotated[int, Query(ge=1, le=50)] = 5,
) -> list[dict[str, Any]]:
    """Employees ranked by number of days whose first punch-in
    was after shift start."""
    pipeline: list[dict[str, Any]] = [
        {MATCH: month_range(month)},
        {SORT: {"punch_in": 1}},
        {
            GROUP: {
                "_id": {"e": EMPLOYEE_ID, "d": WORK_DATE},
                "first_in": {FIRST: "$punch_in"},
            }
        },
        {
            LOOKUP: {
                "from": "employees",
                "localField": "_id.e",
                "foreignField": "_id",
                "as": "emp",
            }
        },
        {UNWIND: "$emp"},
        {
            ADD_FIELDS: {
                "p": {
                    "$dateToParts": {
                        "date": "$first_in",
                        "timezone": TZ_NAME,
                    }
                }
            }
        },
        {
            ADD_FIELDS: {
                "mins_late": {
                    "$subtract": [
                        {
                            "$add": [
                                {MULTIPLY: ["$p.hour", 60]},
                                "$p.minute",
                            ]
                        },
                        "$emp.shift_start_minutes",
                    ]
                }
            }
        },
        {MATCH: {"mins_late": {"$gt": 0}}},
        {
            GROUP: {
                "_id": "$_id.e",
                "name": {FIRST: "$emp.name"},
                "late_days": {"$sum": 1},
                "avg_minutes_late": {"$avg": "$mins_late"},
            }
        },
        {SORT: {"late_days": -1, "avg_minutes_late": -1}},
        {"$limit": top},
        {
            PROJECT: {
                "_id": 0,
                "employee_id": "$_id",
                "name": 1,
                "late_days": 1,
                "avg_minutes_late": {ROUND: ["$avg_minutes_late", 1]},
            }
        },
    ]
    return await db.attendance.aggregate(pipeline).to_list(None)
