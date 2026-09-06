from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from .auth import roles, get_db
from .permissions import profile, scoped_batch, scoped_apiaries
from .models import (
    Lab,
    LabOperator,
    LabAssignment,
    LabResult,
    Officer,
    Batch,
    Extraction,
)
from .schemas import ResultIn, VersionIn, AssignmentIn
from .batches import lock_batch, batch_view, lab_view, event
from .ledger import text_hash, digest, result_record
from .database import now
from .audit import audit

router = APIRouter()
lab_role = roles("LAB_OPERATOR")
officer_role = roles("KVIC_ADMIN")


def latest_result(db, batch_id):
    return db.scalar(
        select(LabResult)
        .where(LabResult.batch_id == batch_id)
        .order_by(LabResult.version.desc())
    )


def enabled_lab(db, user):
    operator = profile(db, user, LabOperator)
    lab = db.get(Lab, operator.lab_id)
    if not lab or not lab.active:
        raise HTTPException(403, "Laboratory inactive")
    return lab


@router.get("/api/kvic/labs")
def labs(user=Depends(officer_role), db=Depends(get_db)):
    return {
        "items": [
            {"id": l.id, "name": l.name}
            for l in db.scalars(select(Lab).where(Lab.active.is_(True)))
        ]
    }


@router.get("/api/kvic/batches/pending")
def pending(user=Depends(officer_role), db=Depends(get_db)):
    ids = [a.id for a in scoped_apiaries(db, user)]
    query = (
        select(Batch)
        .join(Extraction, Batch.extraction_id == Extraction.id)
        .where(
            Extraction.apiary_id.in_(ids),
            Batch.state.in_(["PENDING_LAB", "PENDING_KVIC_REVIEW"]),
        )
    )
    return {"items": [batch_view(db, b) for b in db.scalars(query)]}


@router.get("/api/kvic/batches")
def all_batches(
    user=Depends(officer_role), db=Depends(get_db), state: str | None = None
):
    ids = [a.id for a in scoped_apiaries(db, user)]
    query = (
        select(Batch)
        .join(Extraction, Batch.extraction_id == Extraction.id)
        .where(Extraction.apiary_id.in_(ids))
    )
    if state:
        query = query.where(Batch.state == state)
    return {"items": [batch_view(db, b) for b in db.scalars(query)]}


@router.get("/api/kvic/batches/{batch_id}")
def officer_detail(batch_id: str, user=Depends(officer_role), db=Depends(get_db)):
    return batch_view(db, scoped_batch(db, user, batch_id))


@router.post("/api/kvic/batches/{batch_id}/assign-lab")
def assign(
    batch_id: str, body: AssignmentIn, user=Depends(officer_role), db=Depends(get_db)
):
    batch = scoped_batch(db, user, batch_id)
    if batch.state != "PENDING_LAB" or latest_result(db, batch.id):
        raise HTTPException(409, "Assignment locked after result submission")
    lab = db.get(Lab, body.lab_id)
    if not lab or not lab.active:
        raise HTTPException(422, "Active registered lab required")
    lock_batch(db, batch, body.expected_version)
    assignment = db.scalar(
        select(LabAssignment).where(LabAssignment.batch_id == batch.id)
    )
    if assignment:
        assignment.lab_id = lab.id
        assignment.officer_id = profile(db, user, Officer).id
        assignment.assigned_at = now()
    else:
        db.add(
            LabAssignment(
                batch_id=batch.id,
                lab_id=lab.id,
                officer_id=profile(db, user, Officer).id,
            )
        )
    audit(db, user, "LAB_ASSIGNED", "batch", batch.id)
    db.commit()
    return batch_view(db, batch)


@router.get("/api/lab/batches/assigned")
def assigned(user=Depends(lab_role), db=Depends(get_db)):
    lab = enabled_lab(db, user)
    return {
        "items": [
            batch_view(db, b)
            for b in db.scalars(
                select(Batch)
                .join(LabAssignment, LabAssignment.batch_id == Batch.id)
                .where(LabAssignment.lab_id == lab.id)
            )
        ]
    }


