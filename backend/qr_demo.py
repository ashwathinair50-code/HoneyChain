"""Install the named QR demonstration using real lab and approval transitions."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from sqlalchemy import select
from fastapi.testclient import TestClient
from .models import Batch, User
from .schemas import ExtractionIn
from .batches import create_extraction

DEMO_BATCH_ID = "HC-MH-NAS-2026-00184"

def ensure_qr_demo(app, credentials):
    with TestClient(app) as client:
        with app.state.sessions() as db:
            exists = db.get(Batch, DEMO_BATCH_ID)
            if not exists:
                keeper = db.scalar(select(User).where(User.username == "beekeeper.1"))
                demo_now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
                body = ExtractionIn(
                    client_operation_id="de24d4e0-6ef7-4c24-8419-2ba6308e0184",
                    apiary_id="APIARY-MH-88492",
                    source_hive_ids=["HIVE-MH-88492-01"],
                    extracted_at=datetime(2026,9,3,8,0,tzinfo=timezone.utc),
                    quantity_kg="5.250",
                    honey_type="Synthetic floral source",
                )
                create_extraction(db, keeper, body, seed_batch_id=DEMO_BATCH_ID)
                db.commit()
        def login(name):
            r=client.post("/api/auth/login",json={"username":name,"password":credentials["password"]})
            r.raise_for_status()
            return {"Authorization":"Bearer "+r.json()["access_token"]}
        officer,lab=login("officer.nas"),login("lab.1")
        def detail():
            r=client.get("/api/kvic/batches/"+DEMO_BATCH_ID,headers=officer);r.raise_for_status();return r.json()
        batch=detail()
        if batch["state"]=="REJECTED":
            raise RuntimeError("Named demo was rejected; it will not be overwritten.")
        if not batch["assigned_lab_id"]:
            r=client.post("/api/kvic/batches/"+DEMO_BATCH_ID+"/assign-lab",headers=officer,json={"lab_id":"LAB-MH-0042","expected_version":batch["version"]})
            r.raise_for_status();batch=detail()
        if not batch["lab_results"]:
            report="SYNTHETIC DEMO LAB REPORT\nBatch: "+DEMO_BATCH_ID+"\nNo physical honey was tested. Not a real FSSAI/KVIC certificate.\nMoisture: 17.5% (synthetic).\n"
            r=client.post("/api/lab/batches/"+DEMO_BATCH_ID+"/results",headers=lab,json={
                "report_reference":"SYNTHETIC-DEMO-00184",
                "tested_at":"2026-09-04T08:00:00Z",
                "parameters":[{"code":"Moisture","value":"17.5","unit":"%","method":"Synthetic demonstration"}],
                "outcome":"PASS",
                "evidence_reference":"SYNTHETIC DEMO LAB REPORT 00184.txt",
                "report_content":report,
            });r.raise_for_status();batch=detail()
        latest=batch["lab_results"][-1]
        if latest["status"]!="LAB_RESULT_FINALIZED":
            r=client.post("/api/lab/results/"+latest["result_id"]+"/finalize",headers=lab,json={"expected_version":latest["version"]})
            r.raise_for_status();batch=detail()
        if batch["state"]!="PUBLICLY_VERIFIABLE":
            r=client.post("/api/kvic/batches/"+DEMO_BATCH_ID+"/approve",headers=officer,json={"expected_version":batch["version"],"finalized_result_id":latest["result_id"],"comment":"Synthetic QR demonstration record."})
            r.raise_for_status()
        r=client.get("/api/public/batches/"+DEMO_BATCH_ID);r.raise_for_status()
        if r.json()["status"]!="VERIFIED": raise RuntimeError("Named demo record integrity failed; existing evidence was not changed.")
        return r.json()

def main():
    from .config import ROOT
    from .app import create_app
    credentials=json.loads((ROOT/"demo-credentials.json").read_text())
    result=ensure_qr_demo(create_app(),credentials)
    path=ROOT/"demo-batches.json"
    mapping=json.loads(path.read_text()) if path.exists() else {}
    mapping["qr_demo"]=DEMO_BATCH_ID
    path.write_text(json.dumps(mapping,indent=2))
    print(json.dumps({"batch":result["batch_id"],"status":result["status"],"origin":result["passport"]["origin"],"synthetic_demo":result["passport"]["synthetic_demo"]}))
if __name__=="__main__": main()
