from backend.database import now
from conftest import login
from test_batches import extraction_body


def setup_batch(c):
    keeper = login(c, "beekeeper.1")
    officer = login(c, "officer.nas")
    lab = login(c, "lab.1")
    result = c.post(
        "/api/beekeeper/extractions", headers=keeper, json=extraction_body()
    ).json()
    bid = result["batch_id"]
    response = c.post(
        "/api/kvic/batches/" + bid + "/assign-lab",
        headers=officer,
        json={"lab_id": "LAB-MH-0042", "expected_version": 1},
    )
    assert response.status_code == 200, response.text
    return bid, keeper, officer, lab


def result_body():
    return {
        "report_reference": "SYNTHETIC-DEMO-001",
        "tested_at": now().isoformat(),
        "parameters": [
            {
                "code": "moisture",
                "value": "17.5",
                "unit": "%",
                "method": "Synthetic demonstration only",
            }
        ],
        "outcome": "PASS",
        "evidence_reference": "SYNTHETIC DEMO LAB REPORT.txt",
        "report_content": "SYNTHETIC DEMO LAB REPORT\nNot a real laboratory certificate.\nMoisture: 17.5% (synthetic).",
    }


def test_lab_security_versions_and_evidence(env):
    app, c, _ = env
    bid, keeper, officer, lab = setup_batch(c)
    path = "/api/lab/batches/" + bid + "/results"
    for h in (keeper, officer):
        assert c.post(path, headers=h, json=result_body()).status_code == 403
    assert (
        c.post(path, headers=login(c, "lab.2"), json=result_body()).status_code == 404
    )
    missing = result_body()
    del missing["evidence_reference"]
    assert c.post(path, headers=lab, json=missing).status_code == 422
    response = c.post(path, headers=lab, json=result_body())
    assert response.status_code == 200, response.text
    r = response.json()
    assert len(r["report_sha256"]) == 64
    finish = "/api/lab/results/" + r["result_id"] + "/finalize"
    assert (
        c.post(finish, headers=officer, json={"expected_version": 1}).status_code == 403
    )
    response = c.post(finish, headers=lab, json={"expected_version": 1})
    assert response.status_code == 200, response.text
    assert response.json()["batch_state"] == "PENDING_KVIC_REVIEW"
    assert c.post(finish, headers=lab, json={"expected_version": 1}).status_code == 409
    corrected = result_body() | {
        "outcome": "INCONCLUSIVE",
        "supersedes_result_id": r["result_id"],
    }
    r2 = c.post(path, headers=lab, json=corrected).json()
    assert r2["version"] == 2 and r2["result_id"] != r["result_id"]
    final = c.post(
        "/api/lab/results/" + r2["result_id"] + "/finalize",
        headers=lab,
        json={"expected_version": 2},
    )
    assert final.json()["batch_state"] == "PENDING_LAB"
    detail = c.get("/api/kvic/batches/" + bid, headers=officer).json()
    assert (
        len(detail["lab_results"]) == 2
        and detail["lab_results"][0]["status"] == "LAB_RESULT_FINALIZED"
    )
    assert (
        c.get("/api/kvic/batches/" + bid, headers=login(c, "officer.pun")).status_code
        == 404
    )
