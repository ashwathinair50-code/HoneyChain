# Validation record
Validated locally on 2026-09-05 with Python 3.12.

- Final pytest suite: **31 passed**. Two dependency deprecation warnings from
  Starlette/httpx and AnyIO; no failed tests.
- Started the actual Uvicorn server and ran the separate simulator CLI over HTTP:
  NORMAL_HIVE, WEIGHT_DROP_EVENT and REGIONAL_CLUSTER.
- Live HTTP checks confirmed a beekeeper weight-pattern alert, scoped regional
  anomaly, verified released passport and 404 responses for pending/rejected data.
- Browser-tested public lookup and the full role-separated workflow:
  beekeeper extraction → officer lab assignment → lab evidence submission →
  lab finalization → officer approval → public VERIFIED passport and real QR.
- Browser-tested an extraction while the backend was stopped. IndexedDB retained
  one operation; after restarting and syncing, one batch appeared and the queue
  returned to zero.
- Inspected the desktop dashboard layout. Browser developer error logs were empty
  during the successful full workflow. The deliberate outage produced expected
  network failures.
- Final inline JavaScript syntax check passed. No Math.random telemetry or obsolete
  signature-failure wording appears in the frontend.
- Controlled tampering tests modified an approved snapshot, finalized report and
  predecessor block in isolated databases. Integrity verification failed as expected.
- Other tests cover ownership/jurisdiction, role separation, device revocation,
  impossible and nonnumeric readings, idempotency, finalized versions, failed lab
  outcomes, minimum regional coverage and concurrent duplicate approval.

Not validated: real ESP32 measurements, physical camera scanning on hardware,
biological performance, real lab integration, PostgreSQL, cloud deployment,
multi-worker operation, or offline cold start. These are not claimed as completed.

Latest demo validation: 29 tests passed. Browser sign-in confirmed all three named demo accounts reach their correct dashboards. Direct root shows no batch details; root with batch query loads the API-backed passport. The generated QR was independently decoded with ZXing and its URL/API/ledger flow passed. Physical phone scanning and public cloud hosting remain untested.

Deployment preparation checks: production origin/CORS guards passed; Vercel build injected an HTTPS API origin with no localhost in the output; isolated cloud initialization and second startup preserved and verified the released demo. Docker image execution and actual hosted services have not been tested.
