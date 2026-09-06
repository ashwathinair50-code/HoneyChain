"""Explainable prototype rules. No disease diagnosis or validated biological claims."""

from datetime import timedelta
from statistics import mean
from sqlalchemy import select
from .models import Device, Alert, Extraction, ExtractionHive, Maintenance
from .telemetry_api import readings, reading_view, alert_view


def covered(rows, start, end, max_gap):
    return (
        len(rows) >= 3
        and rows[0].measured_at <= start
        and rows[-1].measured_at >= end
        and all(
            (b.measured_at - a.measured_at).total_seconds() <= max_gap * 60
            for a, b in zip(rows, rows[1:])
        )
    )


def evaluate(db, hive, s, current):
    rows = readings(db, hive.id)
    device = db.scalar(select(Device).where(Device.hive_id == hive.id))
    latest = rows[-1] if rows else None
    offline = (
        not device
        or not device.last_contact
        or current - device.last_contact > timedelta(minutes=s.offline_minutes)
    )
    fresh = latest and current - latest.measured_at <= timedelta(
        minutes=s.max_gap_minutes
    )
    findings = []
    derived = {
        "weight_change_kg": None,
        "moving_average_kg": None,
        "temperature_change_c": None,
        "humidity_change_percent": None,
        "stability_48h": False,
        "seconds_since_contact": round((current - device.last_contact).total_seconds())
        if device and device.last_contact
        else None,
    }

    def add(kind, severity, used, threshold, action, derived_values=None):
        findings.append(
            {
                "type": kind,
                "severity": severity,
                "recommendation": action,
                "evidence": {
                    "measurements": [reading_view(r) for r in used],
                    "derived_measurements": derived_values or {},
                    "configured_threshold": threshold,
                    "rule": kind,
                    "rule_version": s.rule_version,
                    "time_window": {
                        "from": used[0].measured_at.isoformat()
                        if used
                        else current.isoformat(),
                        "to": used[-1].measured_at.isoformat()
                        if used
                        else current.isoformat(),
                    },
                },
            }
        )

    sufficient = False
    if latest:
        recent = [
            r
            for r in rows
            if r.measured_at
            >= latest.measured_at - timedelta(minutes=2 * s.swarm_minutes)
        ]
        sufficient = (
            fresh
            and len(rows) >= 3
            and all(
                (b.measured_at - a.measured_at).total_seconds()
                <= s.max_gap_minutes * 60
                for a, b in zip(rows[-3:], rows[-2:])
            )
        )
        if len(recent) >= 2:
            derived.update(
                weight_change_kg=round(latest.weight_kg - recent[0].weight_kg, 3),
                moving_average_kg=round(mean(r.weight_kg for r in recent), 3),
                temperature_change_c=round(
                    latest.temperature_c - recent[0].temperature_c, 3
                ),
                humidity_change_percent=round(
                    latest.humidity_percent - recent[0].humidity_percent, 3
                ),
            )
        sensor_pairs = [
            (a, b)
            for a, b in zip(recent, recent[1:])
            if abs(b.weight_kg - a.weight_kg) >= s.sensor_jump
            and (b.measured_at - a.measured_at) <= timedelta(minutes=s.swarm_minutes)
        ]
        if fresh and sensor_pairs:
            add(
                "SENSOR_DATA_ANOMALY",
                "WARNING",
                recent,
                {"abrupt_jump_kg": s.sensor_jump},
                "Inspect sensor mounting and calibration before interpreting hive condition.",
            )
        if sufficient and not sensor_pairs:
            if (
                latest.temperature_c > s.normal_temp_max
                or latest.temperature_c < s.normal_temp_min
            ):
                add(
                    "TEMPERATURE_ANOMALY",
                    "WARNING",
                    recent,
                    {"low": s.normal_temp_min, "high": s.normal_temp_max},
                    "Inspect hive ventilation and confirm the sensor reading.",
                )
            if not s.humidity_min <= latest.humidity_percent <= s.humidity_max:
                add(
                    "HUMIDITY_ANOMALY",
                    "WARNING",
                    recent,
                    {"min": s.humidity_min, "max": s.humidity_max},
                    "Check humidity sensor and inspect hive conditions.",
                )
            start = latest.measured_at - timedelta(minutes=s.stress_minutes)
            window = [r for r in rows if r.measured_at >= start - timedelta(minutes=1)]
            if (
                covered(window, start, latest.measured_at, s.max_gap_minutes)
                and all(r.temperature_c > s.temp_warning for r in window)
                and latest.weight_kg <= window[0].weight_kg
            ):
                add(
                    "COLONY_STRESS_INDICATOR",
                    "CRITICAL",
                    window,
                    {
                        "temperature_above": s.temp_warning,
                        "persistence_minutes": s.stress_minutes,
                        "weight_change_max_kg": 0,
                    },
                    "Inspect hive physically for possible colony stress.",
                    {
                        "weight_change_kg": round(
                            latest.weight_kg - window[0].weight_kg, 3
                        )
                    },
                )
            for i in range(1, len(recent) - 1):
                before, drop, confirmation = recent[i - 1 : i + 2]
                loss = before.weight_kg - drop.weight_kg
                if (
                    loss >= s.weight_drop
                    and drop.measured_at - before.measured_at
                    <= timedelta(minutes=s.swarm_minutes)
                    and confirmation.weight_kg <= before.weight_kg - s.weight_drop
                ):
                    ext = db.scalar(
                        select(Extraction)
                        .join(
                            ExtractionHive,
                            ExtractionHive.extraction_id == Extraction.id,
                        )
                        .where(
                            ExtractionHive.hive_id == hive.id,
                            Extraction.extracted_at
                            >= before.measured_at - timedelta(minutes=30),
                            Extraction.extracted_at
                            <= drop.measured_at + timedelta(minutes=30),
                        )
                    )
                    maintenance = db.scalar(
                        select(Maintenance).where(
                            Maintenance.hive_id == hive.id,
                            Maintenance.occurred_at
                            >= before.measured_at - timedelta(minutes=30),
                            Maintenance.occurred_at
                            <= drop.measured_at + timedelta(minutes=30),
                        )
                    )
                    if ext or maintenance:
                        derived["weight_loss_context"] = (
                            "Recorded extraction or maintenance near the weight drop; inspect if unexplained."
                        )
                    else:
                        add(
                            "POSSIBLE_SWARMING_PATTERN",
                            "WARNING",
                            [before, drop, confirmation],
                            {
                                "weight_drop_kg": s.weight_drop,
                                "window_minutes": s.swarm_minutes,
                            },
                            "Rapid weight-loss pattern detected. Possible swarming-associated event. Physical inspection recommended.",
                            {"drop_kg": round(loss, 3)},
                        )
                    break
            start = latest.measured_at - timedelta(hours=s.harvest_hours)
            stable = [r for r in rows if r.measured_at >= start]
            earlier = [r for r in rows if r.measured_at < start]
            stable_ok = (
                covered(stable, start, latest.measured_at, s.max_gap_minutes)
                and max(r.weight_kg for r in stable) - min(r.weight_kg for r in stable)
                <= s.harvest_tolerance
            )
            derived["stability_48h"] = stable_ok
            if (
                stable_ok
                and earlier
                and latest.weight_kg >= hive.harvest_target_kg
                and latest.weight_kg - hive.baseline_kg >= s.harvest_gain
                and stable[0].weight_kg - min(r.weight_kg for r in earlier)
                >= s.harvest_gain
            ):
                add(
                    "HARVEST_READINESS",
                    "INFO",
                    stable,
                    {
                        "hive_baseline_kg": hive.baseline_kg,
                        "hive_target_kg": hive.harvest_target_kg,
                        "gain_kg": s.harvest_gain,
                        "stability_hours": s.harvest_hours,
                        "tolerance_kg": s.harvest_tolerance,
                    },
                    "Hive may be approaching harvest readiness. Manual assessment recommended.",
                    {
                        "stable_range_kg": round(
                            max(r.weight_kg for r in stable)
                            - min(r.weight_kg for r in stable),
                            3,
                        )
                    },
                )
    if offline:
        add(
            "DEVICE_OFFLINE",
            "WARNING",
            [],
            {"contact_timeout_minutes": s.offline_minutes},
            "Check device power and connectivity. Current hive condition is unknown.",
            {"seconds_since_contact": derived["seconds_since_contact"]},
        )
    active = list(
        db.scalars(
            select(Alert).where(Alert.hive_id == hive.id, Alert.resolved_at.is_(None))
        )
    )
    kinds = {f["type"] for f in findings}
    for old in active:
        if old.type not in kinds:
            old.resolved_at = current
    for f in findings:
        old = next((a for a in active if a.type == f["type"]), None)
        observed = current if f["type"] == "DEVICE_OFFLINE" else latest.measured_at
        if old:
            old.evidence = f["evidence"]
            old.last_seen = observed
            old.severity = f["severity"]
        else:
            old = Alert(
                hive_id=hive.id,
                type=f["type"],
                severity=f["severity"],
                evidence=f["evidence"],
                recommendation=f["recommendation"],
                opened_at=observed,
                last_seen=observed,
            )
            db.add(old)
    db.flush()
    active = list(
        db.scalars(
            select(Alert).where(Alert.hive_id == hive.id, Alert.resolved_at.is_(None))
        )
    )
    state = (
        "ATTENTION" if findings else ("NORMAL" if sufficient else "INSUFFICIENT_DATA")
    )
    if not sufficient and not findings:
        state = "INSUFFICIENT_DATA"
    return {
        "hive_id": hive.id,
        "apiary_id": hive.apiary_id,
        "beekeeper_id": hive.apiary.beekeeper_id,
        "source_type": device.source_type if device else None,
        "source_label": "Synthetic / Simulated Hive Telemetry"
        if device and device.source_type == "SIMULATOR"
        else "Physical Device Telemetry",
        "device_status": "OFFLINE" if offline else "ONLINE",
        "measured": reading_view(latest) if latest else None,
        "derived": derived,
        "interpreted": {
            "status": state,
            "coverage": "SUFFICIENT" if sufficient else "INSUFFICIENT_DATA",
            "alerts": [alert_view(a) for a in active],
        },
        "as_of": current.isoformat(),
    }
