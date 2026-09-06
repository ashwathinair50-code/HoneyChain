# Deploy HoneyChain

Local validation is recorded in docs/VALIDATION.md. No public services have been created yet. The values below with YOUR-... are placeholders, not live URLs. Do not print the production QR until they are replaced and deployment smoke checks pass.

## 1. Prepare the repository

Use this HoneyChain folder as the Git repository root. Commit source files, Dockerfile, .dockerignore, frontend/vercel.json and frontend/build.mjs. Do not commit .env, database files, demo-credentials.json or demo-batches.json. The supplied source ZIP excludes these generated files. Connect the repository to your hosting accounts.

## 2. Create the Vercel project

Import the repository into Vercel. Set Root Directory to frontend, Framework Preset to Other, Build Command to node build.mjs, and Output Directory to dist. These build/output settings are also in frontend/vercel.json. Record the project's assigned production domain as FRONTEND_URL. Use the stable project domain, not a per-commit preview URL.

The first build requires API_BASE_URL; finish the backend setup below, then set that variable in Vercel's Production environment and deploy/redeploy. Do not put JWT_SECRET or database credentials in Vercel frontend variables.

## 3. Deploy FastAPI on Render

Create a Web Service from the same repository. Select Docker, repository root as the service root, and ./Dockerfile as Dockerfile path. Use a service plan supporting a persistent disk. Add a disk mounted at /app/storage (1 GB is adequate for the synthetic demo). This requires a paid persistent-disk-capable service; an ephemeral filesystem is not suitable for the database.

Use the Dockerfile's default start command: python -m backend.cloud_start. Set health check path to /api/health. Keep one instance and one Uvicorn worker: the scheduler and SQLite synchronization are designed for this mode. Multiple phones/laptops can connect to that instance; this is not a load-tested high-availability deployment. Disk-attached deploys may briefly interrupt service.

Set these backend environment variables before deploying:

| Variable | Value |
| --- | --- |
| APP_ENV | production |
| DEMO_MODE | true for the synthetic SIH deployment |
| FRONTEND_URL | https://YOUR-PROJECT.vercel.app |
| CORS_ORIGINS | Exact same frontend origin, with no wildcard |
| DATABASE_URL | sqlite:////app/storage/honeychain.db |
| JWT_SECRET | Newly generated random secret, at least 32 characters |
| TOKEN_MINUTES | 60 (optional) |

Generate JWT_SECRET locally with: python -c "import secrets; print(secrets.token_urlsafe(48))". Paste it only into the backend secret setting. Render supplies PORT; the startup command binds 0.0.0.0 at that port.

The first startup seeds synthetic users, apiaries, the finalized demo lab result, approval, released snapshot and linked ledger for HC-MH-NAS-2026-00184. Later startups validate the existing released record and preserve the database. A failed integrity check stops startup instead of overwriting evidence. Cloud seed does not write a plaintext credential file; demo login password hashes are stored in the database. Keep DEMO_MODE=true for the requested SIH accounts. Turning it off disables demo alias login and username advertising.

Record the assigned Render HTTPS URL as API_BASE_URL. Confirm its /api/health endpoint responds successfully.

## 4. Finish Vercel deployment

In Vercel, set Production API_BASE_URL to the Render HTTPS origin, for example https://YOUR-BACKEND.onrender.com. It must contain no path, credentials, query or fragment. Redeploy the frontend. The build injects this origin into the API meta tag; all browser API calls share that one setting.

Open the final Vercel root domain. If the actual domain differs from the value configured earlier, update backend FRONTEND_URL and CORS_ORIGINS to that exact domain and redeploy the backend. No application source URL edits are required.

## 5. Required final URLs and checks

Record the actual values after the services are created:

- Frontend: https://YOUR-PROJECT.vercel.app
- Backend: https://YOUR-BACKEND.onrender.com
- Passport / encoded QR: https://YOUR-PROJECT.vercel.app/?batch=HC-MH-NAS-2026-00184
- Public JSON: https://YOUR-BACKEND.onrender.com/api/public/batches/HC-MH-NAS-2026-00184
- Real QR PNG: https://YOUR-BACKEND.onrender.com/api/public/batches/HC-MH-NAS-2026-00184/qr

Download the QR PNG from the deployed backend only after FRONTEND_URL is final. The existing supplied PNG is a local LAN test artifact and must not be used as the production QR. QR generation uses FRONTEND_URL dynamically; it contains only the public website URL and batch ID.

Check in two separate devices/browsers: root has no product details; manual verification and the query URL both display the synthetic passport; all three logins reach their role dashboard; a forbidden role API returns an authorization error; pending/rejected records remain private. Scan the deployed QR on a phone and confirm the address is the Vercel domain. In browser Network tools, API calls must go to the HTTPS backend, with no localhost requests. Restart the backend and recheck the same batch to confirm disk persistence. Camera scanning requires HTTPS and permission; manual entry remains available.

## Configuration files

- .env.local.example: copy to .env for local use, supplying a random secret. FRONTEND_URL and API_BASE_URL are http://127.0.0.1:8000. The unbuilt local frontend uses same-origin requests.
- .env.production.example: reference for host environment settings; never copy local secrets or URLs into production.
- backend/config.py: FRONTEND_URL drives generated QR links. PUBLIC_URL remains a compatibility fallback for older local setup.
- frontend/build.mjs: consumes API_BASE_URL at Vercel build time. Changing it requires a frontend rebuild.
- Dockerfile / backend/cloud_start.py: container build, safe initial demo seed and single-worker start.
- frontend/vercel.json: Vercel build/output configuration.

Official setup references: [Vercel project settings](https://vercel.com/docs/project-configuration/project-settings), [Vercel environment variables](https://vercel.com/docs/environment-variables), [Render Docker](https://render.com/docs/docker), [Render persistent disks](https://render.com/docs/disks).
