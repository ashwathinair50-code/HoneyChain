"""Create disposable synthetic demo data through the same APIs used by the UI."""

import json, secrets
from pathlib import Path
from datetime import datetime, timezone, timedelta
from uuid import uuid4


def main():
    root = Path(__file__).resolve().parents[1]
    if not (root / ".env").exists():
        (root / ".env").write_text(
            "DEMO_MODE=true\nJWT_SECRET="
            + secrets.token_urlsafe(48)
            + "\nPUBLIC_URL=http://127.0.0.1:8000\nCORS_ORIGINS=http://127.0.0.1:8000\n",
            encoding="utf-8",
        )
    from .config import Settings
    from .app import create_app
    from .seed import seed
    from .models import User
    from fastapi.testclient import TestClient
    from simulator.simulator import replay

    app = create_app(Settings())
    from .demo_accounts import install
    with app.state.sessions() as db:
        if db.query(User).first():
            install(db)
            print(
                "Database already initialized; no data replaced. Use existing demo-credentials.json."
            )
            from .qr_demo import main as install_qr_demo
            install_qr_demo()
            return
        creds = seed(db)
    (root / "demo-credentials.json").write_text(
        json.dumps(creds, indent=2), encoding="utf-8"
    )
    with TestClient(app) as c:
        end = datetime.now(timezone.utc)
        for index, mode in enumerate(
            [
                "NORMAL_HIVE",
                "TEMPERATURE_STRESS",
                "TEMPERATURE_STRESS",
                "HARVEST_READY",
                "SENSOR_FAILURE",
                "NORMAL_HIVE",
            ]
        ):
            replay(c, creds, mode, end=end, device_index=index)

        def login(name):
            r = c.post(
                "/api/auth/login",
                json={"username": name, "password": creds["password"]},
            )
            r.raise_for_status()
            from .qr_demo import main as install_qr_demo
            install_qr_demo()
            return {"Authorization": "Bearer " + r.json()["access_token"]}

        k, o, l = login("beekeeper.1"), login("officer.nas"), login("lab.1")
        summary = {}
        for purpose in ("pending_lab", "pending_review", "rejected", "released"):
            body = {
                "client_operation_id": str(uuid4()),
                "apiary_id": "APIARY-MH-88492",
                "source_hive_ids": ["HIVE-MH-88492-01"],
                "extracted_at": (end - timedelta(days=2)).isoformat(),
                "quantity_kg": "5.250",
                "honey_type": "Synthetic floral source",
            }
            r = c.post("/api/beekeeper/extractions", headers=k, json=body)
            r.raise_for_status()
            bid = r.json()["batch_id"]
            summary[purpose] = bid
            r = c.post(
                "/api/kvic/batches/" + bid + "/assign-lab",
                headers=o,
                json={"lab_id": "LAB-MH-0042", "expected_version": 1},
            )
            r.raise_for_status()
            if purpose == "pending_lab":
                continue
            evidence = (
                "SYNTHETIC DEMO LAB REPORT\nNot a real FSSAI/KVIC laboratory certificate.\nBatch: "
                + bid
                + "\nMoisture: 17.5% (synthetic).\nOutcome: PASS (demonstration policy only).\n"
            )
            r = c.post(
                "/api/lab/batches/" + bid + "/results",
                headers=l,
                json={
                    "report_reference": "SYNTHETIC-DEMO-" + purpose.upper(),
                    "tested_at": (end - timedelta(days=1)).isoformat(),
                    "parameters": [
                        {
                            "code": "Moisture",
                            "value": "17.5",
                            "unit": "%",
                            "method": "Synthetic demonstration",
                        }
                    ],
                    "outcome": "PASS",
                    "evidence_reference": "SYNTHETIC DEMO LAB REPORT.txt",
                    "report_content": evidence,
                },
            )
            r.raise_for_status()
            rid = r.json()["result_id"]
            r = c.post(
                "/api/lab/results/" + rid + "/finalize",
                headers=l,
                json={"expected_version": 1},
            )
            r.raise_for_status()
            version = r.json()["batch_version"]
            if purpose == "rejected":
                r = c.post(
                    "/api/kvic/batches/" + bid + "/reject",
                    headers=o,
                    json={
                        "expected_version": version,
                        "reason": "Synthetic demonstration rejection: source documentation requires clarification",
                    },
                )
                r.raise_for_status()
            if purpose == "released":
                r = c.post(
                    "/api/kvic/batches/" + bid + "/approve",
                    headers=o,
                    json={
                        "expected_version": version,
                        "finalized_result_id": rid,
                        "comment": "Synthetic SIH review only",
                    },
                )
                r.raise_for_status()
        (root / "demo-batches.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        print("Synthetic demo ready. Public batch: " + summary["released"])
        print("Credentials: demo-credentials.json (private local file; do not commit)")


    from .qr_demo import main as install_qr_demo
    install_qr_demo()

if __name__ == "__main__":
    main()
