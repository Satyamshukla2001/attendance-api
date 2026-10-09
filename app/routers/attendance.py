# pyright: reportMissingImports=false
# pyright: reportMissingTypeArgument=false
# pyright: reportMissingParameterType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownParameterType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUntypedFunctionDecorator=false
# pyright: reportAttributeAccessIssue=false

from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Query
from pymongo.errors import DuplicateKeyError

from ..config import MAX_CORRECTION_DAYS
from ..db import db, get_client, supports_transactions
from ..rules import (
    duration_minutes,
    to_utc,
    utcnow,
    validate_interval,
    work_date_ist,
)
from ..schemas import CorrectionRequest, PunchRequest

router = APIRouter(prefix="/attendance", tags=["attendance"])


def serialize(doc: dict[str, Any]) -> dict[str, Any]:
    doc["id"] = str(doc.pop("_id"))
    return doc


def oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except InvalidId as exc:
        raise HTTPException(422, "invalid attendance id") from exc


@router.get("/employees")
async def list_employees() -> list[dict[str, Any]]:
    employees = db.employees.find(
        {}, {"_id": 1, "name": 1, "department": 1}
    ).sort("name", 1)
    return [
        {
            "employee_id": employee["_id"],
            "name": employee["name"],
            "department": employee["department"],
        }
        async for employee in employees
    ]


@router.post(
    "/punch-in",
    status_code=201,
    responses={
        404: {"description": "employee not found"},
        409: {"description": "employee already has an open shift"},
    },
)
async def punch_in(body: PunchRequest) -> dict[str, Any]:
    if not await db.employees.find_one({"_id": body.employee_id}):
        raise HTTPException(404, "employee not found")
    now = utcnow()
    doc: dict[str, Any] = {
        "employee_id": body.employee_id,
        "work_date": work_date_ist(now),
        "punch_in": now,
        "punch_out": None,
        "status": "open",
        "duration_minutes": None,
        "version": 1,
        "corrected": False,
    }
    try:
        res = await db.attendance.insert_one(doc)
    except DuplicateKeyError:  # partial unique index -> already punched in
        raise HTTPException(409, "employee already has an open shift")
    doc["_id"] = res.inserted_id
    return serialize(doc)


@router.post(
    "/punch-out",
    responses={
        409: {"description": "no open shift to punch out of"},
        422: {"description": "invalid punch-out time interval"},
    },
)
async def punch_out(body: PunchRequest) -> dict[str, Any]:
    open_rec = await db.attendance.find_one(
        {"employee_id": body.employee_id, "status": "open"}
    )
    if not open_rec:
        raise HTTPException(409, "no open shift to punch out of")
    now = utcnow()
    err = validate_interval(open_rec["punch_in"], now)
    if err:
        raise HTTPException(422, err)
    # Filter on status again so two concurrent punch-outs can't both win.
    updated = await db.attendance.find_one_and_update(
        {"_id": open_rec["_id"], "status": "open"},
        {
            "$set": {
                "punch_out": now,
                "status": "closed",
                "duration_minutes": duration_minutes(
                    open_rec["punch_in"], now
                ),
            },
            "$inc": {"version": 1},
        },
        return_document=True,
    )
    if not updated:
        raise HTTPException(409, "shift was already closed")
    return serialize(updated)


