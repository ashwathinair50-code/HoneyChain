"""Reproducible engineering fixtures, not biological measurements."""

from datetime import timedelta

SCENARIOS = (
    "NORMAL_HIVE",
    "TEMPERATURE_STRESS",
    "WEIGHT_DROP_EVENT",
    "HARVEST_READY",
    "SENSOR_FAILURE",
    "REGIONAL_CLUSTER",
)


def sequence(scenario, end):
    if scenario not in SCENARIOS:
        raise ValueError("Unknown scenario")
    if scenario == "HARVEST_READY":
        return [
            (
                end - timedelta(hours=60 - i),
                round(32 + i * 0.75, 2) if i < 12 else 41 + (i % 2) * 0.1,
                35.0,
                58.0,
            )
            for i in range(61)
        ]
    weights = [38.2, 38.1, 38.2, 38.1, 38.2, 38.1, 38.2]
    temps = [35.0, 35.1, 35.0, 35.1, 35.0, 35.1, 35.0]
    if scenario in ("TEMPERATURE_STRESS", "REGIONAL_CLUSTER"):
        temps = [35, 39, 39.2, 39.3, 39.4, 39.5, 39.5]
        weights = [38.2, 38.2, 38.1, 38.1, 38, 38, 38]
    if scenario == "WEIGHT_DROP_EVENT":
        weights = [38.2, 38.1, 38.2, 35.1, 35, 35.1, 35]
    if scenario == "SENSOR_FAILURE":
        weights = [38.2, 38.1, 38.2, 3.1, 38, 38.1, 38]
    return [
        (end - timedelta(minutes=(len(weights) - 1 - i) * 10), w, temps[i], 58.2)
        for i, w in enumerate(weights)
    ]


def payload(device, point):
    timestamp, weight, temp, humidity = point
    return {k: device[k] for k in ("device_id", "hive_id", "beekeeper_id")} | {
        "timestamp": timestamp.isoformat(),
        "weight_kg": weight,
        "temperature_c": temp,
        "humidity_percent": humidity,
    }
