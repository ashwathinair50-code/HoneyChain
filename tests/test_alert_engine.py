import pytest
from datetime import timedelta
from sqlalchemy import select
from backend.database import now
from backend.models import Maintenance, User
from simulator.simulator import replay
from simulator.scenarios import payload
from conftest import login


@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("NORMAL_HIVE", "NORMAL"),
        ("TEMPERATURE_STRESS", "COLONY_STRESS_INDICATOR"),
        ("WEIGHT_DROP_EVENT", "POSSIBLE_SWARMING_PATTERN"),
        ("HARVEST_READY", "HARVEST_READINESS"),
        ("SENSOR_FAILURE", "SENSOR_DATA_ANOMALY"),
    ],
)
def test_scenarios(env, scenario, expected):
    app, c, creds = env
    replay(c, creds, scenario)
    h = login(c, "beekeeper.1")
    data = c.get(
        "/api/hives/" + creds["devices"][0]["hive_id"] + "/status", headers=h
    ).json()
    if expected == "NORMAL":
        assert data["interpreted"]["status"] == "NORMAL"
    else:
        alerts = data["interpreted"]["alerts"]
        assert expected in [a["type"] for a in alerts], data
        for a in alerts:
            assert {
                "measurements",
                "derived_measurements",
                "configured_threshold",
                "rule_version",
                "time_window",
            } <= a["evidence"].keys()
    if scenario == "SENSOR_FAILURE":
        assert "POSSIBLE_SWARMING_PATTERN" not in [
            a["type"] for a in data["interpreted"]["alerts"]
        ]


def test_insufficient_and_event_context(env):
    app, c, creds = env
    d = creds["devices"][0]
    t = now()
    c.post(
        "/api/telemetry",
        json=payload(d, (t - timedelta(minutes=70), 38, 35, 58)),
        headers={"X-Device-Key": d["key"]},
    )
    h = login(c, "beekeeper.1")
    data = c.get("/api/hives/" + d["hive_id"] + "/status", headers=h).json()
    assert data["interpreted"]["coverage"] == "INSUFFICIENT_DATA"
    assert data["interpreted"]["status"] != "NORMAL"
    c.post(
        "/api/hives/" + d["hive_id"] + "/maintenance",
        json={
            "occurred_at": (t - timedelta(minutes=30)).isoformat(),
            "description": "Synthetic inspection and box removal",
        },
        headers=h,
    )
    replay(c, creds, "WEIGHT_DROP_EVENT", end=t)
    data = c.get("/api/hives/" + d["hive_id"] + "/status", headers=h).json()
    assert "POSSIBLE_SWARMING_PATTERN" not in [
        a["type"] for a in data["interpreted"]["alerts"]
    ]
    assert "weight_loss_context" in data["derived"]
