import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from backend.models import User, Telemetry
from backend.permissions import own_hive, scoped_apiaries
from backend.auth import device_auth, roles
from backend.security import verify_password
from backend.database import now
from conftest import login


def test_auth_and_hashes(env):
    app, c, _ = env
    assert c.get("/api/auth/me").status_code == 401
    assert (
        c.post(
            "/api/auth/login", json={"username": "beekeeper.1", "password": "wrong"}
        ).status_code
        == 401
    )
    h = login(c, "beekeeper.1")
    me = c.get("/api/auth/me", headers=h).json()
    assert me["role"] == "BEEKEEPER" and "password_hash" not in me
    with app.state.sessions() as db:
        user = db.scalar(select(User).where(User.username == "beekeeper.1"))
        assert user.password_hash.startswith("$argon2") and verify_password(
            "Test-only-password!", user.password_hash
        )
        user.active = False
        db.commit()
    assert c.get("/api/auth/me", headers=h).status_code == 401


def test_ownership_jurisdiction_lab_separation(env):
    app, c, creds = env
    with app.state.sessions() as db:
        users = {u.username: u for u in db.scalars(select(User))}
        assert own_hive(db, users["beekeeper.1"], creds["devices"][0]["hive_id"])
        for username, index in [("beekeeper.1", 1), ("officer.nas", 5), ("lab.1", 0)]:
            with pytest.raises(HTTPException):
                own_hive(db, users[username], creds["devices"][index]["hive_id"])
        assert len(scoped_apiaries(db, users["officer.nas"])) == 5
        for username in ("beekeeper.1", "officer.nas"):
            with pytest.raises(HTTPException):
                roles("LAB_OPERATOR")(users[username])
        with pytest.raises(HTTPException):
            roles("KVIC_ADMIN")(users["lab.1"])


def test_device_and_constraints(env):
    app, _, creds = env
    d = creds["devices"][0]
    with app.state.sessions() as db:
        assert device_auth(db, d["device_id"], d["key"]).hive_id == d["hive_id"]
        for did, key in [(d["device_id"], "invalid"), ("missing", d["key"])]:
            with pytest.raises(HTTPException):
                device_auth(db, did, key)
        db.add(
            Telemetry(
                device_id=d["device_id"],
                measured_at=now(),
                weight_kg=-1,
                temperature_c=35,
                humidity_percent=50,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
