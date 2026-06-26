#!/usr/bin/env bash
set -euo pipefail

# MetaTrader VPS Setup Script
# Run as root on a fresh Ubuntu 24.04 VPS:
#   chmod +x setup.sh && sudo ./setup.sh

APP_DIR="/opt/metatrader"
BACKEND_DIR="$APP_DIR/backend"
VENV_DIR="$BACKEND_DIR/venv"
PYTHON_VERSION="3.12"
DOMAIN="${1:-localhost}"

echo "=== MetaTrader VPS Setup ==="

# System packages
echo ">>> Installing system packages..."
apt-get update -qq
apt-get install -y -qq \
  python${PYTHON_VERSION} python${PYTHON_VERSION}-venv python${PYTHON_VERSION}-dev \
  postgresql postgresql-client redis-server \
  nginx certbot python3-certbot-nginx \
  nodejs npm \
  curl git build-essential

# Create app user/directories
echo ">>> Creating app directories..."
mkdir -p "$APP_DIR" "$BACKEND_DIR"
id -u metatrader &>/dev/null || useradd -r -s /bin/false metatrader

# PostgreSQL
echo ">>> Setting up PostgreSQL..."
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='metatrader'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE USER metatrader WITH PASSWORD 'metatrader';"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='metatrader'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE DATABASE metatrader OWNER metatrader;"

# Redis
echo ">>> Configuring Redis..."
sed -i 's/^supervised no/supervised systemd/' /etc/redis/redis.conf
systemctl enable redis-server
systemctl restart redis-server

# Python virtualenv
echo ">>> Setting up Python environment..."
python${PYTHON_VERSION} -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$BACKEND_DIR/requirements.txt" -q

# Environment file
if [ ! -f "$APP_DIR/.env" ]; then
  cp "$BACKEND_DIR/.env.example" "$APP_DIR/.env"
  echo ">>> Created $APP_DIR/.env — EDIT THIS FILE with your API keys!"
fi

# Backend systemd service
echo ">>> Creating systemd services..."
cat > /etc/systemd/system/metatrader-api.service << 'SYSTEMD'
[Unit]
Description=MetaTrader Backend API
After=network.target postgresql.service redis-server.service

[Service]
User=www-data
WorkingDirectory=/opt/metatrader/backend
EnvironmentFile=/opt/metatrader/.env
ExecStart=/opt/metatrader/backend/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SYSTEMD

cat > /etc/systemd/system/metatrader-worker.service << 'SYSTEMD'
[Unit]
Description=MetaTrader Celery Worker
After=network.target redis-server.service

[Service]
User=www-data
WorkingDirectory=/opt/metatrader/backend
EnvironmentFile=/opt/metatrader/.env
ExecStart=/opt/metatrader/backend/venv/bin/celery -A app.worker worker --loglevel=info --concurrency=4
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SYSTEMD

# Nginx
echo ">>> Configuring Nginx..."
cat > /etc/nginx/sites-available/metatrader << NGINX
server {
    listen 80;
    server_name ${DOMAIN};

    # Frontend static files
    root /opt/metatrader/frontend/dist;
    index index.html;

    # API proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # WebSocket proxy
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 86400;
    }

    # SPA fallback
    location / {
        try_files \$uri \$uri/ /index.html;
        expires 1h;
        add_header Cache-Control "public, max-age=3600";
    }

    # Security
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
}
NGINX

ln -sf /etc/nginx/sites-available/metatrader /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

# Enable services
echo ">>> Enabling services..."
systemctl daemon-reload
systemctl enable metatrader-api metatrader-worker

# Set permissions
chown -R www-data:www-data "$APP_DIR"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Edit $APP_DIR/.env with your API keys"
echo "2. Run: alembic upgrade head   (from $BACKEND_DIR with venv activated)"
echo "3. Build frontend: cd frontend && npm run build"
echo "4. Start: systemctl start metatrader-api metatrader-worker"
echo "5. Enable SSL: certbot --nginx -d $DOMAIN"
echo ""
echo "API will be at: http://$DOMAIN (after starting services)"