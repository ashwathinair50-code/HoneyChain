from datetime import timedelta
from sqlalchemy import select
from .models import Apiary, Hive, Device, Alert, RegionalAlert
from .telemetry_api import readings


def regional(db, jurisdiction, s, current):
    apiaries = list(
        db.scalars(
            select(Apiary).where(
                Apiary.jurisdiction_id == jurisdiction.id, Apiary.active.is_(True)
            )
        )
    )
    monitored = set()
    affected = set()
    start = current - timedelta(hours=s.regional_hours)
    for apiary in apiaries:
        for hive in db.scalars(select(Hive).where(Hive.apiary_id == apiary.id)):
            device = db.scalar(
                select(Device).where(Device.hive_id == hive.id, Device.active.is_(True))
            )
            if not device:
                continue
            rows = [r for r in readings(db, hive.id) if r.measured_at >= start]
            enough = (
                len(rows) >= 3
                and current - rows[-1].measured_at
                <= timedelta(minutes=s.max_gap_minutes)
                and all(
                    b.measured_at - a.measured_at
                    <= timedelta(minutes=s.max_gap_minutes)
                    for a, b in zip(rows[-3:], rows[-2:])
                )
            )
            if not enough:
                continue
            monitored.add(apiary.id)
            alert = db.scalar(
                select(Alert).where(
                    Alert.hive_id == hive.id,
                    Alert.type == "COLONY_STRESS_INDICATOR",
                    Alert.last_seen >= start,
                )
            )
            if alert:
                affected.add(apiary.id)
    percentage = round(100 * len(affected) / len(monitored), 2) if monitored else 0
    active = (
        len(monitored) >= s.regional_min_monitored
        and len(affected) >= s.regional_min_affected
        and percentage > s.regional_percentage
    )
    data = {
        "jurisdiction_id": jurisdiction.id,
        "district": jurisdiction.name,
        "registered_active_apiaries": len(apiaries),
        "sufficiently_reporting_apiaries": len(monitored),
        "affected_apiaries": len(affected),
        "affected_apiary_ids": sorted(affected),
        "affected_percentage": percentage,
        "configured_threshold_percentage": s.regional_percentage,
        "minimum_monitored": s.regional_min_monitored,
        "minimum_affected": s.regional_min_affected,
        "window_hours": s.regional_hours,
        "rule_version": s.rule_version,
        "observed_pattern": "COLONY_STRESS_INDICATOR",
        "status": "REGIONAL_ANOMALY_ALERT"
        if active
        else (
            "INSUFFICIENT_DATA"
            if len(monitored) < s.regional_min_monitored
            else "NO_REGIONAL_ALERT"
        ),
        "recommendation": "Prioritize field assessment of affected apiaries."
        if active
        else "Continue monitoring; this is not a disease-outbreak diagnosis.",
        "as_of": current.isoformat(),
    }
    old = db.scalar(
        select(RegionalAlert).where(
            RegionalAlert.jurisdiction_id == jurisdiction.id,
            RegionalAlert.resolved_at.is_(None),
        )
    )
    if active:
        if old:
            old.evidence = data
            old.last_seen = current
        else:
            db.add(
                RegionalAlert(
                    jurisdiction_id=jurisdiction.id,
                    evidence=data,
                    opened_at=current,
                    last_seen=current,
                )
            )
    elif old:
        old.resolved_at = current
    return data
