#!/usr/bin/env bash
set -euo pipefail

# MetaTrader — Full Lifecycle Management Script
#
# Usage:
#   sudo ./setup.sh install [domain]     Full first-boot setup (fresh Ubuntu 24.04 VPS)
#   sudo ./setup.sh uninstall            Reverse everything this script created
#   sudo ./setup.sh reinstall [domain]   uninstall + install
#   sudo ./setup.sh update               git pull + rebuild + restart
#   sudo ./setup.sh upgrade              update + alembic upgrade head
#   sudo ./setup.sh start                Start all services
#   sudo ./setup.sh stop                 Stop all services
#   sudo ./setup.sh restart              Restart all services
#   sudo ./setup.sh status               Health check and runtime info
#   sudo ./setup.sh logs [api|worker|nginx]  Tail service logs
#   sudo ./setup.sh help                 Show this message

# ── Configuration ───────────────────────────────────────────────────────────
APP_DIR="/opt/metatrader"
BACKEND_DIR="$APP_DIR/backend"
VENV_DIR="$BACKEND_DIR/venv"
MANIFEST_FILE="$APP_DIR/.setup-manifest"
PACKAGES_FILE="$APP_DIR/.setup-packages"
REQUIRED_PYTHON="3.12"
REQUIRED_PYTHON_MIN="$REQUIRED_PYTHON.0"
PYTHON_BIN="python${REQUIRED_PYTHON}"
SERVICES="metatrader-api metatrader-worker"
DB_ROLE="metatrader"
DB_NAME="metatrader"
DB_PASSWORD="metatrader"
SYS_USER="metatrader"
RUN_USER="www-data"

# ── Helpers ─────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}>>>${NC} $*"; }
ok()    { echo -e "${GREEN}✓${NC} $*"; }
warn()  { echo -e "${YELLOW}⚠${NC} $*"; }
err()   { echo -e "${RED}✗${NC} $*" >&2; }
die()   { err "$@"; exit 1; }

must_be_root() { [ "$(id -u)" -eq 0 ] || die "This script must be run as root (use sudo)."; }

require_manifest() { [ -f "$MANIFEST_FILE" ] || die "No manifest found at $MANIFEST_FILE. Run 'install' first."; }

# ── Python version check ────────────────────────────────────────────────────
check_python() {
    info "Checking Python $REQUIRED_PYTHON availability..."

    # Try the default python3 first (fast path if it happens to be the right version)
    local found_bin=""
    local found_ver=""

    # Check explicit python3.12 first (never auto-repoint python3 symlink)
    if command -v "$PYTHON_BIN" &>/dev/null; then
        found_bin="$PYTHON_BIN"
        found_ver=$("$found_bin" --version 2>&1 | awk '{print $2}')
    elif command -v python3 &>/dev/null; then
        local default_ver
        default_ver=$(python3 --version 2>&1 | awk '{print $2}')
        if [[ "$default_ver" == "$REQUIRED_PYTHON."* ]]; then
            found_bin="python3"
            found_ver="$default_ver"
        fi
    fi

    if [ -n "$found_bin" ]; then
        info "Found: $found_bin → $found_ver"
        local major_minor
        major_minor=$(echo "$found_ver" | cut -d. -f1-2)
        if [ "$major_minor" != "$REQUIRED_PYTHON" ]; then
            warn "$found_bin is Python $found_ver, but project targets $REQUIRED_PYTHON.x"
            found_bin=""
        elif [ "$(echo "$found_ver" | cut -d. -f3)" -lt 0 ]; then
            warn "$found_bin is $found_ver (too old — need >= $REQUIRED_PYTHON_MIN)"
            found_bin=""
        fi
    fi

    # Not found or wrong version — install
    if [ -z "$found_bin" ]; then
        info "Python $REQUIRED_PYTHON not available. Installing..."
        if ! apt-cache show "$PYTHON_BIN" &>/dev/null 2>&1; then
            info "Adding deadsnakes PPA for Python $REQUIRED_PYTHON..."
            apt-get install -y -qq software-properties-common
            add-apt-repository -y ppa:deadsnakes/ppa
            apt-get update -qq
        fi
        apt-get install -y -qq "$PYTHON_BIN" "$PYTHON_BIN-venv" "$PYTHON_BIN-dev"
        found_bin="$PYTHON_BIN"
        found_ver=$("$found_bin" --version 2>&1 | awk '{print $2}')
        ok "Installed Python $found_ver"
    fi

    # Validate
    if [ ! -x "$(command -v "$found_bin")" ]; then
        die "Failed to verify Python $REQUIRED_PYTHON binary."
    fi
    PYTHON_BIN="$found_bin"
    ok "Python $REQUIRED_PYTHON confirmed (binary: $PYTHON_BIN, version: $found_ver)"
}

