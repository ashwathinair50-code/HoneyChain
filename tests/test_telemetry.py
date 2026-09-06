from datetime import timedelta
from sqlalchemy import select, func
from backend.database import now
from backend.models import Telemetry
from simulator.scenarios import payload
from simulator.simulator import replay
from conftest import login


def test_ingest_validation_duplicates_and_access(env):
    app, c, creds = env
    d = creds["devices"][0]
    p = payload(d, (now(), 38.2, 35.1, 58.2))
    h = {"X-Device-Key": d["key"]}
    assert c.post("/api/telemetry", json=p).status_code == 401
    assert (
        c.post("/api/telemetry", json=p, headers={"X-Device-Key": "bad"}).status_code
        == 401
    )
    assert (
        c.post(
            "/api/telemetry",
            json=p | {"hive_id": creds["devices"][1]["hive_id"]},
            headers=h,
        ).status_code
        == 403
    )
    for bad in (
        {"weight_kg": -1},
        {"temperature_c": 150},
        {"humidity_percent": 500},
        {"timestamp": "2026-09-05T14:10:00"},
        {"timestamp": (now() + timedelta(days=1)).isoformat()},
    ):
        assert c.post("/api/telemetry", json=p | bad, headers=h).status_code == 422
    assert c.post("/api/telemetry", json=p, headers=h).status_code == 200
    assert c.post("/api/telemetry", json=p, headers=h).json()["duplicate"]
    assert (
        c.post("/api/telemetry", json=p | {"weight_kg": 39}, headers=h).status_code
        == 409
    )
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Telemetry)) == 1
    path = "/api/hives/" + d["hive_id"] + "/telemetry"
    assert c.get(path, headers=login(c, "beekeeper.1")).status_code == 200
    assert c.get(path, headers=login(c, "beekeeper.2")).status_code == 404
    assert c.get(path, headers=login(c, "officer.pun")).status_code == 404
    assert c.get(path, headers=login(c, "lab.1")).status_code == 403


def test_simulator_contract_and_late_data(env):
    app, c, creds = env
    assert replay(c, creds, "NORMAL_HIVE") == 7
    d = creds["devices"][0]
    h = login(c, "beekeeper.1")
    before = c.get("/api/hives/" + d["hive_id"] + "/status", headers=h).json()[
        "measured"
    ]["timestamp"]
    p = payload(d, (now() - timedelta(days=2), 37, 35, 58))
    assert (
        c.post("/api/telemetry", json=p, headers={"X-Device-Key": d["key"]}).status_code
        == 200
    )
    after = c.get("/api/hives/" + d["hive_id"] + "/status", headers=h).json()[
        "measured"
    ]["timestamp"]
    assert before == after
