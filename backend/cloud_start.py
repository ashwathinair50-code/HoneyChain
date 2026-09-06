"""Single-instance deployment with a persistent SQLite volume."""

import os
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from .app import create_app
from .config import Settings
from .models import User, Batch, Device
from .seed import seed
from .qr_demo import ensure_qr_demo, DEMO_BATCH_ID
from .demo_accounts import install
from .schemas import ExtractionIn
from .batches import create_extraction
from .security import hash_key


DEMO_BATCHES = {
    "pending_lab": "HC-MH-NAS-2026-13063D99F647",
    "pending_review": "HC-MH-NAS-2026-D0822E3FF018",
    "rejected": "HC-MH-NAS-2026-7DD52F21FD51",
    "released": "HC-MH-NAS-2026-FEA1FA11FD51",
}


def ensure_workflow_demo(app):
    """Create the four synthetic workflow demo batches if they are missing."""

    # Demo-account passwords from backend/demo_accounts.py
    beekeeper_headers = None
    officer_headers = None
    lab_headers = None

    with TestClient(app) as client:

        def login(username, password):
            response = client.post(
                "/api/auth/login",
                json={
                    "username": username,
                    "password": password,
                },
            )
            response.raise_for_status()
            return {
                "Authorization": "Bearer "
                + response.json()["access_token"]
            }

        beekeeper_headers = login(
            "NHM-MH-88492",
            "BeeDemo@2026",
        )

        officer_headers = login(
            "KVIC-MH-NAS-001",
            "KvicDemo@2026",
        )

        lab_headers = login(
            "LAB-MH-0042",
            "LabDemo@2026",
        )

        for purpose, batch_id in DEMO_BATCHES.items():

            # Check whether this deterministic batch already exists.
            with app.state.sessions() as db:
                batch = db.get(Batch, batch_id)

                if batch is None:
                    beekeeper = db.scalar(
                        __import__("sqlalchemy").select(User).where(
                            User.username == "beekeeper.1"
                        )
                    )

                    if not beekeeper:
                        raise RuntimeError(
                            "Demo beekeeper is missing"
                        )

                    body = ExtractionIn(
                        client_operation_id=uuid4(),
                        apiary_id="APIARY-MH-88492",
                        source_hive_ids=[
                            "HIVE-MH-88492-01"
                        ],
                        extracted_at=(
                            datetime.now(timezone.utc)
                            - timedelta(days=2)
                        ),
                        quantity_kg="5.250",
                        honey_type="Synthetic floral source",
                    )

                    create_extraction(
                        db,
                        beekeeper,
                        body,
                        seed_batch_id=batch_id,
                    )

                    db.commit()

                    batch = db.get(Batch, batch_id)

                if not batch:
                    raise RuntimeError(
                        "Failed to create demo batch " + batch_id
                    )

                state = batch.state
                version = batch.version

            # pending_lab intentionally stops before laboratory assignment.
            if purpose == "pending_lab":
                continue

            # Assign laboratory if the batch is still waiting for assignment.
            if state == "PENDING_LAB":
                response = client.post(
                    "/api/kvic/batches/"
                    + batch_id
                    + "/assign-lab",
                    headers=officer_headers,
                    json={
                        "lab_id": "LAB-MH-0042",
                        "expected_version": version,
                    },
                )
                response.raise_for_status()

                state = response.json()["state"]
                version = response.json()["version"]

            # If a lab result does not exist yet, create one.
            with app.state.sessions() as db:
                batch = db.get(Batch, batch_id)

                from .models import LabResult
                from sqlalchemy import select

                latest = db.scalar(
                    select(LabResult)
                    .where(LabResult.batch_id == batch_id)
                    .order_by(LabResult.version.desc())
                )

                result_id = latest.id if latest else None
                result_version = latest.version if latest else None
                finalized = (
                    latest.finalized_at is not None
                    if latest
                    else False
                )
                state = batch.state
                version = batch.version

            if not latest:
                evidence = (
                    "SYNTHETIC DEMO LAB REPORT\n"
                    "Not a real FSSAI/KVIC laboratory certificate.\n"
                    "Batch: "
                    + batch_id
                    + "\n"
                    "Moisture: 17.5% (synthetic).\n"
                    "Outcome: PASS "
                    "(demonstration policy only).\n"
                )

                response = client.post(
                    "/api/lab/batches/"
                    + batch_id
                    + "/results",
                    headers=lab_headers,
                    json={
                        "report_reference":
                            "SYNTHETIC-DEMO-"
                            + purpose.upper(),
                        "tested_at": (
                            datetime.now(timezone.utc)
                            - timedelta(days=1)
                        ).isoformat(),
                        "parameters": [
                            {
                                "code": "Moisture",
                                "value": "17.5",
                                "unit": "%",
                                "method":
                                    "Synthetic demonstration",
                            }
                        ],
                        "outcome": "PASS",
                        "evidence_reference":
                            "SYNTHETIC DEMO LAB REPORT.txt",
                        "report_content": evidence,
                    },
                )
                response.raise_for_status()

                result_id = response.json()["result_id"]
                result_version = response.json()["version"]

                finalized = False

            # Finalize the PASS result.
            if not finalized:
                response = client.post(
                    "/api/lab/results/"
                    + result_id
                    + "/finalize",
                    headers=lab_headers,
                    json={
                        "expected_version": result_version,
                    },
                )
                response.raise_for_status()

                state = response.json()["batch_state"]
                version = response.json()["batch_version"]

            # Rejected demo.
            if purpose == "rejected":
                if state != "REJECTED":
                    response = client.post(
                        "/api/kvic/batches/"
                        + batch_id
                        + "/reject",
                        headers=officer_headers,
                        json={
                            "expected_version": version,
                            "reason":
                                "Synthetic demonstration rejection: "
                                "source documentation requires "
                                "clarification",
                        },
                    )
                    response.raise_for_status()

            # Released demo.
            elif purpose == "released":
                if state != "PUBLICLY_VERIFIABLE":
                    # Refresh the batch version/state before approval.
                    response = client.get(
                        "/api/kvic/batches/"
                        + batch_id,
                        headers=officer_headers,
                    )
                    response.raise_for_status()

                    current = response.json()
                    version = current["version"]
                    state = current["state"]

                    if state != "PENDING_KVIC_REVIEW":
                        raise RuntimeError(
                            "Released demo batch "
                            + batch_id
                            + " is in unexpected state: "
                            + str(state)
                        )

                    response = client.post(
                        "/api/kvic/batches/"
                        + batch_id
                        + "/approve",
                        headers=officer_headers,
                        json={
                            "expected_version": version,
                            "finalized_result_id": result_id,
                            "comment":
                                "Synthetic SIH review only",
                        },
                    )
                    response.raise_for_status()

    print("Synthetic workflow demos ready.")