# ── Package tracking ────────────────────────────────────────────────────────
snapshot_packages() {
    dpkg-query -W -f='${Package}\n' 2>/dev/null | sort > /tmp/mt-pkgs-before
}

record_new_packages() {
    dpkg-query -W -f='${Package}\n' 2>/dev/null | sort > /tmp/mt-pkgs-after
    comm -13 /tmp/mt-pkgs-before /tmp/mt-pkgs-after > "$PACKAGES_FILE"
    local count; count=$(wc -l < "$PACKAGES_FILE")
    if [ "$count" -gt 0 ]; then
        ok "Tracked $count new package(s) installed by this script"
    else
        ok "No new system packages were installed (all already present)"
    fi
    rm -f /tmp/mt-pkgs-before /tmp/mt-pkgs-after
}

# ── Manifest ────────────────────────────────────────────────────────────────
read_manifest() {
    [ -f "$MANIFEST_FILE" ] && source "$MANIFEST_FILE"
}

write_manifest() {
    cat > "$MANIFEST_FILE" << MANIFEST
packages_file=$PACKAGES_FILE
db_role=$DB_ROLE
db_name=$DB_NAME
sys_user=$SYS_USER
domain=${DOMAIN:-localhost}
services=$SERVICES
nginx_site=metatrader
python_bin=$PYTHON_BIN
ppa_added=${PPA_ADDED:-false}
default_nginx_removed=${NGINX_DEFAULT_REMOVED:-false}
MANIFEST
}

# ── Domain detection ────────────────────────────────────────────────────────
detect_domain() {
    if [ -z "${DOMAIN:-}" ]; then
        info "No domain provided, detecting public IPv4..."
        DOMAIN=$(curl -s4 --connect-timeout 5 ifconfig.me 2>/dev/null \
            || curl -s4 --connect-timeout 5 icanhazip.com 2>/dev/null \
            || echo "")
        if [ -n "$DOMAIN" ]; then
            ok "Using public IP: $DOMAIN"
        else
            DOMAIN="localhost"
            warn "Could not detect public IP, falling back to localhost"
        fi
    fi
}

# ── System update (first boot) ──────────────────────────────────────────────
first_boot_update() {
    info "Running system update (first-boot VPS)..."
    apt-get update -qq
    apt-get upgrade -y -qq
    ok "System packages updated"
}

# ── System user ─────────────────────────────────────────────────────────────
ensure_system_user() {
    if id -u "$SYS_USER" &>/dev/null; then
        ok "System user '$SYS_USER' already exists"
    else
        useradd -r -s /bin/false "$SYS_USER"
        ok "Created system user '$SYS_USER'"
    fi
}

# ── PostgreSQL ──────────────────────────────────────────────────────────────
setup_postgres() {
    info "Setting up PostgreSQL..."
    systemctl start postgresql 2>/dev/null || true
    systemctl enable postgresql 2>/dev/null || true

    if sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_ROLE'" 2>/dev/null | grep -q 1; then
        ok "PostgreSQL role '$DB_ROLE' already exists"
    else
        sudo -u postgres psql -c "CREATE USER $DB_ROLE WITH PASSWORD '$DB_PASSWORD';"
        ok "Created PostgreSQL role '$DB_ROLE'"
    fi

    if sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" 2>/dev/null | grep -q 1; then
        ok "PostgreSQL database '$DB_NAME' already exists"
    else
        sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_ROLE;"
        ok "Created PostgreSQL database '$DB_NAME'"
    fi
}

teardown_postgres() {
    info "Tearing down PostgreSQL..."
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS $DB_NAME;" 2>/dev/null && ok "Dropped database '$DB_NAME'" || warn "Database '$DB_NAME' not found"
    sudo -u postgres psql -c "DROP ROLE IF EXISTS $DB_ROLE;" 2>/dev/null && ok "Dropped role '$DB_ROLE'" || warn "Role '$DB_ROLE' not found"
}

