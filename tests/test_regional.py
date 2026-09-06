from datetime import timedelta
from simulator.simulator import replay
from backend.regional_engine import regional
from backend.models import Jurisdiction
from backend.database import now
from conftest import login


def test_cluster_and_jurisdiction(env):
    app, c, creds = env
    replay(c, creds, "REGIONAL_CLUSTER")
    r = c.get("/api/kvic/regional-alerts", headers=login(c, "officer.nas")).json()[
        "items"
    ][0]
    assert (
        r["status"] == "REGIONAL_ANOMALY_ALERT"
        and r["affected_apiaries"] == 2
        and r["sufficiently_reporting_apiaries"] == 5
    )
    assert r["affected_percentage"] == 40
    other = c.get("/api/kvic/regional-alerts", headers=login(c, "officer.pun")).json()[
        "items"
    ][0]
    assert (
        other["sufficiently_reporting_apiaries"] == 0
        and other["status"] == "INSUFFICIENT_DATA"
    )
    assert (
        c.get("/api/kvic/overview", headers=login(c, "beekeeper.1")).status_code == 403
    )
    with app.state.sessions() as db:
        later = regional(
            db,
            db.get(Jurisdiction, "MH-NAS"),
            app.state.settings,
            now() + timedelta(hours=49),
        )
        assert (
            later["status"] == "INSUFFICIENT_DATA" and later["affected_apiaries"] == 0
        )


def test_small_denominator_not_alarm(env):
    app, c, creds = env
    replay(c, creds, "TEMPERATURE_STRESS", device_index=0)
    replay(c, creds, "NORMAL_HIVE", device_index=1)
    replay(c, creds, "NORMAL_HIVE", device_index=2)
    r = c.get("/api/kvic/regional-alerts", headers=login(c, "officer.nas")).json()[
        "items"
    ][0]
    assert r["affected_apiaries"] == 1 and r["sufficiently_reporting_apiaries"] == 3
    assert r["status"] == "INSUFFICIENT_DATA"