def ensure_demo_device_key(app):
    demo_key = os.getenv("DEMO_DEVICE_KEY")
    if not demo_key:
        return

    with app.state.sessions() as db:
        device = db.get(Device, "DEV-MH-88492-01")
        if device is None:
            raise RuntimeError("Demo telemetry device is missing")

        device.key_hash = hash_key(demo_key)
        device.active = True
        db.commit()


def initialize():
    settings = Settings()
    app = create_app(settings)

    if settings.demo_mode:
        with app.state.sessions() as db:
            empty = db.query(User).first() is None

            if empty:
                credentials = seed(db)
                install(db)
            else:
                credentials = None
                install(db)

        # Make sure the main QR demo exists.
        if credentials:
            ensure_qr_demo(app, credentials)
        else:
            with TestClient(app) as client:
                response = client.get(
                    "/api/public/batches/"
                    + DEMO_BATCH_ID
                )

                if (
                    response.status_code != 200
                    or response.json().get("status") != "VERIFIED"
                ):
                    raise RuntimeError(
                        "Existing demo database failed verification; "
                        "refusing to overwrite it"
                    )

        # Make sure the four workflow demo batches exist.
        ensure_demo_device_key(app)
        ensure_workflow_demo(app)

    app.state.engine.dispose()


if __name__ == "__main__":
    initialize()

    os.execvp(
        "uvicorn",
        [
            "uvicorn",
            "backend.app:create_app",
            "--factory",
            "--host",
            "0.0.0.0",
            "--port",
            os.getenv("PORT", "8000"),
            "--workers",
            "1",
        ],
    )