# ── Redis ───────────────────────────────────────────────────────────────────
setup_redis() {
    info "Configuring Redis..."
    systemctl start redis-server 2>/dev/null || true
    if grep -q '^supervised systemd' /etc/redis/redis.conf 2>/dev/null; then
        ok "Redis already configured (supervised systemd)"
    else
        sed -i 's/^supervised no/supervised systemd/' /etc/redis/redis.conf
        ok "Redis configured (supervised systemd)"
    fi
    systemctl enable redis-server 2>/dev/null || true
    systemctl restart redis-server
}

# ── Python virtualenv ───────────────────────────────────────────────────────
setup_venv() {
    info "Setting up Python virtualenv with $PYTHON_BIN..."
    if [ -f "$VENV_DIR/bin/python" ]; then
        local current; current=$("$VENV_DIR/bin/python" --version 2>&1 | awk '{print $2}')
        info "Virtualenv exists ($current). Re-creating..."
        rm -rf "$VENV_DIR"
    fi
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip -q
    "$VENV_DIR/bin/pip" install -r "$BACKEND_DIR/requirements.txt" -q
    local installed; installed=$("$VENV_DIR/bin/python" --version 2>&1)
    ok "Virtualenv ready: $installed"
}

# ── Environment file ────────────────────────────────────────────────────────
setup_env() {
    if [ -f "$APP_DIR/.env" ]; then
        ok ".env already exists (not overwriting)"
    else
        cp "$BACKEND_DIR/.env.example" "$APP_DIR/.env"
        ok "Created .env — EDIT THIS FILE with your API keys!"
    fi
}

# ── Systemd services ────────────────────────────────────────────────────────
setup_systemd() {
    info "Creating systemd services..."

    cat > /etc/systemd/system/metatrader-api.service << SYSTEMD
[Unit]
Description=MetaTrader Backend API
After=network.target postgresql.service redis-server.service

[Service]
User=$RUN_USER
WorkingDirectory=$BACKEND_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$VENV_DIR/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SYSTEMD

    cat > /etc/systemd/system/metatrader-worker.service << SYSTEMD
[Unit]
Description=MetaTrader Celery Worker
After=network.target redis-server.service

[Service]
User=$RUN_USER
WorkingDirectory=$BACKEND_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$VENV_DIR/bin/celery -A app.worker worker --loglevel=info --concurrency=4
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SYSTEMD

    systemctl daemon-reload
    systemctl enable $SERVICES 2>/dev/null || true
    ok "Systemd services created and enabled"
}

teardown_systemd() {
    info "Removing systemd services..."
    for svc in $SERVICES; do
        systemctl stop "$svc" 2>/dev/null || true
        systemctl disable "$svc" 2>/dev/null || true
        rm -f "/etc/systemd/system/$svc.service"
        ok "Removed $svc"
    done
    systemctl daemon-reload
}

# ── Nginx ───────────────────────────────────────────────────────────────────
setup_nginx() {
    info "Configuring Nginx..."
    cat > /etc/nginx/sites-available/metatrader << NGINX
server {
    listen 80;
    server_name ${DOMAIN};

    root $APP_DIR/frontend/dist;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 86400;
    }

    location / {
        try_files \$uri \$uri/ /index.html;
        expires 1h;
        add_header Cache-Control "public, max-age=3600";
    }

    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
}
NGINX

    ln -sf /etc/nginx/sites-available/metatrader /etc/nginx/sites-enabled/
    if [ -f /etc/nginx/sites-enabled/default ]; then
        rm -f /etc/nginx/sites-enabled/default
        NGINX_DEFAULT_REMOVED="true"
    fi
    if nginx -t 2>/dev/null; then
        systemctl restart nginx
        ok "Nginx configured and restarted"
    else
        err "Nginx config test failed — check /etc/nginx/sites-available/metatrader"
    fi
}

teardown_nginx() {
    info "Removing Nginx site config..."
    rm -f /etc/nginx/sites-enabled/metatrader
    rm -f /etc/nginx/sites-available/metatrader
    if [ "${NGINX_DEFAULT_REMOVED:-false}" = "true" ]; then
        ln -sf /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default 2>/dev/null || true
        ok "Restored default Nginx site"
    fi
    systemctl restart nginx 2>/dev/null || true
}

# ── Frontend build ──────────────────────────────────────────────────────────
build_frontend() {
    info "Building frontend..."
    cd "$APP_DIR/frontend"
    npm ci --silent
    npm run build --silent
    ok "Frontend built → $APP_DIR/frontend/dist/"
}

