"""Send deterministic synthetic telemetry through the real authenticated API."""

import argparse, json, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import httpx
from simulator.scenarios import SCENARIOS, sequence, payload


def replay(client, credentials, scenario, end=None, delay=0, device_index=0):
    end = end or datetime.now(timezone.utc)
    devices = (
        credentials["devices"][:5]
        if scenario == "REGIONAL_CLUSTER"
        else [credentials["devices"][device_index]]
    )
    count = 0
    for i, d in enumerate(devices):
        mode = (
            "TEMPERATURE_STRESS"
            if scenario == "REGIONAL_CLUSTER" and i in (1, 2)
            else ("NORMAL_HIVE" if scenario == "REGIONAL_CLUSTER" else scenario)
        )
        for point in sequence(mode, end):
            response = client.post(
                "/api/telemetry",
                json=payload(d, point),
                headers={"X-Device-Key": d["key"]},
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"Telemetry rejected: {response.status_code} {response.text}"
                )
            count += 1
            if delay:
                time.sleep(delay)
    if scenario == "WEIGHT_DROP_EVENT":
        # Live confirmation samples follow replay history, so a prior scenario's
        # backfilled readings cannot interleave with the new event's final samples.
        for weight in (38.2, 35.0, 35.0):
            time.sleep(0.05)
            point = (datetime.now(timezone.utc), weight, 35.0, 58.2)
            response = client.post(
                "/api/telemetry",
                json=payload(devices[0], point),
                headers={"X-Device-Key": devices[0]["key"]},
            )
            if response.status_code != 200:
                raise RuntimeError(response.text)
            count += 1
    return count


def main():
    p = argparse.ArgumentParser(
        description="Synthetic / Simulated Hive Telemetry. No biological validation."
    )
    p.add_argument("--scenario", choices=SCENARIOS, default="NORMAL_HIVE")
    p.add_argument("--url", default="http://127.0.0.1:8000")
    p.add_argument("--credentials", type=Path, default=Path("demo-credentials.json"))
    p.add_argument("--device-index", type=int, default=0)
    p.add_argument("--delay", type=float, default=0)
    p.add_argument("--repeat", type=int, default=1)
    args = p.parse_args()
    creds = json.loads(args.credentials.read_text())
    with httpx.Client(base_url=args.url, timeout=30) as c:
        for _ in range(args.repeat):
            count = replay(
                c,
                creds,
                args.scenario,
                delay=args.delay,
                device_index=args.device_index,
            )
            print(f"{args.scenario}: {count} authenticated synthetic readings accepted")
            if args.repeat > 1:
                time.sleep(10)


if __name__ == "__main__":
    main()
