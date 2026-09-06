from uuid import uuid4
from backend.database import now
from sqlalchemy import select, func
from backend.models import Batch, Audit
from conftest import login


def extraction_body():
    return {
        "client_operation_id": str(uuid4()),
        "apiary_id": "APIARY-MH-88492",
        "source_hive_ids": ["HIVE-MH-88492-01"],
        "extracted_at": now().isoformat(),
        "quantity_kg": "5.250",
        "honey_type": "Synthetic floral source",
    }


def test_extraction_sync_and_scope(env):
    app, c, _ = env
    h = login(c, "beekeeper.1")
    body = extraction_body()
    r = c.post("/api/beekeeper/extractions", headers=h, json=body)
    assert r.status_code == 200, r.text
    bid = r.json()["batch_id"]
    assert r.json()["state"] == "PENDING_LAB"
    for _ in range(2):
        result = c.post(
            "/api/sync/extractions", headers=h, json={"operations": [body]}
        ).json()["items"][0]
        assert result["result"]["duplicate"] and result["result"]["batch_id"] == bid
    assert (
        c.post(
            "/api/beekeeper/extractions", headers=h, json=body | {"quantity_kg": "6"}
        ).status_code
        == 409
    )
    assert (
        c.post(
            "/api/beekeeper/extractions",
            headers=login(c, "beekeeper.2"),
            json=extraction_body(),
        ).status_code
        == 404
    )
    assert (
        c.post(
            "/api/beekeeper/extractions",
            headers=login(c, "lab.1"),
            json=extraction_body(),
        ).status_code
        == 403
    )
    assert (
        c.get(
            "/api/beekeeper/batches/" + bid, headers=login(c, "beekeeper.2")
        ).status_code
        == 404
    )
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Batch)) == 1
        assert db.scalar(select(Audit).where(Audit.action == "EXTRACTION_CREATED"))
