import logging

from fastapi import FastAPI, WebSocket, Depends, Query
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import engine, Base
from app.core.security import decode_token
from app.api.routes import auth, market, trading, strategies, costs, learning, scripts, settings, admin
from app.api.websocket import websocket_endpoint

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(title=settings.APP_NAME, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(market.router)
app.include_router(trading.router)
app.include_router(strategies.router)
app.include_router(costs.router)
app.include_router(learning.router)
app.include_router(scripts.router)
app.include_router(settings.router)
app.include_router(admin.router)


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")


@app.on_event("shutdown")
async def shutdown():
    await engine.dispose()
    from app.market.websocket import get_binance_ws
    ws = get_binance_ws()
    try:
        await ws.close()
    except Exception:
        pass
    logger.info("Shutdown complete")


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "app": settings.APP_NAME}


@app.websocket("/ws/{user_id}")
async def ws_route(websocket: WebSocket, user_id: int, token: str = Query(...)):
    try:
        payload = decode_token(token)
        token_user_id = int(payload.get("sub", 0))
        if token_user_id != user_id:
            await websocket.close(code=4003)
            return
    except Exception:
        await websocket.close(code=4001)
        return

    await websocket_endpoint(websocket, user_id)