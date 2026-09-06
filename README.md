# HoneyChain / BeeTrust AI
Team Insite Ã‚Â· SIH26_241 Ã‚Â· Somaiya Vidyavihar University Ã‚Â· PS 26021

A working local SIH prototype connecting hive monitoring, extraction, registered
laboratory evidence, institutional review and public Digital Honey Passports.

## Run locally
Requires Python 3.12 or newer. Run from this project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe -m backend.demo_setup
.\.venv\Scripts\python.exe -m uvicorn backend.app:create_app --factory --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. The default page is public verification. API documentation
is at /docs; the machine-readable contract is at /openapi.json and docs/openapi.json.

Setup generates a random JWT secret in .env and a random demonstration password in
demo-credentials.json. It does not replace an existing database. The generated
demo-batches.json lists the actual released, rejected and pending batch identifiers.
Do not commit .env, databases or demo-credentials.json. Source archives exclude them.
No secrets are embedded in frontend JavaScript.

In the current Codex workspace, run.ps1 also recognizes the already-installed
workspace Python environment. On another computer, create .venv as above.

## SIH Demo Credentials

These are **SIH DEMO credentials only**, not official KVIC, NBHM or laboratory
credentials. The login screen lists usernames only when DEMO_MODE=true. Passwords
are never included in frontend JavaScript or public API responses.

| Role | Username | Password |
|---|---|---|
| KVIC ADMIN | KVIC-MH-NAS-001 | KvicDemo@2026 |
| BEEKEEPER | NHM-MH-88492 | BeeDemo@2026 |
| LAB OPERATOR | LAB-MH-0042 | LabDemo@2026 |

The backslash before @ in the request is Markdown escaping; type the passwords
as shown above, with no backslash. Only Argon2 hashes are stored in the database.
These demo login identities map to the existing seeded principals, preserving
their ownership, jurisdiction and already-approved ledger evidence.
DEMO_MODE=false hides the Demo Accounts section and disables these three demo
logins. It does not erase local documentation or existing synthetic released data.
Do not provision demo data in a production database.

Fresh demo setup enables DEMO_MODE and installs the three logins. To add them to an
existing initialized database: set DEMO_MODE=true in .env, then run
`python -m backend.demo_accounts`.

### Phone QR demonstration
The QR encodes PUBLIC_URL + /?batch=HC-MH-NAS-2026-00184.
For this laptop's current Wi-Fi demo, PUBLIC_URL=http://192.168.1.21:8000.
Run the server with --host 0.0.0.0 and connect the phone to the same Wi-Fi.
The large 320px QR appears in the verified passport. The direct homepage shows no product details. Manual
Batch ID verification remains available if in-browser camera access is unavailable.
For deployment, set PUBLIC_URL to the full public HTTPS frontend URL. Static
hosting serves the same index.html at /. The batch query parameter triggers the shared public API lookup.
No private database fields are encoded into the QR.
The app has been tested through the laptop's LAN URL; phone reachability can still
depend on the Wi-Fi's client isolation and Windows firewall configuration.

## Additional generated demonstration accounts
All use the locally generated password from demo-credentials.json.

| Username | Role | Scope |
|---|---|---|
| beekeeper.1 through beekeeper.5 | BEEKEEPER | One synthetic Nashik apiary each |
| beekeeper.6 | BEEKEEPER | One synthetic Pune apiary |
| officer.nas | KVIC_ADMIN | Nashik only |
| officer.pun | KVIC_ADMIN | Pune only |
| lab.1 | LAB_OPERATOR | Registered synthetic lab LAB-MH-0042 |
| lab.2 | LAB_OPERATOR | Second lab, LAB-MH-0043 |

NHM-, KVIC- and LAB- identifiers are synthetic prototype identifiers, not official
government credentials. There is no public account registration or role switcher.

## Architecture and database
Single index.html Ã¢â€ â€™ Fetch API Ã¢â€ â€™ FastAPI Ã¢â€ â€™ SQLAlchemy Ã¢â€ â€™ SQLite.
The separate Python simulator and future ESP32 use the same authenticated API.
The browser never calls a simulator or sensor directly.

The database contains users, jurisdiction profiles, beekeepers, labs/operators,
apiaries, hives, devices, telemetry, alerts, regional alerts, maintenance events,
extractions/source-hive links, batches, lab assignments, versioned lab results,
reviews, lifecycle events, release snapshots, linked ledger blocks, the ledger
head, idempotent synchronization records and audit logs. Foreign keys, role/state
checks, numeric checks and uniqueness constraints enforce core relationships.
One officer has one district assignment in this SIH implementation. One hive has
one active device in this initial model.

