# MetaTrader — AI-Powered Paper Trading Bot

A mobile-optimized paper trading platform with a built-in automated trading bot that uses OpenRouter LLMs to analyze market data and execute trades. Features a ComfyUI-style node orchestrator, RAG memory, auto-improvement, per-user API key management with hot-reload, an admin panel, and real-time cost tracking.

## Features

### Trading
- **Paper broker** with market/limit orders, slippage, and commission simulation
- **Portfolio management** — cash balance, positions, P&L, and equity tracking
- **Risk management** — position sizing, stop-loss, take-profit, and drawdown circuit breaker
- **Multi-portfolio** support with per-portfolio risk config
- **Binance.US** real-time market data (REST + WebSocket streams)

### AI Model Orchestrator (ComfyUI-style)
- **8 node types**: Trigger, Market Data, LLM Model, Council, Filter, Merge, Action, Script
- **Drag-and-drop** canvas with connectable nodes (ReactFlow v12)
- **Council voting** — N models vote, a presiding judge makes the final decision
- **Parallel execution** — same-level nodes run simultaneously
- **Concurrent strategies** — run multiple graph strategies with independent schedules
- **Streaming execution** via SSE (Server-Sent Events)

### Per-User API Key Management
- **OpenRouter** and **Binance.US** keys stored per-user in the database
- **Fernet symmetric encryption** — keys encrypted at rest, decrypted on demand
- **Hot-reload** — changing keys in the dashboard takes effect immediately; no restart required
- **30-second credential cache** with instant invalidation on save
- **Fallback chain** — per-user keys override environment variable defaults; env vars serve as global fallbacks
- **Masked key previews** in settings (e.g. `sk-or-v1-****abcd`)

### Admin Panel
- **User management** — view all users, toggle active/disabled, promote/demote admins, delete accounts (cascade)
- **Registration control** — enable/disable new signups from the dashboard
- **Base URL configuration** — OpenRouter API URL, Binance API URL, Binance WebSocket URL (admin-managed, changes take effect immediately)
- **System stats** — total users, strategies, trades, P&L, and LLM costs
- **Self-protection** — admins cannot delete themselves or remove the last admin
- **First-user auto-admin** — the first account registered automatically becomes admin

### Learning & Memory
- **ChromaDB** vector store for trade embeddings
- **RAG context** — similar past trades injected into LLM prompts
- **Auto-improver** — 5 mutation types (model swap, temperature tweak, prompt optimization, threshold adjust, node rewire)
- **Performance analyzer** — win rate, Sharpe ratio, profit factor, per-model breakdown

### Cost Tracking
- **OpenRouter `usage.cost`** extraction and logging for every LLM call
- **Per-model daily budget** enforcement with auto-fallback to cheaper models
- **Per-strategy cost** breakdown
- **Predictive projection** — 7-day and 30-day cost forecasts
- **Real-time** WebSocket cost updates

### Strategy Editor
- **Monaco editor** with Python syntax highlighting and 15+ autocompletion snippets
- **4 built-in templates** (RSI, MA Crossover, Volume Spike, Portfolio Monitor)
- **Code validation** with security sandbox (AST-level import/function checks)
- **Live execution** with sandboxed access to market data, paper trading, and model APIs
- Save/load/delete from script library

### Dashboard
- **7 tabs**: Market, Orchestrator, Editor, Stats, Costs, Settings, Admin (admin-only)
- **Mobile-first** responsive design (Tailwind CSS 4)
- **Dark/light theme** toggle
- **Keyboard shortcuts**: `1-6` for tab navigation, `Ctrl+D` / `Cmd+D` for theme

---

## Quick Start

### Prerequisites
- Python 3.12+, PostgreSQL 16, Redis, Node.js 20+, npm

### Backend Setup

```bash
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env from example and fill in your keys
cp .env.example .env
# Edit .env — set SECRET_KEY, DATABASE_URL, and optionally OpenRouter API key

# Create database and run migrations
createdb metatrader
alembic upgrade head

# Start the API server
uvicorn app.main:app --reload --port 8000

# In a separate terminal, start the Celery worker
celery -A app.worker worker --loglevel=info --concurrency=4
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev       # Dev server on :5173 (proxies API to :8000)
npm run build     # Production build to dist/
```

