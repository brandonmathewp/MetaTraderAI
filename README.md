# MetaTrader — AI-Powered Paper Trading Bot

A mobile-optimized paper trading platform with a built-in automated trading bot that uses OpenRouter LLMs to analyze market data and execute trades. Features a **ComfyUI-style node orchestrator**, RAG memory, auto-improvement, and real-time cost tracking.

## Features

### Trading
- **Paper broker** with market/limit orders, slippage, commission simulation
- **Portfolio management** — cash balance, positions, P&L, equity tracking
- **Risk management** — position sizing, stop-loss, take-profit, drawdown circuit breaker
- **Multi-portfolio** support
- **Binance.US** real-time market data (REST + WebSocket streams)

### AI Model Orchestrator (ComfyUI-style)
- **8 node types**: Trigger, Market Data, LLM Model, Council, Filter, Merge, Action, Script
- **Drag-and-drop** canvas with connectable nodes
- **Council voting** — N models vote, presiding judge decides
- **Parallel execution** — same-level nodes run simultaneously
- **Concurrent strategies** — run multiple graph strategies at once
- **Streaming execution** via SSE (Server-Sent Events)

### Learning & Memory
- **ChromaDB** vector store for trade embeddings
- **RAG context** — similar past trades injected into LLM prompts
- **Auto-improver** — 5 mutation types (model swap, temp tweak, prompt optimization, threshold adjust, node rewire)
- **Performance analyzer** — win rate, Sharpe ratio, profit factor, per-model breakdown

### Cost Tracking
- **OpenRouter usage.cost** extraction and logging
- **Per-model budget** enforcement with auto-fallback to cheaper models
- **Per-strategy cost** breakdown
- **30-day predictive** cost projection
- **Real-time** WebSocket cost updates

### Strategy Editor
- **Monaco editor** with Python syntax highlighting
- **15+ autocompletion** snippets for sandbox APIs
- **4 built-in templates** (RSI, MA Crossover, Volume Spike, Portfolio Monitor)
- **Code validation** with security sandbox (AST-level checks)
- **Ctrl+S** saves to backend, load/delete from library

### Dashboard
- **6 tabs**: Market, Orchestrator, Editor, Stats, Costs, Settings
- **Mobile-first** responsive design
- **Dark/light theme** toggle
- **Keyboard shortcuts**: 1-6 for tab navigation, Ctrl+S for save, Ctrl+D for theme

---

## Quick Start

### Prerequisites
- Python 3.12+, PostgreSQL 16, Redis, Node.js 20+

### Backend Setup
```bash
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env from example and fill in your keys
cp .env.example .env
# Edit .env with your OpenRouter API key

# Create database
createdb metatrader

# Run
uvicorn app.main:app --reload --port 8000
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev       # Dev server on :5173
npm run build     # Production build to dist/
```

### VPS Deployment
```bash
# One-command setup (Ubuntu 24.04)
sudo scripts/setup.sh your-domain.com

# Then edit /opt/metatrader/.env with your API keys
# Build frontend and start:
cd /opt/metatrader/frontend && npm run build
systemctl start metatrader-api metatrader-worker
```

---

## Architecture

```
Frontend (React + Vite)  ──REST/WS──>  Backend (FastAPI)
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
              Market Data            Model Graph            Trading Engine
           (Binance.US API)      (DAG executor +         (Paper broker +
                                 council voting)         risk manager)
                    │                      │                      │
                    └──────────────────────┼──────────────────────┘
                                           │
                              ┌────────────┴────────────┐
                              │                         │
                         Learning Layer           Cost Tracking
                      (ChromaDB + RAG +        (usage.cost +
                       auto-improver)          budgets + fallback)
```

### Key Design Decisions
| Decision | Choice | Reason |
|----------|--------|--------|
| Backend | FastAPI (async) | WebSocket, auto-docs, Python ML ecosystem |
| Graph engine | Custom DAG executor | Full control over node types, parallel/council |
| Node UI | ReactFlow v12 | ComfyUI-like handles, edges, custom nodes |
| Vector DB | ChromaDB (embedded) | Zero infra, fast for trade memory |
| Cost tracking | First-class DB table | Every OpenRouter call logged with usage.cost |
| Strategy scripts | Python sandbox | Live market data, paper trading, model access |

### API Endpoints
| Prefix | Routes | Description |
|--------|--------|-------------|
| `/api/auth` | 5 | Registration, login, refresh, profile |
| `/api/market` | 6 | Symbols, prices, klines, indicators, orderbooks |
| `/api/trading` | 12 | Portfolios, market/limit orders, positions, risk config |
| `/api/strategies` | 17 | CRUD + nodes/edges + execute/start/stop/stream/clone |
| `/api/costs` | 13 | Today, by-strategy, predictive, budgets, history, model rates |
| `/api/learning` | 11 | Memory, performance, auto-improver |
| `/api/scripts` | 8 | CRUD, execute, validate, templates |

---

## Environment Variables

```env
SECRET_KEY=change-me-use-openssl-rand-hex-32
DATABASE_URL=postgresql+asyncpg://metatrader:metatrader@localhost:5432/metatrader
REDIS_URL=redis://localhost:6379/0
OPENROUTER_API_KEY=sk-or-v1-your-key-here
BINANCE_API_KEY=           # Optional — for account access
BINANCE_API_SECRET=         # Optional
CORS_ORIGINS=http://localhost:5173
CHROMA_PERSIST_DIR=./chroma_data
```

---

## License

MIT