Use SQLite on a persistent local disk with a single application process.
A local request lock and a 30-second monitoring job avoid competing alert writes.
Database version checks and unique constraints separately protect batch decisions.
This is deliberately a small prototype, not a multi-worker production service.

## Measurement, derivation and interpretation
- Measured: weight, temperature, humidity, measurement time and receipt time.
- Derived: weight change, moving mean, temperature/humidity change, history
  coverage, stability and device contact age.
- Interpreted: explainable rules and inspection recommendations.

All simulator devices are registered as SIMULATOR. Their cards say
**Synthetic / Simulated Hive Telemetry**. PHYSICAL_DEVICE is a separate registry
value, never a payload field chosen by the sender.

Every alert contains the readings, derived evidence, threshold, rule version,
window, severity and recommendation. Missing history returns INSUFFICIENT_DATA.
No disease diagnosis, validated ML model, accuracy percentage or yield promise is
implemented. Sensor values do not establish honey purity.

Prototype settings live in backend/config.py and can be overridden through .env.
Normal/stress limits, weight drop, sensor-jump limit, stability duration, coverage
gap, harvest gain and target, regional counts/window and device timeout are
configuration values, not official KVIC or biological rules.

Rapid loss needs subsequent confirmation; extreme jumps/rebounds are sensor
anomalies. Recorded extraction or maintenance near a weight change suppresses a
blind swarming interpretation. Harvest readiness needs baseline-relative gain,
earlier growth, target weight and adequately sampled 48-hour stability.

Old telemetry is accepted within the retention window and never replaces the
newest measurement. Rules evaluate the current event-time history after ingestion.
This initial version does not rebuild every past alert revision after arbitrary
out-of-order uploads; its deterministic historical fixtures replay chronologically.

## Simulator
Run from the project root in a second terminal:

```powershell
python -m simulator.simulator --scenario NORMAL_HIVE --device-index 0
python -m simulator.simulator --scenario WEIGHT_DROP_EVENT --device-index 0
python -m simulator.simulator --scenario TEMPERATURE_STRESS --device-index 1
python -m simulator.simulator --scenario HARVEST_READY --device-index 3
python -m simulator.simulator --scenario SENSOR_FAILURE --device-index 4
python -m simulator.simulator --scenario REGIONAL_CLUSTER
```

Use the activated .venv Python, or replace python with .venv/Scripts/python.exe.
--url selects the API host; --credentials selects the generated local device file.
--delay controls wall time between uploads; --repeat repeats a scenario with a
10-second pause. Values are explicit reproducible engineering sequences; timestamps
are anchored to the run time. Weight-drop replay adds real-time confirmation
samples spaced 50 ms apart to prevent Windows clock collisions. These are software
test timings, not biological sampling recommendations.

Historical replay compresses up to 60 hours into a short test run. Do not mistake
this for 60 hours of actual monitoring. Use the designated device indices above:
contradictory backfilled scenarios on one hive can legitimately interrupt a
sustained rule. REGIONAL_CLUSTER uses apiaries 2 and 3 for stress and samples five
apiaries. Rerun a scenario to refresh it; a stopped simulator correctly becomes
offline after the configured timeout.

Expected scenarios: NORMAL, colony stress, possible swarming-associated weight
pattern, harvest readiness, sensor anomaly, and regional anomaly respectively.
Impossible readings such as 150 Ã‚Â°C and 500% humidity are rejected, not stored.

## Regional aggregation
Affected percentage = distinct affected sufficiently reporting active apiaries /
distinct sufficiently reporting active apiaries. At least three recent readings
with bounded gaps and a recent final measurement qualify a reporting hive.
Multiple hives in an apiary cannot inflate the denominator or numerator.
The default window is 48 hours and the trigger is strictly more than 15%, with
at least four monitored and two affected apiaries. Thus 1 / 3 cannot trigger it.
The officer dashboard exposes counts, coverage, settings and recommendations.
A regional anomaly is not a confirmed disease outbreak.

## Extraction and laboratory workflow
1. Beekeeper records an extraction from owned source hives. The server creates
   PENDING_LAB and a unique batch ID. UI entry uses one hive; API supports multiple
   source hives within the same owned apiary.
2. An in-scope officer assigns an active registered lab.
3. The assigned LAB_OPERATOR submits evidence with registered lab/operator
   attribution, report reference, tested time, parameters/units/method, declared
   PASS/FAIL/INCONCLUSIVE outcome and required evidence reference.
4. Optional UTF-8 text file contents are stored and hashed by the backend.
   The UI accepts .txt reports up to 100 KB; PDF/binary report storage is future work.
5. Lab finalization freezes that version and its hash. Corrections create a new
   version referencing the preceding result. Both versions remain visible.
6. Only a finalized PASS outcome is accepted by the current prototype release
   policy. It moves to PENDING_KVIC_REVIEW. FAIL/INCONCLUSIVE remains PENDING_LAB
   for correction/retesting or institutional rejection.
