import hashlib, json
from sqlalchemy import select
from .models import LabResult, Release, LedgerBlock


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def text_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def result_record(r):
    return {
        "id": r.id,
        "batch_id": r.batch_id,
        "lab_id": r.lab_id,
        "laboratory_name": r.laboratory_name,
        "submitted_by": r.submitted_by,
        "report_reference": r.report_reference,
        "tested_at": r.tested_at.isoformat(),
        "entered_at": r.entered_at.isoformat(),
        "parameters": r.parameters,
        "outcome": r.outcome,
        "evidence_reference": r.evidence_reference,
        "report_sha256": r.report_sha256,
        "version": r.version,
        "supersedes_id": r.supersedes_id,
        "finalized_at": r.finalized_at.isoformat() if r.finalized_at else None,
    }


def verify(db, batch_id):
    blocks = list(db.scalars(select(LedgerBlock).order_by(LedgerBlock.block_number)))
    target = next((b for b in blocks if b.batch_id == batch_id), None)
    if not target:
        return False, None
    previous = "0" * 64
    for index, block in enumerate(blocks, 1):
        if not isinstance(block.canonical_record, dict):
            return False, target.block_number
        if (
            block.block_number != index
            or block.previous_hash != previous
            or block.canonical_record.get("previous_hash") != previous
            or block.current_hash != digest(block.canonical_record)
        ):
            return False, target.block_number
        record = block.canonical_record
        if (
            record.get("batch_id") != block.batch_id
            or record.get("block_number") != index
        ):
            return False, target.block_number
        release = db.scalar(select(Release).where(Release.batch_id == block.batch_id))
        result = db.get(LabResult, record.get("result_id"))
        if (
            not release
            or digest(release.snapshot) != release.snapshot_hash
            or release.snapshot_hash != record.get("snapshot_hash")
        ):
            return False, target.block_number
        if (
            not result
            or not result.finalized_at
            or result.batch_id != block.batch_id
            or digest(result_record(result)) != record.get("lab_result_hash")
        ):
            return False, target.block_number
        if (
            result.report_content is not None
            and text_hash(result.report_content) != result.report_sha256
        ):
            return False, target.block_number
        previous = block.current_hash
        if block.id == target.id:
            return True, target.block_number
    return False, target.block_number
