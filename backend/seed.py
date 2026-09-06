"""Explicit synthetic setup. No implicit production seeding."""

import json, secrets
from .models import (
    User,
    Jurisdiction,
    Officer,
    Beekeeper,
    Apiary,
    Hive,
    Device,
    Lab,
    LabOperator,
    LedgerHead,
)
from .security import hash_password, hash_key
from .config import Settings


def seed(db, password=None):
    if db.query(User).first():
        raise ValueError("Database already seeded")
    password = password or secrets.token_urlsafe(18)
    credentials = {"password": password, "accounts": {}, "devices": []}
    for district, name in [("NAS", "Nashik"), ("PUN", "Pune")]:
        jid = "MH-" + district
        db.add(Jurisdiction(id=jid, state="MH", district=district, name=name))
        db.flush()
        username = "officer." + district.lower()
        user = User(
            username=username,
            password_hash=hash_password(password),
            role="KVIC_ADMIN",
            display_name="Demo " + name + " Officer",
        )
        db.add(user)
        db.flush()
        db.add(
            Officer(
                id="KVIC-MH-" + district + "-001", user_id=user.id, jurisdiction_id=jid
            )
        )
        credentials["accounts"][username] = "KVIC_ADMIN"
    for n in range(1, 7):
        bid = f"NHM-MH-{88491 + n}"
        user = User(
            username=f"beekeeper.{n}",
            password_hash=hash_password(password),
            role="BEEKEEPER",
            display_name=f"Synthetic Producer {n}",
        )
        db.add(user)
        db.flush()
        db.add(Beekeeper(id=bid, user_id=user.id))
        db.flush()
        aid = f"APIARY-MH-{88491 + n}"
        db.add(
            Apiary(
                id=aid,
                beekeeper_id=bid,
                jurisdiction_id="MH-NAS" if n <= 5 else "MH-PUN",
                name=f"Demo Apiary {n}",
            )
        )
        db.flush()
        hid = f"HIVE-MH-{88491 + n}-01"
        db.add(
            Hive(
                id=hid,
                apiary_id=aid,
                baseline_kg=32,
                harvest_target_kg=Settings().harvest_target,
            )
        )
        db.flush()
        key = secrets.token_urlsafe(32)
        did = f"DEV-MH-{88491 + n}-01"
        db.add(
            Device(id=did, hive_id=hid, key_hash=hash_key(key), source_type="SIMULATOR")
        )
        credentials["accounts"][user.username] = "BEEKEEPER"
        credentials["devices"].append(
            {"device_id": did, "hive_id": hid, "beekeeper_id": bid, "key": key}
        )
    for n in (1, 2):
        lid = f"LAB-MH-004{n + 1}"
        db.add(Lab(id=lid, name=f"SYNTHETIC DEMO LAB {n}"))
        db.flush()
        user = User(
            username=f"lab.{n}",
            password_hash=hash_password(password),
            role="LAB_OPERATOR",
            display_name=f"Demo Lab Operator {n}",
        )
        db.add(user)
        db.flush()
        db.add(LabOperator(user_id=user.id, lab_id=lid))
        credentials["accounts"][user.username] = "LAB_OPERATOR"
    db.add(LedgerHead(id=1, version=0))
    db.commit()
    from .demo_accounts import install
    install(db)
    return credentials


if __name__ == "__main__":
    from .config import Settings, ROOT
    from .database import connect, Base

    engine, sessions = connect(Settings().database_url)
    Base.metadata.create_all(engine)
    with sessions() as db:
        credentials = seed(db)
    (ROOT / "demo-credentials.json").write_text(
        json.dumps(credentials, indent=2), encoding="utf-8"
    )
    print(
        "Synthetic accounts created. Private local credentials: demo-credentials.json"
    )
