from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select, func, update
from backend.models import Release, LedgerBlock, Audit, LabResult
from conftest import login
from test_lab_security import setup_batch, result_body


def ready(c):
    bid, keeper, officer, lab = setup_batch(c)
    r = c.post(
        "/api/lab/batches/" + bid + "/results", headers=lab, json=result_body()
    ).json()
    f = c.post(
        "/api/lab/results/" + r["result_id"] + "/finalize",
        headers=lab,
        json={"expected_version": 1},
    )
    assert f.status_code == 200, f.text
    return (
        bid,
        keeper,
        officer,
        lab,
        {
            "expected_version": f.json()["batch_version"],
            "finalized_result_id": r["result_id"],
        },
    )


def test_release_permissions_privacy_and_tamper(env):
    app, c, _ = env
    bid, k, o, l, body = ready(c)
    assert c.get("/api/public/batches/" + bid).status_code == 404
    path = "/api/kvic/batches/" + bid + "/approve"
    for h in (k, l):
        assert c.post(path, headers=h, json=body).status_code == 403
    assert c.post(path, headers=login(c, "officer.pun"), json=body).status_code == 404
    response = c.post(path, headers=o, json=body)
    assert response.status_code == 200, response.text
    assert c.post(path, headers=o, json=body).status_code == 409
    result = c.get("/api/public/batches/" + bid)
    assert result.json()["status"] == "VERIFIED", result.text
    for field in (
        "password",
        "key_hash",
        "submitted_by",
        "officer_id",
        "hive_id",
        "phone",
        "report_content",
    ):
        assert field not in result.text
    assert (
        c.get("/api/public/batches/" + bid + "/qr").headers["content-type"]
        == "image/png"
    )
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Release)) == 1
        release = db.scalar(select(Release).where(Release.batch_id == bid))
        release.snapshot = release.snapshot | {"quantity_kg": "999.000"}
        db.commit()
    response = c.get("/api/public/batches/" + bid)
    assert response.json()["message"] == "RECORD INTEGRITY VERIFICATION FAILED"
    assert response.json()["passport"] is None
    with app.state.sessions() as db:
        assert db.scalar(
            select(Audit).where(Audit.action == "INTEGRITY_VERIFICATION_FAILED")
        )


def test_rejected_pending_and_changed_lab(env):
    app, c, _ = env
    bid, k, o, l, body = ready(c)
    with app.state.sessions() as db:
        row = db.get(LabResult, body["finalized_result_id"])
        row.parameters = [{"code": "altered"}]
        db.commit()
    assert (
        c.post(
            "/api/kvic/batches/" + bid + "/approve", headers=o, json=body
        ).status_code
        == 409
    )
    response = c.post(
        "/api/kvic/batches/" + bid + "/reject",
        headers=o,
        json={
            "expected_version": body["expected_version"],
            "reason": "Evidence integrity failed",
        },
    )
    assert response.status_code == 200, response.text
    assert c.get("/api/public/batches/" + bid).status_code == 404
    assert c.get("/api/public/batches/" + bid + "/verify").status_code == 404


def test_concurrent_duplicate_approval(env):
    app, c, _ = env
    bid, k, o, l, body = ready(c)

    def approve():
        return c.post(
            "/api/kvic/batches/" + bid + "/approve", headers=o, json=body
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(lambda _: approve(), range(2)))
    assert sorted(statuses) == [200, 409], statuses
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Release)) == 1
        assert db.scalar(select(func.count()).select_from(LedgerBlock)) == 1
