from datetime import timedelta, datetime
from fastapi import APIRouter, Depends, HTTPException, Header, Request, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .auth import get_db, roles, device_auth
from .permissions import own_hive, scoped_apiaries, profile
from .models import Telemetry, Device, Hive, Beekeeper, Alert, Maintenance
from .schemas import TelemetryIn, MaintenanceIn
from .database import now
from .audit import audit

router = APIRouter()
reader = roles("BEEKEEPER", "KVIC_ADMIN")


def reading_view(r):
    return {
        "id": r.id,
        "timestamp": r.measured_at.isoformat(),
        "received_at": r.received_at.isoformat(),
        "weight_kg": r.weight_kg,
        "temperature_c": r.temperature_c,
        "humidity_percent": r.humidity_percent,
    }


def readings(db, hive_id):
    return list(
        db.scalars(
            select(Telemetry)
            .join(Device, Telemetry.device_id == Device.id)
            .where(Device.hive_id == hive_id)
            .order_by(Telemetry.measured_at)
        )
    )


def alert_view(a):
    return {
        "id": a.id,
        "hive_id": a.hive_id,
        "type": a.type,
        "severity": a.severity,
        "evidence": a.evidence,
        "recommendation": a.recommendation,
        "opened_at": a.opened_at.isoformat(),
        "last_seen": a.last_seen.isoformat(),
        "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
    }


