from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from .auth import roles, get_db
from .models import Batch, Extraction
from .permissions import scoped_apiaries, scoped_batch
from .schemas import ExtractionIn, SyncIn
from .batches import create_extraction, batch_view

router = APIRouter()
beekeeper = roles("BEEKEEPER")


def save_extraction(db, user, body):
    try:
        result = create_extraction(db, user, body)
        db.commit()
        return result
    except IntegrityError:
        db.rollback()
        result = create_extraction(db, user, body)
        db.commit()
        return result
    except OperationalError:
        db.rollback()
        raise HTTPException(409, "Concurrent write; retry the same operation ID")


@router.post("/api/beekeeper/extractions")
def extraction(body: ExtractionIn, user=Depends(beekeeper), db=Depends(get_db)):
    return save_extraction(db, user, body)


@router.post("/api/sync/extractions")
def sync(body: SyncIn, user=Depends(beekeeper), db=Depends(get_db)):
    items = []
    for operation in body.operations:
        try:
            items.append(
                {
                    "operation_id": str(operation.client_operation_id),
                    "status": "accepted",
                    "result": save_extraction(db, user, operation),
                }
            )
        except HTTPException as exc:
            db.rollback()
            items.append(
                {
                    "operation_id": str(operation.client_operation_id),
                    "status": "conflict" if exc.status_code == 409 else "invalid",
                    "error": exc.detail,
                }
            )
    return {"items": items}


@router.get("/api/beekeeper/batches")
def batches(user=Depends(beekeeper), db=Depends(get_db), state: str | None = None):
    ids = [a.id for a in scoped_apiaries(db, user)]
    query = (
        select(Batch)
        .join(Extraction, Batch.extraction_id == Extraction.id)
        .where(Extraction.apiary_id.in_(ids))
    )
    if state:
        query = query.where(Batch.state == state)
    return {"items": [batch_view(db, b) for b in db.scalars(query)]}


@router.get("/api/beekeeper/batches/{batch_id}")
def detail(batch_id: str, user=Depends(beekeeper), db=Depends(get_db)):
    return batch_view(db, scoped_batch(db, user, batch_id))
