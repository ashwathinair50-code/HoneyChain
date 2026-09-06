from io import BytesIO
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update
import qrcode
from .auth import roles, get_db
from .permissions import scoped_batch, profile
from .models import *
from .schemas import ApprovalIn, RejectionIn
from .batches import lock_batch, event, batch_view
from .lab_api import latest_result
from .ledger import digest, text_hash, result_record, verify
from .database import now
from .audit import audit

router = APIRouter()
officer_role = roles("KVIC_ADMIN")
PUBLIC_KEYS = (
    "batch_id",
    "origin",
    "producer_display_name",
    "producer_registered",
    "extraction_recorded",
    "extracted_at",
    "quantity_kg",
    "honey_type",
    "lab",
    "institutional_approval",
    "approved_at",
    "synthetic_demo",
)
LAB_KEYS = (
    "lab_id",
    "laboratory_name",
    "report_reference",
    "tested_at",
    "parameters",
    "outcome",
    "status",
    "report_sha256",
    "result_version",
    "finalized_at",
)
PARAM_KEYS = ("code", "value", "unit", "method")


def public_allowlist(snapshot):
    data = {k: snapshot.get(k) for k in PUBLIC_KEYS}
    lab = snapshot.get("lab", {})
    data["lab"] = {k: lab.get(k) for k in LAB_KEYS}
    data["lab"]["parameters"] = [
        {k: p.get(k) for k in PARAM_KEYS}
        for p in lab.get("parameters", [])
        if isinstance(p, dict)
    ]
    return data


@router.post("/api/kvic/batches/{batch_id}/approve")
def approve(
    batch_id: str,
    body: ApprovalIn,
    request: Request,
    user=Depends(officer_role),
    db=Depends(get_db),
):
    batch = scoped_batch(db, user, batch_id)
    if batch.state != "PENDING_KVIC_REVIEW":
        raise HTTPException(409, "Batch is not awaiting institutional review")
    row = latest_result(db, batch.id)
    if (
        not row
        or row.id != body.finalized_result_id
        or not row.finalized_at
        or row.outcome != "PASS"
    ):
        raise HTTPException(
            409, "Latest finalized PASS evidence required by prototype policy"
        )
    if not db.get(Lab, row.lab_id).active:
        raise HTTPException(409, "Laboratory is inactive")
    if (
        not row.finalized_hash
        or row.finalized_hash != digest(result_record(row))
        or (
            row.report_content is not None
            and text_hash(row.report_content) != row.report_sha256
        )
    ):
        raise HTTPException(409, "Finalized laboratory evidence integrity check failed")
    ext = batch.extraction
    apiary = db.get(Apiary, ext.apiary_id)
    keeper = db.get(Beekeeper, ext.beekeeper_id)
    if not keeper.registered or not keeper.user.active:
        raise HTTPException(409, "Active registered producer required")
    lock_batch(db, batch, body.expected_version)
    # Updating the single head serializes chain appends across concurrent approvals.
    db.execute(
        update(LedgerHead)
        .where(LedgerHead.id == 1)
        .values(version=LedgerHead.version + 1)
    )
    head = db.get(LedgerHead, 1)
    if not head:
        raise HTTPException(409, "Ledger head is not initialized; run database setup")
    previous = db.scalar(select(LedgerBlock).order_by(LedgerBlock.block_number.desc()))
    if previous and not verify(db, previous.batch_id)[0]:
        raise HTTPException(409, "Existing ledger integrity failed; release blocked")
    approved = now()
    officer = profile(db, user, Officer)
    snapshot = {
        "batch_id": batch.id,
        "origin": apiary.jurisdiction.name + ", " + {"MH": "Maharashtra"}.get(apiary.jurisdiction.state, apiary.jurisdiction.state),
        "producer_display_name": keeper.user.display_name,
        "producer_registered": True,
        "extraction_recorded": True,
        "extracted_at": ext.extracted_at.isoformat(),
        "quantity_kg": str(ext.quantity_kg),
        "honey_type": ext.honey_type,
        "lab": {
            "lab_id": row.lab_id,
            "laboratory_name": row.laboratory_name,
            "report_reference": row.report_reference,
            "tested_at": row.tested_at.isoformat(),
            "parameters": row.parameters,
            "outcome": row.outcome,
            "status": "LAB_RESULT_FINALIZED",
            "report_sha256": row.report_sha256,
            "result_version": row.version,
            "finalized_at": row.finalized_at.isoformat(),
        },
        "institutional_approval": True,
        "approved_at": approved.isoformat(),
        "synthetic_demo": row.laboratory_name.startswith("SYNTHETIC DEMO"),
    }
    release = Release(
        batch_id=batch.id, snapshot=snapshot, snapshot_hash=digest(snapshot)
    )
    db.add(release)
    number = previous.block_number + 1 if previous else 1
    previous_hash = previous.current_hash if previous else "0" * 64
    record = {
        "schema_version": 1,
        "block_number": number,
        "batch_id": batch.id,
        "farmer_id": keeper.id,
        "origin": snapshot["origin"],
        "extraction_date": snapshot["extracted_at"],
        "quantity_kg": snapshot["quantity_kg"],
        "honey_type": ext.honey_type,
        "result_id": row.id,
        "lab_id": row.lab_id,
        "lab_result_hash": digest(result_record(row)),
        "officer_id": officer.id,
        "approval_timestamp": approved.isoformat(),
        "snapshot_hash": release.snapshot_hash,
        "previous_hash": previous_hash,
    }
    block = LedgerBlock(
        block_number=number,
        batch_id=batch.id,
        previous_hash=previous_hash,
        current_hash=digest(record),
        canonical_record=record,
    )
    db.add(block)
    db.add(
        Review(
            batch_id=batch.id,
            officer_id=officer.id,
            result_id=row.id,
            decision="APPROVED",
            reason=body.comment,
            timestamp=approved,
        )
    )
    for name in (
        "APPROVED",
        "BATCH_RELEASE",
        "LEDGER_BLOCK_CREATED",
        "PUBLICLY_VERIFIABLE",
    ):
        event(db, batch, name)
    for action in ("KVIC_APPROVED", "RELEASE_CREATED", "LEDGER_CREATED"):
        audit(db, user, action, "batch", batch.id)
    batch.state = "PUBLICLY_VERIFIABLE"
    db.commit()
    return {
        "batch_id": batch.id,
        "state": batch.state,
        "block_number": number,
        "public_url": request.app.state.settings.public_url.rstrip("/")
        + "/?batch="
        + quote(batch.id),
    }