The frontend dev server proxies `/api` and `/ws` requests to the backend at `127.0.0.1:8000`.

### First Login
1. Open `http://localhost:5173`
2. Register an account — since the users table is empty, you will automatically become admin
3. Configure your API keys in **Settings → API Keys** (OpenRouter required for LLM features)
4. Create a portfolio in **Market** or **Stats** tab
5. Build a strategy in **Orchestrator** and start trading

---

## VPS Deployment

One-command setup for Ubuntu 24.04:

```bash
# Clone and run setup
git clone <your-repo-url> /opt/metatrader
cd /opt/metatrader
sudo scripts/setup.sh your-domain.com

# Edit environment
nano /opt/metatrader/.env

# Run database migrations
cd /opt/metatrader/backend
source venv/bin/activate
alembic upgrade head

# Build frontend
cd /opt/metatrader/frontend
npm run build

# Start services
systemctl start metatrader-api metatrader-worker
systemctl enable metatrader-api metatrader-worker
```

The setup script installs PostgreSQL, Redis, Nginx, Node.js, and configures systemd services with TLS-ready Nginx configuration. Run `certbot --nginx -d your-domain.com` for HTTPS.

---

## Architecture

```
Frontend (React 19 + Vite 8) ──REST/WS──> Backend (FastAPI async)
                                              │
              ┌─────────────────┬─────────────┼─────────────┬─────────────────┐
              │                 │             │             │                 │
         Market Data      Credential       Model Graph   Trading Engine     Admin
       (Binance.US API)    Service       (DAG executor +  (Paper broker +  (RBAC +
                            │            council voting)  risk manager)   settings)
                            │                 │             │                 │
              ┌─────────────┘                 │             │                 │
              │                        ┌──────┴──────┐      │                 │
         User API Keys              Learning Layer  │  Portfolio Mgr       System
       (Fernet encrypted)        (ChromaDB + RAG +  │  (positions + P&L)  Settings
        per-user in DB            auto-improver)     │                     (DB-backed
              │                         │            │                    hot-reload)
              └─────────────┬───────────┘            │
                            │                  Cost Tracking
                      Credential Cache      (usage.cost + budgets
                        (30s TTL)            + predictive + fallback)
```

### Key Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Backend framework | FastAPI (async) | WebSocket, auto-docs, Python ML ecosystem |
| Graph engine | Custom DAG executor | Full control over node types, parallel execution, council voting |
| Node UI | ReactFlow v12 | ComfyUI-style handles, edges, and custom node panels |
| Vector DB | ChromaDB (embedded) | Zero infrastructure, fast for trade memory similarity search |
| Cost tracking | First-class DB table | Every OpenRouter call logged with `usage.cost` |
| Strategy scripts | Python sandbox (AST-level) | Secure execution with access to market data and paper trading APIs |
| **API key storage** | **Per-user, Fernet-encrypted in DB** | **Isolation between users; env vars as global fallback** |
| **Credential hot-reload** | **30s TTL cache + instant invalidation** | **No restart needed; changes take effect on next API call** |
| **Admin RBAC** | **`is_admin` flag on User** | **Simple, no separate role table; sufficient for single-tenant per-user model** |
| **Registration toggle** | **`SystemSetting` DB table** | **Admins can block new signups from the dashboard; persists across restarts** |

---

## API Endpoints

| Prefix | Routes | Description |
|--------|--------|-------------|
| `/api/auth` | 6 | Register, login, refresh, profile, logout, registration-status |
| `/api/market` | 6 | Symbols, prices, klines, indicators, ticker, orderbooks |
| `/api/trading` | 13 | Portfolios, market/limit orders, positions, trades, risk config |
| `/api/strategies` | 18 | CRUD + nodes/edges + execute/start/stop/stream/clone |
| `/api/costs` | 13 | Today, by-strategy, predictive, budgets, history, model rates |
| `/api/learning` | 11 | Memory, performance snapshots, auto-improver |
| `/api/scripts` | 8 | CRUD, execute, validate, templates |
| `/api/settings` | 3 | Per-user API keys — get, save, delete (encrypted storage) |
| `/api/admin` | 5 | Users CRUD, system settings, site-wide stats (admin-only) |

