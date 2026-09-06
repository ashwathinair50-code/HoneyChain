from datetime import timedelta
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select, update
from .models import *
from .permissions import profile, scoped_apiaries
from .database import now
from .ledger import digest
from .audit import audit


def event(db, batch, name):
    db.add(BatchEvent(batch_id=batch.id, event=name))


def lock_batch(db, batch, expected):
    result = db.execute(
        update(Batch)
        .where(Batch.id == batch.id, Batch.version == expected)
        .values(version=Batch.version + 1)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise HTTPException(409, "Batch changed; reload before retrying")
    db.refresh(batch)


def create_extraction(db, user, body, *, seed_batch_id=None):
    value = body.model_dump(mode="json")
    operation = str(body.client_operation_id)
    hashed = digest(value)
    previous = db.scalar(
        select(SyncRecord).where(
            SyncRecord.user_id == user.id, SyncRecord.operation_id == operation
        )
    )
    if previous:
        if previous.payload_hash != hashed:
            raise HTTPException(409, "Operation ID was already used for different data")
        batch = db.get(Batch, previous.batch_id)
        return {
            "extraction_id": batch.extraction_id,
            "batch_id": batch.id,
            "state": batch.state,
            "duplicate": True,
        }
    apiary = next(
        (a for a in scoped_apiaries(db, user) if a.id == body.apiary_id), None
    )
    if not apiary:
        raise HTTPException(404, "Apiary not found")
    owned = list(
        db.scalars(
            select(Hive).where(
                Hive.apiary_id == apiary.id, Hive.id.in_(body.source_hive_ids)
            )
        )
    )
    if len(owned) != len(body.source_hive_ids):
        raise HTTPException(404, "Source hive not found in selected apiary")
    if body.extracted_at > now() + timedelta(minutes=5):
        raise HTTPException(422, "Extraction time is in the future")
    ext = Extraction(
        beekeeper_id=apiary.beekeeper_id,
        apiary_id=apiary.id,
        extracted_at=body.extracted_at,
        quantity_kg=body.quantity_kg,
        honey_type=body.honey_type,
    )
    db.add(ext)
    db.flush()
    for hive in owned:
        db.add(ExtractionHive(extraction_id=ext.id, hive_id=hive.id))
    batch = Batch(
        id=seed_batch_id or f"HC-{apiary.jurisdiction.state}-{apiary.jurisdiction.district}-{body.extracted_at.year}-{uuid4().hex[:12].upper()}",
        extraction_id=ext.id,
        state="PENDING_LAB",
    )
    db.add(batch)
    db.flush()
    event(db, batch, "EXTRACTION_CREATED")
    event(db, batch, "PENDING_LAB")
    db.add(
        SyncRecord(
            user_id=user.id,
            operation_id=operation,
            payload_hash=hashed,
            batch_id=batch.id,
        )
    )
    audit(db, user, "EXTRACTION_CREATED", "extraction", ext.id)
    return {
        "extraction_id": ext.id,
        "batch_id": batch.id,
        "state": batch.state,
        "duplicate": False,
    }


def batch_view(db, batch):
    ext = batch.extraction
    assignment = db.scalar(
        select(LabAssignment).where(LabAssignment.batch_id == batch.id)
    )
    results = list(
        db.scalars(
            select(LabResult)
            .where(LabResult.batch_id == batch.id)
            .order_by(LabResult.version)
        )
    )
    review = db.scalar(select(Review).where(Review.batch_id == batch.id))
    return {
        "batch_id": batch.id,
        "state": batch.state,
        "version": batch.version,
        "extraction": {
            "id": ext.id,
            "beekeeper_id": ext.beekeeper_id,
            "apiary_id": ext.apiary_id,
            "source_hive_ids": list(
                db.scalars(
                    select(ExtractionHive.hive_id).where(
                        ExtractionHive.extraction_id == ext.id
                    )
                )
            ),
            "extracted_at": ext.extracted_at.isoformat(),
            "quantity_kg": str(ext.quantity_kg),
            "honey_type": ext.honey_type,
        },
        "assigned_lab_id": assignment.lab_id if assignment else None,
        "lab_results": [lab_view(r) for r in results],
        "review": {
            "decision": review.decision,
            "reason": review.reason,
            "timestamp": review.timestamp.isoformat(),
        }
        if review
        else None,
        "audit_summary": [
            {"action": a.action, "role": a.role, "timestamp": a.timestamp.isoformat()}
            for a in db.scalars(
                select(Audit)
                .where(
                    Audit.entity_id.in_([batch.id, ext.id] + [r.id for r in results])
                )
                .order_by(Audit.timestamp)
            )
        ],
        "events": [
            {"event": e.event, "timestamp": e.timestamp.isoformat()}
            for e in db.scalars(
                select(BatchEvent)
                .where(BatchEvent.batch_id == batch.id)
                .order_by(BatchEvent.timestamp)
            )
        ],
    }


def lab_view(r):
    return {
        "result_id": r.id,
        "lab_id": r.lab_id,
        "laboratory_name": r.laboratory_name,
        "report_reference": r.report_reference,
        "tested_at": r.tested_at.isoformat(),
        "parameters": r.parameters,
        "outcome": r.outcome,
        "evidence_reference": r.evidence_reference,
        "report_content": r.report_content,
        "report_sha256": r.report_sha256,
        "version": r.version,
        "supersedes_id": r.supersedes_id,
        "status": "LAB_RESULT_FINALIZED" if r.finalized_at else "SUBMITTED",
        "finalized_at": r.finalized_at.isoformat() if r.finalized_at else None,
    }