7. An officer reviews the exact latest finalized result, then approves or rejects.
   Rejection requires a reason. Lab accounts cannot approve; officers cannot
   fabricate lab results. Closed batches cannot receive ordinary corrections.

Use docs/SYNTHETIC DEMO LAB REPORT.txt as a clearly marked sample.
It is not a real FSSAI/KVIC certificate.

Authentication proves **which registered laboratory account submitted a result**.
Hashing detects later changes to the protected stored result/report.
Neither proves that a dishonest laboratory performed a physical test correctly.
Future hardening includes accredited lab integration, direct laboratory APIs,
digitally signed reports, public-key verification and certificate validation.

## Release, ledger and consumer privacy
Approval, review, release snapshot, ledger block and final lifecycle state commit
in one transaction. A failed operation leaves no partially released batch.
Optimistic batch version checks and unique release/block constraints reject
duplicate approval.

The **Cryptographically linked append-only batch ledger** uses canonical JSON,
UTF-8, sorted keys, UTC timestamps and decimal quantity strings. Blocks link to the
previous SHA-256 hash and protect producer/origin/extraction/quantity, finalized
lab evidence, officer approval and the public snapshot. Public reads verify the
chain from genesis through the requested block, snapshot and report evidence.
Pending/rejected/unknown records all return NOT FOUND / NOT PUBLICLY RELEASED.
Consumers never receive raw database serialization, passwords, private telemetry,
device keys, private officer details or laboratory operator identities.

On mismatch the UI says:
**RECORD INTEGRITY VERIFICATION FAILED**
Protected batch data does not match the approved ledger record.

SHA-256 is a hash, not a digital signature. No trust or purity score is calculated.
The public evidence checklist covers producer registration, extraction, finalized
lab result, institutional approval and ledger integrity. VERIFIED describes the
approved digital record. Pending and rejected states are available only to
authorized internal users.

Normal API roles cannot edit or delete released snapshots, finalized results,
ledger records or audit history. The SQLite file itself is not absolutely immutable.
An attacker with full database control could rewrite the chain and recompute every
hash. Future strengthening requires digital signatures, external anchoring,
independent checkpoints or a permissioned distributed ledger such as Hyperledger
Fabric. This is not a decentralized blockchain network.

## QR and offline behavior
Real QR PNGs contain the public verification URL, not the database record. Camera
decoding uses the browser BarcodeDetector API where supported, with manual Batch
ID and phone-camera fallback. Physical-camera permission and hardware behavior
depend on the browser/device.

A valid batch QR can be copied onto another bottle. Future anti-cloning approaches
include per-bottle serials, tamper-evident packaging, duplicate-scan analytics and
secure NFC tags. Batch traceability cannot eliminate physical counterfeiting.

IndexedDB persists each extraction before the network request, keyed by a UUID and
user. Backend retry handling compares a canonical payload hash and returns the
original batch for the same operation. Changed payload under the same UUID fails.
The queue survives reconnects and login expiry; another user's queue is never
submitted. Conflicted records remain visible for review. Do not clear browser site
data if you need unsynced drafts.

Offline extraction is supported after the page has loaded. Offline cold start is
not implemented: one HTML file and CDN assets do not supply a service-worker app
shell. The UI includes local CSS so basic layout does not depend on Tailwind loading.
The optional TOKEN_SYNC:NHM-MH-88492_W38.20_T35.10_H58.20 notation is only a future
low-bandwidth representation, not an authenticated ingestion path.

## Security and audit
Argon2id password hashes, expiring JWTs, database-backed active/token-version checks,
role dependencies, ownership/jurisdiction filters, per-device credential hashes,
Pydantic validation, CORS allowlist and no-store responses are implemented.
API roles cannot edit audit history. Audits cover extraction, lab assignment,
result/version creation, finalization, approval/rejection, release, ledger append
and public integrity failure. Login throttling is per-process and IP based.

Prototype limitations include in-memory access tokens (reload requires login),
no refresh-token management UI, no provisioning UI, no distributed rate limiter,
a single backend worker, unbounded small-demo collection listings, no post-release
recall/correction workflow, and UTF-8 text evidence only. Use TLS, stronger
provisioning, monitoring, backups and a reviewed security model before production.

## Tests and controlled tampering
```powershell
python -m pytest -q
python -m pytest tests/test_release.py tests/test_end_to_end.py -v
```

Tests use disposable databases, never your demo database. They cover device
authentication, impossible values, duplicate telemetry, ownership/jurisdiction
denials, lab separation, evidence/version freeze, regional coverage, release
privacy, concurrent duplicate approval, snapshot/report/predecessor tampering,
extraction-aware rules and synchronization idempotency.
The tampering tests intentionally modify protected test rows and verify the
required failure response. There is no remotely callable tampering endpoint.