# ── Alembic migrations ──────────────────────────────────────────────────────
run_migrations() {
    info "Running database migrations..."
    cd "$BACKEND_DIR"
    "$VENV_DIR/bin/alembic" upgrade head
    ok "Migrations applied"
}

# ── Permissions ─────────────────────────────────────────────────────────────
set_permissions() {
    info "Setting permissions..."
    chown -R "$RUN_USER:$RUN_USER" "$APP_DIR"
    ok "Ownership set to $RUN_USER:$RUN_USER"
}

# ═════════════════════════════════════════════════════════════════════════════
# COMMANDS
# ═════════════════════════════════════════════════════════════════════════════

cmd_install() {
    DOMAIN="${1:-}"
    must_be_root
    [ -d "$APP_DIR" ] && die "$APP_DIR already exists. Run 'uninstall' first or 'update' to refresh."

    echo -e "${GREEN}╔══════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   MetaTrader VPS Installer       ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════╝${NC}"

    detect_domain

    # ── Phase 1: System preparation ──
    echo ""; info "PHASE 1: System preparation"
    first_boot_update
    check_python
    mkdir -p "$APP_DIR" "$BACKEND_DIR"

    # ── Phase 2: System packages ──
    echo ""; info "PHASE 2: System packages"
    snapshot_packages
    apt-get install -y -qq \
        "$PYTHON_BIN-venv" "$PYTHON_BIN-dev" \
        postgresql postgresql-client redis-server \
        nginx certbot python3-certbot-nginx \
        nodejs npm curl git build-essential
    record_new_packages
    ensure_system_user

    # ── Phase 3: Database & cache ──
    echo ""; info "PHASE 3: Database & cache"
    setup_postgres
    setup_redis

    # ── Phase 4: Python & application ──
    echo ""; info "PHASE 4: Application environment"
    setup_venv
    setup_env

    # ── Phase 5: Services ──
    echo ""; info "PHASE 5: Services"
    setup_systemd
    setup_nginx

    # ── Phase 6: Build & migrate ──
    echo ""; info "PHASE 6: Build & migrate"
    run_migrations
    build_frontend
    set_permissions
    write_manifest

    # ── Done ──
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════╗${NC}"
    echo -e "${GREEN}║      Setup Complete              ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════╝${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Edit $APP_DIR/.env with your API keys"
    echo "  2. Start:  sudo ./setup.sh start"
    if [ -n "${1:-}" ]; then
        echo "  3. Enable SSL: certbot --nginx -d $DOMAIN"
    fi
    echo ""
    echo "App will be at: http://$DOMAIN"
}

cmd_uninstall() {
    must_be_root
    require_manifest
    read_manifest

    echo -e "${RED}╔══════════════════════════════════╗${NC}"
    echo -e "${RED}║   MetaTrader Uninstall           ║${NC}"
    echo -e "${RED}╚══════════════════════════════════╝${NC}"
    echo ""
    warn "This will DELETE all MetaTrader data including the database."
    warn "Packages that were already installed before this script will be kept."
    echo ""
    read -rp "Type CONFIRM to proceed: " confirm
    [ "$confirm" = "CONFIRM" ] || die "Aborted."

    teardown_systemd
    teardown_nginx
    teardown_postgres

    if id -u "$SYS_USER" &>/dev/null; then
        userdel -r "$SYS_USER" 2>/dev/null || true
        ok "Removed system user '$SYS_USER'"
    fi

    if [ -f "$packages_file" ] && [ -s "$packages_file" ]; then
        local pkg_count; pkg_count=$(wc -l < "$packages_file")
        info "Removing $pkg_count package(s) installed by this script..."
        xargs -a "$packages_file" apt-get purge -y -qq
        ok "Packages removed"
    else
        info "No tracked packages to remove"
    fi

    if [ "${ppa_added:-false}" = "true" ]; then
        info "Removing deadsnakes PPA..."
        add-apt-repository -y --remove ppa:deadsnakes/ppa 2>/dev/null || true
    fi

    rm -f "$MANIFEST_FILE" "$packages_file"
    rm -rf "$APP_DIR"
    ok "Removed $APP_DIR"

    echo ""
    ok "Uninstall complete. The VPS has been returned to its pre-install state."
}

