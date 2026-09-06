from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from .auth import roles, get_db
from .permissions import scoped_apiaries, profile
from .models import Hive, Officer, Jurisdiction, Alert, Extraction, Batch
from .telemetry_api import alert_view
from .regional_engine import regional
from .database import now

router = APIRouter()
officer = roles("KVIC_ADMIN")


def scope(db, user):
    return scoped_apiaries(db, user)


def refresh(db, user, request):
    allowed_hives = {
        "HIVE-MH-88492-01",
        "HIVE-MH-88493-01",
    }

    items = [
        request.app.state.evaluate(db, h, request.app.state.settings, now())
        for h in db.scalars(
            select(Hive).where(
                Hive.apiary_id.in_([a.id for a in scope(db, user)]),
                Hive.id.in_(allowed_hives),
            )
        )
    ]

    region = regional(
        db,
        db.get(Jurisdiction, profile(db, user, Officer).jurisdiction_id),
        request.app.state.settings,
        now(),
    )

    db.commit()
    return items, region


@router.get("/api/kvic/overview")
def overview(request: Request, user=Depends(officer), db=Depends(get_db)):
    apiaries = scope(db, user)
    ids = [a.id for a in apiaries]
    hives, region = refresh(db, user, request)
    exts = list(db.scalars(select(Extraction).where(Extraction.apiary_id.in_(ids))))
    batches = list(
        db.scalars(
            select(Batch)
            .join(Extraction, Batch.extraction_id == Extraction.id)
            .where(Extraction.apiary_id.in_(ids))
        )
    )
    return {
        "registered_beekeepers": len({a.beekeeper_id for a in apiaries}),
        "active_apiaries": sum(a.active for a in apiaries),
        "active_hives": len(hives),
        "devices_online": sum(h["device_status"] == "ONLINE" for h in hives),
        "active_hive_alerts": sum(len(h["interpreted"]["alerts"]) for h in hives),
        "regional_alerts": int(region["status"] == "REGIONAL_ANOMALY_ALERT"),
        "pending_lab_batches": sum(b.state == "PENDING_LAB" for b in batches),
        "pending_kvic_reviews": sum(b.state == "PENDING_KVIC_REVIEW" for b in batches),
        "released_batches": sum(b.state == "PUBLICLY_VERIFIABLE" for b in batches),
        "rejected_batches": sum(b.state == "REJECTED" for b in batches),
        "recorded_extraction_kg": str(sum(e.quantity_kg for e in exts)),
        "regional": region,
        "as_of": now().isoformat(),
    }


@router.get("/api/kvic/beekeepers")
def keepers(user=Depends(officer), db=Depends(get_db)):
    values = {
        a.beekeeper_id: {
            "id": a.beekeeper_id,
            "display_name": a.beekeeper.user.display_name,
            "registered": a.beekeeper.registered,
        }
        for a in scope(db, user)
    }
    return {"items": list(values.values())}


@router.get("/api/kvic/apiaries")
def apiaries(
    user=Depends(officer), db=Depends(get_db), beekeeper_id: str | None = None
):
    return {
        "items": [
            {
                "id": a.id,
                "name": a.name,
                "beekeeper_id": a.beekeeper_id,
                "district": a.jurisdiction.name,
                "state": a.jurisdiction.state,
            }
            for a in scope(db, user)
            if not beekeeper_id or a.beekeeper_id == beekeeper_id
        ]
    }


@router.get("/api/kvic/hives")
def hives(
    request: Request,
    user=Depends(officer),
    db=Depends(get_db),
    apiary_id: str | None = None,
    beekeeper_id: str | None = None,
):
    items, _ = refresh(db, user, request)
    return {
        "items": [
            h
            for h in items
            if (not apiary_id or h["apiary_id"] == apiary_id)
            and (not beekeeper_id or h["beekeeper_id"] == beekeeper_id)
        ]
    }


@router.get("/api/kvic/alerts")
def alerts(
    request: Request,
    user=Depends(officer),
    db=Depends(get_db),
    status: str | None = None,
):
    refresh(db, user, request)
    query = (
        select(Alert)
        .join(Hive, Alert.hive_id == Hive.id)
        .where(Hive.apiary_id.in_([a.id for a in scope(db, user)]))
        .order_by(Alert.last_seen.desc())
    )
    if status == "active":
        query = query.where(Alert.resolved_at.is_(None))
    return {"items": [alert_view(a) for a in db.scalars(query)]}


@router.get("/api/kvic/regional-alerts")
def regions(request: Request, user=Depends(officer), db=Depends(get_db)):
    _, region = refresh(db, user, request)
    return {"items": [region]}
