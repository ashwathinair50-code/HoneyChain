from datetime import timedelta
from sqlalchemy import select
from backend.database import now
from backend.models import Extraction, ExtractionHive, User, Alert, Device
from backend.ledger import text_hash
from simulator.simulator import replay
from conftest import login
from test_lab_security import setup_batch, result_body
from test_batches import extraction_body


def test_normal_to_weight_drop(env):
    app, c, creds = env
    replay(c, creds, "NORMAL_HIVE")
    replay(c, creds, "WEIGHT_DROP_EVENT")
    data = c.get(
        "/api/hives/" + creds["devices"][0]["hive_id"] + "/status",
        headers=login(c, "beekeeper.1"),
    ).json()
    assert any(
        a["type"] == "POSSIBLE_SWARMING_PATTERN" for a in data["interpreted"]["alerts"]
    )


def test_recorded_extraction_explains_drop(env):
    app, c, creds = env
    body = extraction_body() | {
        "extracted_at": (now() - timedelta(minutes=25)).isoformat()
    }
    assert (
        c.post(
            "/api/beekeeper/extractions", headers=login(c, "beekeeper.1"), json=body
        ).status_code
        == 200
    )
    replay(c, creds, "WEIGHT_DROP_EVENT")
    data = c.get(
        "/api/hives/" + creds["devices"][0]["hive_id"] + "/status",
        headers=login(c, "beekeeper.1"),
    ).json()
    assert not any(
        a["type"] == "POSSIBLE_SWARMING_PATTERN" for a in data["interpreted"]["alerts"]
    )
    assert "weight_loss_context" in data["derived"]


def test_report_hash_preserves_file_whitespace(env):
    app, c, _ = env
    bid, k, o, l = setup_batch(c)
    content = "SYNTHETIC DEMO LAB REPORT\r\n  spaces retained  \r\n"
    r = c.post(
        "/api/lab/batches/" + bid + "/results",
        headers=l,
        json=result_body() | {"report_content": content},
    )
    assert r.status_code == 200, r.text
    assert r.json()["report_sha256"] == text_hash(content)


def test_revoked_device_and_empty_history(env):
    app, c, creds = env
    h = login(c, "beekeeper.1")
    did = creds["devices"][0]["device_id"]
    data = c.get(
        "/api/hives/" + creds["devices"][0]["hive_id"] + "/status", headers=h
    ).json()
    assert (
        data["measured"] is None
        and data["interpreted"]["coverage"] == "INSUFFICIENT_DATA"
    )
    with app.state.sessions() as db:
        device = db.get(Device, did)
        device.active = False
        db.commit()
    from simulator.scenarios import payload

    r = c.post(
        "/api/telemetry",
        headers={"X-Device-Key": creds["devices"][0]["key"]},
        json=payload(creds["devices"][0], (now(), 38, 35, 58)),
    )
    assert r.status_code == 401


def test_nonnumeric_nan_and_empty_lab_reference(env):
    app, c, creds = env
    import json
    from simulator.scenarios import payload

    d = creds["devices"][0]
    body = payload(d, (now(), 38, 35, 58))
    headers = {"X-Device-Key": d["key"]}
    assert (
        c.post(
            "/api/telemetry", headers=headers, json=body | {"weight_kg": "38"}
        ).status_code
        == 422
    )
    nan = json.dumps(body).replace('"weight_kg": 38', '"weight_kg": NaN')
    r = c.post(
        "/api/telemetry",
        headers=headers | {"Content-Type": "application/json"},
        content=nan,
    )
    assert r.status_code == 422, r.text
    bid, k, o, l = setup_batch(c)
    r = c.post(
        "/api/lab/batches/" + bid + "/results",
        headers=l,
        json=result_body() | {"evidence_reference": "   "},
    )
    assert r.status_code == 422


def test_failing_finalized_outcome_cannot_release(env):
    app, c, _ = env
    bid, k, o, l = setup_batch(c)
    r = c.post(
        "/api/lab/batches/" + bid + "/results",
        headers=l,
        json=result_body() | {"outcome": "FAIL"},
    ).json()
    f = c.post(
        "/api/lab/results/" + r["result_id"] + "/finalize",
        headers=l,
        json={"expected_version": 1},
    ).json()
    assert f["batch_state"] == "PENDING_LAB"
    denied = c.post(
        "/api/kvic/batches/" + bid + "/approve",
        headers=o,
        json={
            "expected_version": f["batch_version"],
            "finalized_result_id": r["result_id"],
        },
    )
    assert denied.status_code == 409