cmd_update() {
    must_be_root
    require_manifest
    [ -d "$APP_DIR/.git" ] || die "Not a git repository. Only git-based installs can be updated."

    info "Updating from git..."
    cd "$APP_DIR"
    git pull origin main
    ok "Git pull complete"

    info "Updating Python dependencies..."
    "$VENV_DIR/bin/pip" install -r "$BACKEND_DIR/requirements.txt" -q
    ok "Python deps updated"

    build_frontend
    set_permissions
    systemctl restart $SERVICES
    ok "Services restarted"
    ok "Update complete"
}

cmd_upgrade() {
    cmd_update
    run_migrations
    ok "Upgrade complete (including migrations)"
}

cmd_start()   { must_be_root; require_manifest; systemctl start $SERVICES;   ok "Services started"; }
cmd_stop()    { must_be_root; require_manifest; systemctl stop $SERVICES;    ok "Services stopped"; }
cmd_restart() { must_be_root; require_manifest; systemctl restart $SERVICES; ok "Services restarted"; }

cmd_reinstall() {
    DOMAIN="${1:-}"
    cmd_uninstall <<< "CONFIRM"
    cmd_install "$DOMAIN"
}

cmd_status() {
    must_be_root; require_manifest; read_manifest
    echo ""
    echo -e "${CYAN}══════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  MetaTrader Status${NC}"
    echo -e "${CYAN}══════════════════════════════════════════════${NC}"

    echo ""; echo "── Services ──"
    for svc in $SERVICES; do
        if systemctl is-active --quiet "$svc" 2>/dev/null; then
            echo -e "  $svc: ${GREEN}active${NC}"
        else
            echo -e "  $svc: ${RED}inactive${NC}"
        fi
    done

    echo ""; echo "── System ──"
    echo "  Domain: ${domain:-unknown}"
    echo "  Python: $("$VENV_DIR/bin/python" --version 2>&1 || echo "not found")"
    echo "  Disk:   $(du -sh "$APP_DIR" 2>/dev/null | awk '{print $1}')"

    echo ""; echo "── Open Ports ──"
    ss -tlnp 2>/dev/null | grep -E ':(80|443|8000|5432|6379)\s' || echo "  (none listening)"

    echo ""; echo "── Last 3 API log lines ──"
    journalctl -u metatrader-api --no-pager -n 3 2>/dev/null || echo "  (no logs)"

    echo ""
}

cmd_logs() {
    local target="${1:-api}"
    must_be_root
    case "$target" in
        api)     journalctl -u metatrader-api -f --no-pager -n 50 ;;
        worker)  journalctl -u metatrader-worker -f --no-pager -n 50 ;;
        nginx)   tail -f /var/log/nginx/access.log /var/log/nginx/error.log ;;
        *)       die "Unknown service: $target. Use: api, worker, or nginx" ;;
    esac
}

cmd_help() {
    echo ""
    echo "MetaTrader — Full Lifecycle Management"
    echo ""
    echo "Usage: sudo ./setup.sh <command> [args]"
    echo ""
    echo "Commands:"
    echo "  install [domain]   Full first-boot setup (fresh Ubuntu 24.04 VPS)"
    echo "  uninstall          Reverse everything this script created"
    echo "  reinstall [domain] Uninstall + install fresh"
    echo "  update             Git pull + rebuild + restart"
    echo "  upgrade            Update + run DB migrations"
    echo "  start              Start metatrader-api and metatrader-worker"
    echo "  stop               Stop all services"
    echo "  restart            Restart all services"
    echo "  status             Show service health, disk usage, open ports"
    echo "  logs [api|worker|nginx]  Tail service logs"
    echo "  help               Show this message"
    echo ""
    echo "Python requirement: $REQUIRED_PYTHON.x (auto-installed if missing)"
    echo "First install auto-detects public IPv4 if no domain provided."
    echo ""
}

# ═════════════════════════════════════════════════════════════════════════════
# DISPATCH
# ═════════════════════════════════════════════════════════════════════════════
COMMAND="${1:-help}"
shift || true

case "$COMMAND" in
    install)    cmd_install "$@" ;;
    uninstall)  cmd_uninstall "$@" ;;
    reinstall)  cmd_reinstall "$@" ;;
    update)     cmd_update ;;
    upgrade)    cmd_upgrade ;;
    start)      cmd_start ;;
    stop)       cmd_stop ;;
    restart)    cmd_restart ;;
    status)     cmd_status ;;
    logs)       cmd_logs "$@" ;;
    help|--help|-h) cmd_help ;;
    *)          echo "Unknown command: $COMMAND"; cmd_help; exit 1 ;;
esac