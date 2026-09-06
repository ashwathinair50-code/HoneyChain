from simulator.simulator import replay
from sqlalchemy import select
from backend.models import LabResult, LedgerBlock, Release
from backend.ledger import verify
from test_release import ready
from conftest import login


def test_full_vertical_slice(env):
    app, c, creds = env
    replay(c, creds, "WEIGHT_DROP_EVENT")
    h = login(c, "beekeeper.1")
    alerts = c.get(
        "/api/hives/" + creds["devices"][0]["hive_id"] + "/alerts", headers=h
    ).json()["items"]
    assert any(a["type"] == "POSSIBLE_SWARMING_PATTERN" for a in alerts)
    replay(c, creds, "REGIONAL_CLUSTER")
    assert (
        c.get("/api/kvic/overview", headers=login(c, "officer.nas")).json()[
            "regional_alerts"
        ]
        == 1
    )
    bid, k, o, l, body = ready(c)
    response = c.post("/api/kvic/batches/" + bid + "/approve", headers=o, json=body)
    assert response.status_code == 200, response.text
    assert (
        c.get("/api/public/batches/" + bid + "/verify").json()["status"] == "VERIFIED"
    )
    with app.state.sessions() as db:
        result = db.get(LabResult, body["finalized_result_id"])
        result.report_content += "\nALTERED"
        db.commit()
    assert (
        c.get("/api/public/batches/" + bid + "/verify").json()["message"]
        == "RECORD INTEGRITY VERIFICATION FAILED"
    )


def test_predecessor_integrity_and_closed_lab(env):
    app, c, _ = env
    ids = []
    for _ in range(2):
        bid, k, o, l, body = ready(c)
        assert (
            c.post(
                "/api/kvic/batches/" + bid + "/approve", headers=o, json=body
            ).status_code
            == 200
        )
        ids.append(bid)
    with app.state.sessions() as db:
        assert verify(db, ids[1])[0]
        first = db.scalar(select(LedgerBlock).where(LedgerBlock.batch_id == ids[0]))
        first.current_hash = "a" * 64
        db.commit()
    assert (
        c.get("/api/public/batches/" + ids[1]).json()["status"]
        == "RECORD INTEGRITY FAILED"
    )