@router.post("/api/telemetry")
def ingest(
    body: TelemetryIn,
    request: Request,
    x_device_key: str | None = Header(default=None),
    db=Depends(get_db),
):
    device = device_auth(db, body.device_id, x_device_key)
    if (
        device.hive_id != body.hive_id
        or device.hive.apiary.beekeeper_id != body.beekeeper_id
    ):
        raise HTTPException(403, "Device ownership mapping mismatch")
    current = now()
    if body.timestamp > current + timedelta(
        minutes=5
    ) or body.timestamp < current - timedelta(
        days=request.app.state.settings.max_age_days
    ):
        raise HTTPException(422, "Timestamp outside ingestion window")
    old = db.scalar(
        select(Telemetry).where(
            Telemetry.device_id == device.id, Telemetry.measured_at == body.timestamp
        )
    )
    if old:
        if any(
            getattr(old, k) != getattr(body, k)
            for k in ("weight_kg", "temperature_c", "humidity_percent")
        ):
            raise HTTPException(409, "Timestamp already exists with different readings")
        device.last_contact = current
        db.commit()
        return {"id": old.id, "duplicate": True}
    row = Telemetry(
        device_id=device.id,
        measured_at=body.timestamp,
        received_at=current,
        weight_kg=body.weight_kg,
        temperature_c=body.temperature_c,
        humidity_percent=body.humidity_percent,
    )
    db.add(row)
    device.last_contact = current
    try:
        db.flush()
        if hasattr(request.app.state, "evaluate"):
            request.app.state.evaluate(
                db, device.hive, request.app.state.settings, current
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        old = db.scalar(
            select(Telemetry).where(
                Telemetry.device_id == device.id,
                Telemetry.measured_at == body.timestamp,
            )
        )
        if old and all(
            getattr(old, k) == getattr(body, k)
            for k in ("weight_kg", "temperature_c", "humidity_percent")
        ):
            return {"id": old.id, "duplicate": True}
        raise HTTPException(409, "Conflicting telemetry")
    return {"id": row.id, "duplicate": False}


@router.get("/api/hives/{hive_id}/telemetry")
def history(
    hive_id: str,
    user=Depends(reader),
    db=Depends(get_db),
    from_time: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
    limit: int = Query(200, ge=1, le=1000),
    cursor: int = Query(0, ge=0),
):
    own_hive(db, user, hive_id)
    for value in (from_time, to):
        if value and value.tzinfo is None:
            raise HTTPException(422, "Timezone required")
    rows = readings(db, hive_id)
    rows = [
        r
        for r in rows
        if (not from_time or r.measured_at >= from_time)
        and (not to or r.measured_at <= to)
    ]
    return {
        "items": [reading_view(r) for r in rows[cursor : cursor + limit]],
        "next_cursor": cursor + limit if len(rows) > cursor + limit else None,
    }


@router.get("/api/hives/{hive_id}/status")
def status(hive_id: str, request: Request, user=Depends(reader), db=Depends(get_db)):
    hive = own_hive(db, user, hive_id)
    if hasattr(request.app.state, "evaluate"):
        result = request.app.state.evaluate(db, hive, request.app.state.settings, now())
        db.commit()
        return result
    rows = readings(db, hive_id)
    return {
        "hive_id": hive.id,
        "measured": reading_view(rows[-1]) if rows else None,
        "interpreted": {"status": "INSUFFICIENT_DATA"},
    }


@router.get("/api/hives/{hive_id}/alerts")
def alerts(
    hive_id: str, user=Depends(reader), db=Depends(get_db), status: str | None = None
):
    own_hive(db, user, hive_id)
    query = (
        select(Alert).where(Alert.hive_id == hive_id).order_by(Alert.last_seen.desc())
    )
    if status == "active":
        query = query.where(Alert.resolved_at.is_(None))
    return {"items": [alert_view(a) for a in db.scalars(query)], "next_cursor": None}


@router.get("/api/beekeeper/me")
def me(user=Depends(roles("BEEKEEPER")), db=Depends(get_db)):
    p = profile(db, user, Beekeeper)
    return {
        "beekeeper_id": p.id,
        "display_name": user.display_name,
        "registered": p.registered,
    }


@router.get("/api/beekeeper/apiaries")
def apiaries(user=Depends(roles("BEEKEEPER")), db=Depends(get_db)):
    return {
        "items": [
            {
                "id": a.id,
                "name": a.name,
                "beekeeper_id": a.beekeeper_id,
                "district": a.jurisdiction.name,
            }
            for a in scoped_apiaries(db, user)
        ]
    }


@router.get("/api/beekeeper/hives")
def hives(
    request: Request,
    user=Depends(roles("BEEKEEPER")),
    db=Depends(get_db),
    apiary_id: str | None = None,
):
    ids = [
        a.id for a in scoped_apiaries(db, user) if not apiary_id or a.id == apiary_id
    ]
    rows = list(db.scalars(select(Hive).where(Hive.apiary_id.in_(ids))))
    items = (
        [
            request.app.state.evaluate(db, h, request.app.state.settings, now())
            for h in rows
        ]
        if hasattr(request.app.state, "evaluate")
        else [{"hive_id": h.id} for h in rows]
    )
    db.commit()
    return {"items": items}


@router.get("/api/beekeeper/alerts")
def my_alerts(
    user=Depends(roles("BEEKEEPER")), db=Depends(get_db), status: str | None = None
):
    ids = [a.id for a in scoped_apiaries(db, user)]
    query = (
        select(Alert)
        .join(Hive, Alert.hive_id == Hive.id)
        .where(Hive.apiary_id.in_(ids))
        .order_by(Alert.last_seen.desc())
    )
    if status == "active":
        query = query.where(Alert.resolved_at.is_(None))
    return {"items": [alert_view(a) for a in db.scalars(query)]}


@router.post("/api/hives/{hive_id}/maintenance")
def maintenance(
    hive_id: str,
    body: MaintenanceIn,
    user=Depends(roles("BEEKEEPER")),
    db=Depends(get_db),
):
    own_hive(db, user, hive_id)
    if body.occurred_at > now() + timedelta(minutes=5):
        raise HTTPException(422, "Future event not allowed")
    row = Maintenance(
        hive_id=hive_id,
        user_id=user.id,
        occurred_at=body.occurred_at,
        description=body.description,
    )
    db.add(row)
    db.flush()
    audit(db, user, "MAINTENANCE_RECORDED", "hive", hive_id)
    db.commit()
    return {"id": row.id}
