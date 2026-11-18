# Deployment

## Option A: Docker Compose (recommended)

```bash
cp backend/.env.example backend/.env       # fill in secrets, DB_USER/DB_PASSWORD, FRONTEND_URL/BACKEND_URL = https://your-domain
export DB_PASSWORD=... MYSQL_ROOT_PASSWORD=...
docker compose up -d --build
docker compose exec backend python -m scripts.create_superadmin --email ceo@your-domain.com --first-name ... --last-name ...
```

The stack contains MySQL 8, Redis, the API and nginx serving the PWA, with `/api` proxied to the API. On start, the backend applies migrations and downloads the face models. If you already run MySQL, delete the `db` service and set `DB_HOST`.

> These files were written for this project but have not yet been built in this environment. Run `docker compose build` once and check the logs before going live.

## Option B: Windows / Linux server without Docker

1. Follow README steps 2–5. Run `npm run build` and serve `frontend/dist` with nginx or IIS, using `frontend/nginx.conf` as the template. Change the `proxy_pass` target to `http://127.0.0.1:8000`.
2. Run the API as a service:
   - **Linux (systemd):** `ExecStart=/srv/echoutra/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers`, `WorkingDirectory=/srv/echoutra/backend`, `Restart=always`.
   - **Windows:** register the same command with NSSM or Task Scheduler (*At startup*, restart on failure).
3. Run **one** API process with `SCHEDULER_ENABLED=true`. If you scale out to more workers or servers, set `SCHEDULER_ENABLED=false` on the extras and set `REDIS_URL` so rate limits are shared.

## HTTPS

HTTPS is required for camera access, PWA install and secure sessions. Terminate TLS with one of these:

- **Caddy** (automatic Let's Encrypt): `one.echoutra.com { reverse_proxy localhost:80 }`
- **nginx + certbot:** `certbot --nginx -d one.echoutra.com`
- A cloud load balancer (AWS ALB, Cloudflare) in front of port 80.

Then set `ENVIRONMENT=production`, `FRONTEND_URL`/`BACKEND_URL` to the HTTPS origin, and `CORS_ORIGINS` to the same origin. Register the OAuth redirect URIs with the HTTPS host.

## Production checklist

- [ ] Fresh `SECRET_KEY`, `DATA_ENCRYPTION_KEY` and `BIOMETRIC_ENCRYPTION_KEY`, stored in a secrets manager (see SECURITY.md).
- [ ] A dedicated MySQL user with rights only on `echo_attend`, not root.
- [ ] `ENVIRONMENT=production` (enables the HSTS header and the strong-secret check).
- [ ] HTTPS working, and camera check-in tested on a phone.
- [ ] Super Admin created; company profile, working hours, weekly offs and holidays configured.
- [ ] Daily backups scheduled and **a restore tested**.
- [ ] Optional integrations configured (Gemini, Gmail/Outlook, S3).

## Backups

- **In the app:** Settings → Backups → *Create backup* (requires `admin.backup`).
- **Scheduled:** `python -m scripts.backup --keep 14`. Run it daily, for example with Task Scheduler at 02:00 or `0 2 * * * cd /srv/echoutra/backend && .venv/bin/python -m scripts.backup`.
- Copy `backend/backups/` **and** `backend/storage/` (uploaded documents) off the server every day, for example with `aws s3 sync` or to a NAS.
- Keep the encryption keys in a separate, secure location. A database backup without them cannot decrypt bank details or face templates.

## Restore

```bash
mysql -u root -p -e "CREATE DATABASE echo_attend_restore CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
mysql -u root -p echo_attend_restore < backups/echo_attend-YYYYMMDD-HHMMSS.sql
# verify, then point DB_NAME at the restored database (or rename) and restart the API
cd backend && .venv/bin/alembic upgrade head        # brings an older backup up to the current schema
```

Restore `storage/` from the same date so that document records match their files.

## Upgrades

```bash
git pull
cd backend && .venv/bin/pip install -r requirements.txt && .venv/bin/alembic upgrade head
cd ../frontend && npm ci && npm run build
# restart the API service
```

New schema changes are added as Alembic revisions (`alembic revision --autogenerate -m "..."`). Review each generated migration before committing it.