All authenticated endpoints are scoped to the current user. Admin endpoints require the `is_admin` flag.

---

## Project Stats

| Metric | Count |
|--------|-------|
| Total lines of code | ~10,558 |
| Backend Python files | 53 (7,226 lines) |
| Backend functions | 138 |
| Backend classes | 75 |
| Frontend TypeScript/TSX files | 18 (3,041 lines) |
| Frontend components | 10 |
| Frontend functions | 43 |
| Database models | 14 |
| API endpoints | 84 |
| Database migrations | 2 |
| Zustand stores | 5 |
| Custom hooks | 1 |

---

## Environment Variables

All variables are loaded from `.env` via `pydantic-settings`. Values shown are defaults.

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `MetaTrader` | Application name |
| `DEBUG` | `false` | Enable debug mode |
| `SECRET_KEY` | *(placeholder)* | JWT signing key — **must be changed in production** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime |
| `ALGORITHM` | `HS256` | JWT signing algorithm |
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL connection string (async driver) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `CELERY_BROKER_URL` | `redis://localhost:6379/1` | Celery message broker |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/2` | Celery result backend |
| `OPENROUTER_API_KEY` | *(empty)* | OpenRouter API key — global fallback; users can override per-account |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter API base URL — admin-overridable |
| `BINANCE_API_KEY` | *(empty)* | Binance.US API key — global fallback; users can override per-account |
| `BINANCE_API_SECRET` | *(empty)* | Binance.US API secret — global fallback |
| `BINANCE_API_BASE` | `https://api.binance.us` | Binance REST API base — admin-overridable |
| `BINANCE_WS_BASE` | `wss://stream.binance.us:9443/ws` | Binance WebSocket base — admin-overridable |
| `CHROMA_PERSIST_DIR` | `./chroma_data` | ChromaDB vector store directory |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | Allowed CORS origins (comma-separated) |

**Base URLs** (`OPENROUTER_BASE_URL`, `BINANCE_API_BASE`, `BINANCE_WS_BASE`) can also be changed by an admin through the Admin panel without editing `.env` or restarting.

**API keys** (`OPENROUTER_API_KEY`, `BINANCE_API_KEY`, `BINANCE_API_SECRET`) set in `.env` are global fallbacks. Individual users can set their own keys via **Settings → API Keys** in the dashboard. Per-user keys are encrypted with Fernet (key derived from `SECRET_KEY`), cached for 30 seconds, and hot-reloaded on every API call.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend Framework** | FastAPI 0.115 (Python 3.12+, async) |
| **ASGI Server** | Uvicorn 0.34 |
| **ORM** | SQLAlchemy 2.0 (async) + asyncpg |
| **Database** | PostgreSQL 16 |
| **Migrations** | Alembic 1.14 |
| **Task Queue** | Celery 5.4 + Redis 5.2 |
| **Vector DB** | ChromaDB 0.5 (embedded) |
| **Auth** | python-jose (JWT) + passlib (bcrypt) |
| **Encryption** | cryptography (Fernet) |
| **LLM Gateway** | OpenRouter API |
| **Market Data** | Binance.US REST + WebSocket |
| **Frontend Framework** | React 19 + TypeScript 6.0 |
| **Build Tool** | Vite 8.1 |
| **CSS** | Tailwind CSS 4.3 |
| **State Management** | Zustand 5.0 |
| **Graph Editor** | @xyflow/react 12.11 (ReactFlow) |
| **Charts** | lightweight-charts 5.2 |
| **Code Editor** | @monaco-editor/react 4.7 |
| **Linting** | oxlint 1.69 |
| **Deployment** | Nginx reverse proxy + systemd on Ubuntu 24.04 |

---

## License

MIT