@router.get("/api/lab/batches/{batch_id}")
def detail(batch_id: str, user=Depends(lab_role), db=Depends(get_db)):
    enabled_lab(db, user)
    return batch_view(db, scoped_batch(db, user, batch_id))


@router.post("/api/lab/batches/{batch_id}/results")
def submit(batch_id: str, body: ResultIn, user=Depends(lab_role), db=Depends(get_db)):
    lab = enabled_lab(db, user)
    batch = scoped_batch(db, user, batch_id)
    if not body.report_reference.strip() or not body.evidence_reference.strip():
        raise HTTPException(422, "Nonblank report and evidence references required")
    if batch.state in ("PUBLICLY_VERIFIABLE", "REJECTED"):
        raise HTTPException(409, "Closed batch; new results are not permitted")
    if (
        body.tested_at > now() + timedelta(minutes=5)
        or body.tested_at < batch.extraction.extracted_at
    ):
        raise HTTPException(
            422, "Test time must follow extraction and not be in future"
        )
    previous = latest_result(db, batch.id)
    if previous and body.supersedes_result_id != previous.id:
        raise HTTPException(
            409, "Correction must explicitly reference the latest result"
        )
    if not previous and body.supersedes_result_id:
        raise HTTPException(409, "No result exists to supersede")
    lock_batch(db, batch, batch.version)
    row = LabResult(
        batch_id=batch.id,
        lab_id=lab.id,
        submitted_by=user.id,
        laboratory_name=lab.name,
        report_reference=body.report_reference,
        tested_at=body.tested_at,
        parameters=[p.model_dump() for p in body.parameters],
        outcome=body.outcome,
        evidence_reference=body.evidence_reference,
        report_content=body.report_content,
        report_sha256=text_hash(body.report_content)
        if body.report_content is not None
        else None,
        version=previous.version + 1 if previous else 1,
        supersedes_id=previous.id if previous else None,
    )
    db.add(row)
    batch.state = "PENDING_LAB"
    db.flush()
    audit(
        db,
        user,
        "LAB_CORRECTION_CREATED" if previous else "LAB_RESULT_CREATED",
        "lab_result",
        row.id,
    )
    db.commit()
    return lab_view(row)


@router.post("/api/lab/results/{result_id}/finalize")
def finalize(
    result_id: str, body: VersionIn, user=Depends(lab_role), db=Depends(get_db)
):
    lab = enabled_lab(db, user)
    row = db.get(LabResult, result_id)
    if not row or row.lab_id != lab.id:
        raise HTTPException(404, "Result not found")
    batch = scoped_batch(db, user, row.batch_id)
    if (
        row.finalized_at
        or row.version != body.expected_version
        or latest_result(db, batch.id).id != row.id
        or batch.state != "PENDING_LAB"
    ):
        raise HTTPException(409, "Result cannot be finalized in current state")
    if not row.evidence_reference or not row.report_reference or not row.parameters:
        raise HTTPException(422, "Laboratory evidence required")
    if (
        row.report_content is not None
        and text_hash(row.report_content) != row.report_sha256
    ):
        raise HTTPException(409, "Report integrity check failed")
    lock_batch(db, batch, batch.version)
    row.finalized_at = now()
    row.finalized_hash = digest(result_record(row))
    batch.state = "PENDING_KVIC_REVIEW" if row.outcome == "PASS" else "PENDING_LAB"
    event(db, batch, "LAB_RESULT_FINALIZED")
    if row.outcome == "PASS":
        event(db, batch, "PENDING_KVIC_REVIEW")
    audit(db, user, "LAB_RESULT_FINALIZED", "lab_result", row.id)
    db.commit()
    return {
        "result": lab_view(row),
        "batch_state": batch.state,
        "batch_version": batch.version,
    }
