from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import User, CustomScript
from app.scripts.sandbox import sandbox_factory
from app.scripts.validator import validate_script, extract_functions, extract_symbols

router = APIRouter(prefix="/api/scripts", tags=["scripts"])


class ScriptCreate(BaseModel):
    name: str
    python_code: str


class ScriptUpdate(BaseModel):
    name: str | None = None
    python_code: str | None = None


class ScriptExecute(BaseModel):
    code: str
    portfolio_id: int | None = None
    strategy_id: int | None = None
    input_data: dict | None = None


@router.get("")
async def list_scripts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CustomScript)
        .where(CustomScript.user_id == current_user.id)
        .order_by(CustomScript.updated_at.desc())
    )
    scripts = result.scalars().all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "code_preview": s.python_code[:100] + ("..." if len(s.python_code) > 100 else ""),
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in scripts
    ]


@router.post("")
async def create_script(
    data: ScriptCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    valid, errors = validate_script(data.python_code)
    if not valid:
        raise HTTPException(status_code=400, detail={"errors": errors})

    script = CustomScript(
        user_id=current_user.id,
        name=data.name,
        python_code=data.python_code,
    )
    db.add(script)
    await db.flush()
    return {"id": script.id, "name": script.name}


@router.get("/{script_id}")
async def get_script(
    script_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CustomScript).where(
            CustomScript.id == script_id,
            CustomScript.user_id == current_user.id,
        )
    )
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")

    functions = extract_functions(script.python_code)
    symbols = extract_symbols(script.python_code)

    return {
        "id": script.id,
        "name": script.name,
        "python_code": script.python_code,
        "functions": functions,
        "symbols": symbols,
        "created_at": script.created_at.isoformat() if script.created_at else None,
        "updated_at": script.updated_at.isoformat() if script.updated_at else None,
    }


@router.put("/{script_id}")
async def update_script(
    script_id: int,
    data: ScriptUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CustomScript).where(
            CustomScript.id == script_id,
            CustomScript.user_id == current_user.id,
        )
    )
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")

    if data.python_code is not None:
        valid, errors = validate_script(data.python_code)
        if not valid:
            raise HTTPException(status_code=400, detail={"errors": errors})

    if data.name is not None:
        script.name = data.name
    if data.python_code is not None:
        script.python_code = data.python_code

    await db.flush()
    return {"id": script.id, "name": script.name, "updated": True}


@router.delete("/{script_id}")
async def delete_script(
    script_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CustomScript).where(
            CustomScript.id == script_id,
            CustomScript.user_id == current_user.id,
        )
    )
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    await db.delete(script)
    return {"message": "Script deleted"}


@router.post("/execute")
async def execute_script(
    data: ScriptExecute,
    current_user: User = Depends(get_current_user),
):
    valid, errors = validate_script(data.code)
    if not valid:
        raise HTTPException(status_code=400, detail={"errors": errors})

    sandbox = sandbox_factory(
        user_id=current_user.id,
        portfolio_id=data.portfolio_id,
        strategy_id=data.strategy_id,
    )

    result = await sandbox.execute(
        code=data.code,
        input_data=data.input_data or {},
    )

    return result


@router.post("/validate")
async def validate_code(data: ScriptExecute):
    valid, errors = validate_script(data.code)
    functions = extract_functions(data.code) if valid else []
    symbols = extract_symbols(data.code) if valid else []
    return {
        "valid": valid,
        "errors": errors,
        "functions": functions,
        "symbols": symbols,
    }


@router.get("/templates")
async def get_templates():
    return [
        {
            "name": "RSI Mean Reversion",
            "description": "Buy when RSI < 30, sell when RSI > 70",
            "code": '''# RSI Mean Reversion Strategy
async def run():
    symbol = "BTCUSDT"
    rsi = await market.get_indicator(symbol, "RSI", period=14)
    price = await market.get_price(symbol)
    positions = await portfolio.get_positions()

    print(f"{symbol} RSI: {rsi:.1f}, Price: ${price:.2f}")

    if rsi < 30 and symbol not in positions:
        await trade.buy(symbol, quantity=0.01)
        print(f"BUY signal: RSI oversold at {rsi:.1f}")
    elif rsi > 70 and symbol in positions:
        await trade.sell(symbol, quantity=positions[symbol]["quantity"])
        print(f"SELL signal: RSI overbought at {rsi:.1f}")
    else:
        print("HOLD: No clear signal")

result = await run()''',
        },
        {
            "name": "Moving Average Crossover",
            "description": "Buy when fast MA crosses above slow MA",
            "code": '''# MA Crossover Strategy
async def run():
    symbol = "ETHUSDT"
    klines = await market.get_klines(symbol, "15m", 50)
    price = await market.get_price(symbol)

    # Compute MAs
    closes = [k["close"] for k in klines]
    fast_ma = sum(closes[-12:]) / 12
    slow_ma = sum(closes[-26:]) / 26
    positions = await portfolio.get_positions()

    print(f"{symbol} Fast MA: {fast_ma:.2f}, Slow MA: {slow_ma:.2f}")

    if fast_ma > slow_ma and symbol not in positions:
        await trade.buy(symbol, quantity=0.1)
        print("BUY: Fast MA crossed above Slow MA")
    elif fast_ma < slow_ma and symbol in positions:
        await trade.sell(symbol, quantity=positions[symbol]["quantity"])
        print("SELL: Fast MA crossed below Slow MA")
    else:
        print("HOLD: No crossover")

result = await run()''',
        },
        {
            "name": "Volume Spike Alert",
            "description": "Detect unusual volume and log it",
            "code": '''# Volume Spike Detector
async def run():
    symbol = "BTCUSDT"
    klines = await market.get_klines(symbol, "5m", 30)

    volumes = [k["volume"] for k in klines]
    avg_volume = sum(volumes[:-1]) / max(len(volumes) - 1, 1)
    current_volume = volumes[-1] if volumes else 0
    price = await market.get_price(symbol)

    ratio = current_volume / avg_volume if avg_volume > 0 else 0
    print(f"{symbol} Price: ${price:.2f} | Vol ratio: {ratio:.1f}x")

    if ratio > 2.0:
        print(f"ALERT: {ratio:.1f}x normal volume!")
        prediction = await model.predict(
            name="gpt-4o-mini",
            prompt=f"Volume {ratio:.1f}x average for {symbol} at ${price:.2f}. Action?"
        )
        print(f"Model prediction: {prediction}")

result = await run()''',
        },
        {
            "name": "Portfolio Monitor",
            "description": "Check portfolio health and log status",
            "code": '''# Portfolio Monitor
async def run():
    balance = await portfolio.get_balance()
    equity = await portfolio.get_equity()
    positions = await portfolio.get_positions()
    pnl = await portfolio.get_pnl()

    print(f"=== Portfolio Status ===")
    print(f"Cash Balance: ${balance:,.2f}")
    print(f"Total Equity: ${equity:,.2f}")
    print(f"Unrealized PnL: ${pnl:,.2f}")
    print(f"Active Positions: {len(positions)}")

    for symbol, pos in positions.items():
        upnl = pos.get("unrealized_pnl", 0)
        emoji = "+" if upnl > 0 else ""
        print(f"  {symbol}: {pos['quantity']} @ ${pos['avg_entry']:.2f} | PnL: {emoji}${upnl:.2f}")

result = await run()''',
        },
    ]