@router.post("/api/kvic/batches/{batch_id}/reject")
def reject(
    batch_id: str, body: RejectionIn, user=Depends(officer_role), db=Depends(get_db)
):
    batch = scoped_batch(db, user, batch_id)
    if batch.state not in ("PENDING_LAB", "PENDING_KVIC_REVIEW"):
        raise HTTPException(409, "Batch is closed")
    lock_batch(db, batch, body.expected_version)
    row = latest_result(db, batch.id)
    batch.state = "REJECTED"
    db.add(
        Review(
            batch_id=batch.id,
            officer_id=profile(db, user, Officer).id,
            result_id=row.id if row else None,
            decision="REJECTED",
            reason=body.reason,
        )
    )
    event(db, batch, "REJECTED")
    audit(db, user, "KVIC_REJECTED", "batch", batch.id)
    db.commit()
    return batch_view(db, batch)


def public_result(db, batch_id, include_passport=True):
    release = db.scalar(select(Release).where(Release.batch_id == batch_id))
    batch = db.get(Batch, batch_id)
    if not release or not batch or batch.state != "PUBLICLY_VERIFIABLE":
        raise HTTPException(404, "NOT FOUND / NOT PUBLICLY RELEASED")
    valid, number = verify(db, batch_id)
    if not valid:
        audit(db, None, "INTEGRITY_VERIFICATION_FAILED", "batch", batch_id)
        db.commit()
    result = {
        "batch_id": batch_id,
        "status": "VERIFIED" if valid else "RECORD INTEGRITY FAILED",
        "message": "Approved digital record integrity verified."
        if valid
        else "RECORD INTEGRITY VERIFICATION FAILED",
        "detail": "This verifies a digital batch record, not physical honey purity."
        if valid
        else "Protected batch data does not match the approved ledger record.",
        "block_number": number,
        "checked_at": now().isoformat(),
        "ledger_type": "Cryptographically linked append-only batch ledger",
        "evidence": {
            "producer_registration": True if valid else None,
            "extraction_recorded": True if valid else None,
            "lab_result_finalized": True if valid else None,
            "institutional_approval": True if valid else None,
            "ledger_integrity": valid,
        },
    }
    if include_passport:
        result["passport"] = public_allowlist(release.snapshot) if valid else None
    block = db.scalar(select(LedgerBlock).where(LedgerBlock.batch_id == batch_id))
    if block:
        result["block_hash"] = block.current_hash
        result["previous_hash"] = block.previous_hash
    return result


@router.get("/api/public/batches/{batch_id}/blockchain")
def blockchain_view(batch_id: str, db=Depends(get_db)):
    blocks = list(db.scalars(select(LedgerBlock).order_by(LedgerBlock.block_number)))
    target = next((b for b in blocks if b.batch_id == batch_id), None)
    if not target:
        raise HTTPException(404, "No ledger record for this batch")
    valid, number = verify(db, batch_id)
    return {
        "batch_id": batch_id,
        "chain_valid": valid,
        "ledger_protocol": "Cryptographically Linked Append-Only Hash Chain",
        "immutability_standard": "SHA-256 Merkle-Linked Sequential Blocks",
        "blocks": [
            {
                "block_number": b.block_number,
                "batch_id": b.batch_id,
                "previous_hash": b.previous_hash,
                "current_hash": b.current_hash,
                "snapshot_hash": b.canonical_record.get("snapshot_hash"),
                "lab_result_hash": b.canonical_record.get("lab_result_hash"),
                "approval_timestamp": b.canonical_record.get("approval_timestamp"),
            }
            for b in blocks
        ],
    }


@router.get("/api/public/batches/{batch_id}")
def passport(batch_id: str, db=Depends(get_db)):
    return public_result(db, batch_id)


@router.get("/api/public/batches/{batch_id}/verify")
def verification(batch_id: str, db=Depends(get_db)):
    return public_result(db, batch_id, False)


@router.get("/api/public/batches/{batch_id}/qr")
def qr(batch_id: str, request: Request, db=Depends(get_db)):
    result = public_result(db, batch_id, False)
    if result["status"] != "VERIFIED":
        raise HTTPException(409, result["message"])
    img = qrcode.make(
        request.app.state.settings.public_url.rstrip("/") + "/?batch=" + quote(batch_id)
    )
    out = BytesIO()
    img.save(out, format="PNG")
    return Response(out.getvalue(), media_type="image/png")