## SIH demonstration
1. Run setup and server; open the public page. Use demo-batches.json to verify
   the released sample and inspect its evidence/QR.
2. Sign in as beekeeper.1. Run NORMAL_HIVE then WEIGHT_DROP_EVENT from a second
   terminal. Refresh or wait for the 10-second dashboard poll.
3. Run REGIONAL_CLUSTER. Sign in as officer.nas to see the reporting denominator
   and regional alert.
4. Sign in as beekeeper.1, select Batch traceability, and save a new extraction.
5. Sign in as officer.nas, open that batch and assign LAB-MH-0042.
6. Sign in as lab.1, open the assigned batch, enter synthetic report evidence and
   a test timestamp after extraction, submit, then finalize.
7. Sign in as officer.nas, review the evidence, approve and release.
8. Open the public passport; see VERIFIED and the real QR code.
9. Run the isolated tampering tests. Explain the digital-record and physical
   authenticity limitations.
10. Test retries by pausing the backend after loading the beekeeper form, saving
    a draft, restarting the backend and clicking Sync pending records.

## Deployment and future work
For Vercel, deploy only frontend/ as a static project. Set the api-base meta value
in index.html to the backend HTTPS origin. Configure CORS_ORIGINS on FastAPI for
the exact frontend origin and PUBLIC_URL for the public frontend URL.
Deploy FastAPI separately with persistent SQLite storage and one worker for SIH.
Static Vercel does not execute the simulator. No cloud deployment is performed by
the local setup.

SQLAlchemy models use portable relational types; PostgreSQL remains a planned
migration, not a tested deployment. Add a PostgreSQL driver, schema migrations,
connection configuration, multi-worker job coordination and concurrency tests
before switching. create_all initializes missing tables; it does not upgrade
existing schemas.

ESP32 replacement is documented in docs/esp32-integration.md. Future ML requires
real labeled telemetry, beekeeper inspections, confirmed pest/disease observations,
weather/floral/seasonal context and actual harvest outcomes, then validation on
unseen data before reporting accuracy. Present functionality is rule-based
decision support and recorded extraction totals, not validated yield forecasting.

## Named QR demonstration
Setup also ensures the released synthetic batch HC-MH-NAS-2026-00184 exists.
Open http://127.0.0.1:8000/?batch=HC-MH-NAS-2026-00184 or use its QR endpoint:
/api/public/batches/HC-MH-NAS-2026-00184/qr.
Its approved origin is Nashik, Maharashtra. It contains finalized synthetic lab
evidence, institutional approval and a verified ledger record. On an existing
installation, run `python -m backend.qr_demo` once. Reruns do not duplicate or
rewrite released evidence. The fixed ID is available only to the local seed
helper, not through the public extraction API.

A phone cannot reach a laptop through a 127.0.0.1 QR URL. For phone demonstrations,
set PUBLIC_URL to the reachable HTTPS frontend URL (or an explicitly configured
LAN demo URL), restart the backend, then download the QR again.


## Exactly two entry flows, one website
QR-first: PUBLIC_URL/?batch=<BATCH_ID> opens the same index.html and immediately
calls GET /api/public/batches/<BATCH_ID>. Only the backend result can show VERIFIED.
Direct: PUBLIC_URL/ shows only verification controls and login options. No batch
details or preselected demo batch are displayed. Enter a Batch ID or scan a QR to
call that same API. A large demo QR is available after opening the named passport.

### Vercel configuration
Set the Vercel project root to frontend/. Its build command is node build.mjs and
output is dist/. Set API_BASE_URL to the public HTTPS FastAPI origin in Vercel.
On FastAPI, set PUBLIC_URL to the actual Vercel HTTPS origin and CORS_ORIGINS to
that exact origin. Redeploy the frontend and restart the backend after changes.
PUBLIC_URL is the frontend origin, never the API origin. All phones and laptops
share the same backend database; browser-specific IndexedDB is only for unsynced
beekeeper extraction drafts. Run one persistent backend instance for this SIH
SQLite prototype; requests from multiple clients are supported and serialized.
A deployed public frontend requires a publicly reachable backend, not localhost
or a private Wi-Fi IP. No Vercel deployment is claimed until those URLs exist.

For phones on the same Wi-Fi, start with: .\run.ps1 -Lan. Set PUBLIC_URL to the laptop's current LAN address before generating a QR. Public deployment still requires an HTTPS backend and frontend; a v0 account link is not a deployed site URL.

Public deployment: follow [DEPLOYMENT.md](DEPLOYMENT.md) for the exact Vercel and Render setup, environment values, persistent disk and final QR checks.
