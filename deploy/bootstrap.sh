#!/usr/bin/env bash
# Podium - VPS production bootstrap.
# Run as root on the VPS. Adjust GIT_REPO, ADMIN_PASSWORD, DB_PASSWORD before running.
set -euo pipefail

GIT_REPO="${GIT_REPO:-https://github.com/androidnega/ifnotus.git}"
APP_DIR="/srv/apps/podium"
APP_USER="podium"
DOMAIN="manage.podiumclass.online"
ADMIN_USER="admin"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-CHANGE_ME}"
DB_PASSWORD="${DB_PASSWORD:-CHANGE_ME}"

echo "==> Installing system packages (Python 3.13 via deadsnakes, PostgreSQL, Nginx)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y software-properties-common
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update -y
apt-get install -y python3.13 python3.13-venv python3.13-dev postgresql nginx \
  git curl build-essential libpq-dev

# Redis is reused from the running LiveKit Docker container (127.0.0.1:6379).
echo "==> Redis: reusing existing Docker redis on 127.0.0.1:6379 (no native install)"

echo "==> Creating app user"
id -u "$APP_USER" >/dev/null 2>&1 || useradd -r -m -d "$APP_DIR" -s /bin/bash "$APP_USER"

echo "==> Cloning repository"
mkdir -p "$APP_DIR"
git clone "$GIT_REPO" "$APP_DIR" 2>/dev/null || (cd "$APP_DIR" && git pull)

echo "==> Python venv + install"
cd "$APP_DIR/backend"
python3.13 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"

echo "==> PostgreSQL user + database"
runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='podium'" | grep -q 1 || \
  runuser -u postgres -- psql -c "CREATE ROLE podium LOGIN PASSWORD '$DB_PASSWORD'"
runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname='podium'" | grep -q 1 || \
  runuser -u postgres -- createdb -O podium podium

echo "==> Redis (reused from Docker container, already up)"
echo "    Redis container: livekitpodiumclassonline-redis-1 on 127.0.0.1:6379"

echo "==> Backend .env"
if [ ! -f backend/.env ]; then
  cp "$APP_DIR/deploy/.env.production.example" "$APP_DIR/backend/.env"
  SECRET=$(openssl rand -hex 32)
  sed -i "s|SECRET_KEY=.*|SECRET_KEY=$SECRET|" "$APP_DIR/backend/.env"
  sed -i "s|DATABASE_URL=.*|DATABASE_URL=postgresql+asyncpg://podium:$DB_PASSWORD@127.0.0.1:5432/podium|" "$APP_DIR/backend/.env"
  sed -i "s|CORS_ORIGINS=.*|CORS_ORIGINS=https://$DOMAIN|" "$APP_DIR/backend/.env"
fi

echo "==> Migrations + seed admin"
cd "$APP_DIR/backend"
set -a; . ./.env; set +a
.venv/bin/alembic upgrade head
.venv/bin/podium-seed-admin "$ADMIN_USER" "$ADMIN_PASSWORD" || true

echo "==> systemd units"
cp "$APP_DIR/deploy/podium-api.service" /etc/systemd/system/
cp "$APP_DIR/deploy/podium-worker.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now podium-api
systemctl enable --now podium-worker

echo "==> Frontend dist (built locally; upload from deploy/ if missing)"
mkdir -p "$APP_DIR/frontend"

echo "==> Nginx vhost"
cp "$APP_DIR/deploy/nginx-manage.podiumclass.online.conf" /etc/nginx/sites-available/"$DOMAIN"
ln -sf /etc/nginx/sites-available/"$DOMAIN" /etc/nginx/sites-enabled/"$DOMAIN"

echo "==> Ownership + perms"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chown -R www-data:www-data "$APP_DIR/frontend/dist" 2>/dev/null || true

echo ""
echo "================================================================"
echo " Bootstrap complete. Remaining manual steps:"
echo "   1) DNS: A record manage.podiumclass.online -> <VPS_IP>"
echo "   2) certbot --nginx -d $DOMAIN  (gets HTTPS cert)"
echo "   3) nginx -t && systemctl reload nginx"
echo "   4) Upload frontend build: rsync frontend/dist/ $APP_DIR/frontend/dist/"
echo "   5) Verify: curl https://$DOMAIN/api/v1/health"
echo "   6) Admin login: $ADMIN_USER / your ADMIN_PASSWORD"
echo "   7) Set ADMIN_ALLOWED_IPS in backend/.env and enable lockdown"
echo "================================================================"