@router.get("")
async def list_attendance(
    employee_id: str | None = None,
    date_from: str | None = Query(None, description="YYYY-MM-DD (IST)"),
    date_to: str | None = Query(None, description="YYYY-MM-DD (IST)"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    q: dict[str, Any] = {}
    if employee_id:
        q["employee_id"] = employee_id
    if date_from or date_to:
        q["work_date"] = {}
        if date_from:
            q["work_date"]["$gte"] = date_from
        if date_to:
            q["work_date"]["$lte"] = date_to
    cur = db.attendance.find(q).sort("punch_in", -1).skip(skip).limit(limit)
    return [serialize(d) async for d in cur]


def _validate_correction(
    rec: dict[str, Any], body: CorrectionRequest, now: datetime
) -> tuple[datetime, datetime | None]:
    if body.punch_in is None and body.punch_out is None:
        raise HTTPException(422, "provide punch_in and/or punch_out")
    if rec["punch_in"] < now - timedelta(days=MAX_CORRECTION_DAYS):
        raise HTTPException(
            422,
            f"records older than {MAX_CORRECTION_DAYS} days are locked",
        )

    new_in = to_utc(body.punch_in) if body.punch_in else rec["punch_in"]
    new_out = to_utc(body.punch_out) if body.punch_out else rec["punch_out"]
    if new_in > now or (new_out and new_out > now):
        raise HTTPException(422, "times cannot be in the future")
    err = validate_interval(new_in, new_out)
    if err:
        raise HTTPException(422, err)
    return new_in, new_out


async def _ensure_no_overlap(
    rec: dict[str, Any],
    new_in: datetime,
    new_out: datetime | None,
    now: datetime,
) -> None:
    overlap = await db.attendance.find_one(
        {
            "_id": {"$ne": rec["_id"]},
            "employee_id": rec["employee_id"],
            "punch_in": {"$lt": new_out or now},
            "$or": [
                {"punch_out": {"$gt": new_in}},
                {"status": "open"},
            ],
        }
    )
    if overlap:
        raise HTTPException(409, "corrected times overlap another record")


@router.post(
    "/{attendance_id}/corrections",
    responses={
        404: {"description": "attendance record not found"},
        409: {"description": "conflict while updating the attendance record"},
        422: {"description": "invalid attendance id"},
    },
)
async def correct(
    attendance_id: str,
    body: CorrectionRequest,
) -> dict[str, Any]:
    rec = await db.attendance.find_one({"_id": oid(attendance_id)})
    if not rec:
        raise HTTPException(404, "attendance record not found")

    now = utcnow()
    new_in, new_out = _validate_correction(rec, body, now)
    await _ensure_no_overlap(rec, new_in, new_out, now)

    status = "closed" if new_out else "open"
    changes: dict[str, Any] = {
        "punch_in": new_in,
        "punch_out": new_out,
        "status": status,
        "work_date": work_date_ist(new_in),
        "duration_minutes": (
            duration_minutes(new_in, new_out) if new_out else None
        ),
        "corrected": True,
    }
    audit_entry: dict[str, Any] = {
        "attendance_id": rec["_id"],
        "employee_id": rec["employee_id"],
        "action": "correction",
        "by": body.corrected_by,
        "reason": body.reason,
        "at": now,
        "before": {
            k: rec.get(k) for k in ("punch_in", "punch_out", "status")
        },
        "after": {
            k: changes[k] for k in ("punch_in", "punch_out", "status")
        },
    }

    async def write(session: Any | None = None) -> dict[str, Any]:
        # Optimistic concurrency: only update if nobody changed it
        # since we read it.
        try:
            updated = await db.attendance.find_one_and_update(
                {"_id": rec["_id"], "version": rec["version"]},
                {"$set": changes, "$inc": {"version": 1}},
                return_document=True,
                session=session,
            )
        except DuplicateKeyError as exc:
            raise HTTPException(
                409,
                "employee already has another open shift",
            ) from exc
        if not updated:
            raise HTTPException(409, "record changed concurrently, retry")
        # Append-only audit entry: the API never updates or deletes these.
        await db.audit_log.insert_one(dict(audit_entry), session=session)
        return updated

    if supports_transactions():
        client: Any | None = get_client()
        if client is None:
            updated = await write()
        else:
            async with client.start_session() as session:
                session.start_transaction()
                updated = await write(session)
    else:
        updated = await write()
    return serialize(updated)


@router.get(
    "/{attendance_id}/audit",
    responses={
        404: {"description": "attendance record not found"},
        422: {"description": "invalid attendance id"},
    },
)
async def audit(attendance_id: str) -> list[dict[str, Any]]:
    cur = (
        db.audit_log.find({"attendance_id": oid(attendance_id)})
        .sort("at", 1)
    )
    out: list[dict[str, Any]] = []
    async for d in cur:
        d["id"] = str(d.pop("_id"))
        d["attendance_id"] = str(d["attendance_id"])
        out.append(d)
    return out
