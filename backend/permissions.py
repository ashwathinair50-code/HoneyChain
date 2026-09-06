from fastapi import HTTPException
from sqlalchemy import select
from .models import Beekeeper, Officer, LabOperator, Apiary, Hive, Batch, LabAssignment


def profile(db, user, model):
    item = db.scalar(select(model).where(model.user_id == user.id))
    if not item:
        raise HTTPException(403, "Role profile unavailable")
    return item


def scoped_apiaries(db, user):
    query = select(Apiary)
    if user.role == "BEEKEEPER":
        query = query.where(Apiary.beekeeper_id == profile(db, user, Beekeeper).id)
    elif user.role == "KVIC_ADMIN":
        query = query.where(
            Apiary.jurisdiction_id == profile(db, user, Officer).jurisdiction_id
        )
    else:
        raise HTTPException(403, "Role not permitted")
    return list(db.scalars(query))


def own_hive(db, user, hive_id):
    hive = db.get(Hive, hive_id)
    if not hive or hive.apiary_id not in {a.id for a in scoped_apiaries(db, user)}:
        raise HTTPException(404, "Hive not found")
    return hive


def scoped_batch(db, user, batch_id):
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found")
    if user.role == "LAB_OPERATOR":
        lab = profile(db, user, LabOperator)
        assignment = db.scalar(
            select(LabAssignment).where(
                LabAssignment.batch_id == batch.id, LabAssignment.lab_id == lab.lab_id
            )
        )
        if not assignment:
            raise HTTPException(404, "Batch not found")
    elif batch.extraction.apiary_id not in {a.id for a in scoped_apiaries(db, user)}:
        raise HTTPException(404, "Batch not found")
    return batch
