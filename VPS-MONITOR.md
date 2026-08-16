# Podium — VPS Monitor & Control Panel

How the deployed system works, for anyone (or another agent) picking this up.

## What it is

Podium is a self-hosted VPS monitoring and control panel, deployed in production at:

- **Panel / dashboard**: `https://manage.podiumclass.online`
- **VPS**: Ubuntu 24.04 (Contabo), IP `161.97.176.191`, hostname `vmi3317675`

It replaced the old VPS Dashboard (Next.js on Vercel, `vps-three-mu.vercel.app` — now deleted).

## Where everything lives

### On the VPS

```
/srv/apps/podium/                 # app root (git clone of github.com/Ajigiwe/vps)
├── backend/                      # FastAPI app (Python 3.13, package "app")
│   ├── .venv/                    # virtualenv (python3.13 via deadsnakes PPA)
│   ├── .env                      # ALL config/secrets (see below)
│   ├── alembic/                  # DB migrations
│   └── app/                      # source (routers/, services/, models/, ...)
├── applications/*.yaml           # app registry (podium-api, podium-frontend, podium-lms, auto-registered)
├── frontend/dist/                # built Vue 3 SPA (served by Nginx)
├── deploy/                       # systemd units, nginx vhost template, bootstrap.sh
├── scripts/podium-unlock         # admin-lockdown CLI
└── .podium/                      # runtime state (backups, upload sessions, etc.)
```

Elsewhere on the host:

```
/etc/systemd/system/podium-api.service      # uvicorn on 127.0.0.1:8000
/etc/systemd/system/podium-worker.service   # Redis background task worker
/etc/nginx/sites-enabled/                   # vhosts (see below)
/etc/letsencrypt/live/manage.podiumclass.online/   # TLS cert (renews automatically)
/opt/podium/                              # the Podium LMS app (docker container "podium-app")
```

### Local dev repo (Windows)

`C:\Users\ABCD\Desktop\atio\ifnotUs\ifnotUs` — this repo. Pushed to `github.com/Ajigiwe/vps` (branch `main`). Branding is "Podium" (renamed from IFNOTUS).

## Architecture

- **Backend**: FastAPI + uvicorn (`podium-api.service`), Python 3.13, port 8000 on loopback only.
- **Worker**: `podium-worker.service`, consumes `podium:tasks` from Redis.
- **Database**: native PostgreSQL 16 (package install, NOT docker). DB/user both `podium`; password in `.env`.
- **Redis**: reuses the existing docker container `livekitpodiumclassonline-redis-1` at `127.0.0.1:6379` (no native redis installed).
- **Frontend**: Vue 3 + Vite + TypeScript, built to `frontend/dist`, served by Nginx with SPA fallback.
- **Nginx** routes `https://manage.podiumclass.online/api/` → `127.0.0.1:8000/api/`; everything else → the SPA.

### Nginx vhosts on the VPS

| vhost | purpose |
|-------|---------|
| `manage.podiumclass.online` | this panel |
| `podium` | `podiumclass.online` → `127.0.0.1:3000` (Podium LMS) |
| `livekit` | LiveKit WebRTC stack |
| `prometheus-proxy` | Prometheus metrics |
| `vps-api-proxy` | orphaned legacy `/vps-api` (old dashboard) — candidate for removal |

## Config (`/srv/apps/podium/backend/.env`)

Generated at deploy time. Contains: `SECRET_KEY`, `DATABASE_URL` (`postgresql+asyncpg://podium:<pw>@127.0.0.1:5432/podium`), `REDIS_URL=redis://127.0.0.1:6379/0`, `REDIS_TASK_QUEUE=podium:tasks`, `ENVIRONMENT=production`, `CORS_ORIGINS=https://manage.podiumclass.online`, absolute `APPLICATIONS_DIR`, `DISCOVERY_*`, `NGINX_*`, `LETSENCRYPT_LIVE_DIR`, and `ADMIN_LOCKDOWN_ENABLED` / `ADMIN_ALLOWED_IPS`.

Do not commit it; it is git-ignored.

## How app status/health works

Apps are defined in `applications/*.yaml`. Status is resolved in `backend/app/services/applications/engine.py` (`_resolve_runtime_status`):

1. `app.enabled == false` → `stopped`
2. supervisor/systemd binding → its live state
3. nginx-bound site disabled → `stopped`
4. matching processes (`runtime.process_match`, e.g. `uvicorn.*8000`, `next-server`) → `running`
5. static/PHP sites with nginx + files present → `running`
6. otherwise → `stopped`

Health checks also read git dirty state, nginx site status, and SSL cert expiry (`/etc/letsencrypt/live/<domain>/fullchain.pem`). Note: certs dir must be traversable by the service user (it runs as root now, so fine).

The auto-registrar (`backend/app/services/applications/registrar.py`) promotes discovered apps (in `DISCOVERY_SCAN_PATHS`) into the YAML registry unless excluded via `DISCOVERY_AUTO_REGISTER_EXCLUDE`.

## Controlling services from the panel

- **Applications → open an app → Start / Stop / Restart / Enable / Disable**.
- Enable/Disable also toggles the app's Nginx site (offline page for the domain). To work, the app YAML needs a valid `nginx.site` (e.g. `/etc/nginx/sites-enabled/podium`) or `server_name` matching a real vhost.
- Systemd-backed apps use `systemctl` under the hood; Nginx site changes write a "disabled-stub" and reload Nginx.

## Admin lockdown (new-IP approval)

Logins from unknown IPs get a one-time challenge. CLI on the VPS:

```bash
bash /srv/apps/podium/scripts/podium-unlock pending    # list codes
bash /srv/apps/podium/scripts/podium-unlock add <IP>   # whitelist IP in .env
bash /srv/apps/podium/scripts/podium-unlock off        # disable lockdown
bash /srv/apps/podium/scripts/podium-unlock status     # current state
```

## Admin account

Username/email: `admin@podium.local`. Superadmin, created via `podium-seed-admin`. Password was generated at deploy (reset with `podium-seed-admin admin <newpass>`).

## Deployment / update flow

```bash
cd /srv/apps/podium
git pull
systemctl restart podium-api podium-worker
```

(The service units run as **root** so the panel can mutate Nginx/systemd. No ownership chown needed after pulls.)

- Migrations: `cd /srv/apps/podium/backend && .venv/bin/alembic upgrade head`
- New frontend build must be uploaded: `scp -r frontend/dist root@161.97.176.191:/srv/apps/podium/frontend/`

## Scope notes

- **Core enabled**: dashboard, monitoring, applications, operations, security, servers, settings.
- **Deferred (code kept, hidden from nav)**: hosting panel (domains/databases/ssl/mail/files), customer portal/billing, AI.