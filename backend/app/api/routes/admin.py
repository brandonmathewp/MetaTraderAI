import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.credentials import credential_service
from app.models.models import User, Portfolio, Trade, Strategy, ModelCost

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


class UpdateUserRequest(BaseModel):
    is_active: bool | None = None
    is_admin: bool | None = None


class SystemSettingsUpdate(BaseModel):
    key: str
    value: str


@router.get("/users")
async def list_users(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "is_active": u.is_active,
            "is_admin": u.is_admin,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    data: UpdateUserRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == admin.id and data.is_admin is False:
        raise HTTPException(status_code=400, detail="Cannot demote yourself")

    user_count = await db.execute(select(func.count(User.id)).where(User.is_admin == True))
    admin_count = user_count.scalar()
    if user.is_admin and data.is_admin is False and admin_count <= 1:
        raise HTTPException(status_code=400, detail="Cannot remove the last admin")

    if data.is_active is not None:
        user.is_active = data.is_active
    if data.is_admin is not None:
        user.is_admin = data.is_admin
    await db.commit()

    logger.info(f"Admin {admin.email} updated user {user.email}: is_active={user.is_active}, is_admin={user.is_admin}")
    return {"message": "User updated", "user_id": user_id}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user_email = user.email
    await db.delete(user)
    await db.commit()

    logger.info(f"Admin {admin.email} deleted user {user_email}")
    return {"message": "User deleted", "user_id": user_id}


@router.get("/settings")
async def get_settings(
    admin: User = Depends(require_admin),
):
    all_settings = await credential_service.get_all_system_settings()
    defaults = {
        "registration_enabled": "true",
        "openrouter_base_url": "",
        "binance_api_base": "",
        "binance_ws_base": "",
    }
    return {**defaults, **all_settings}


@router.put("/settings")
async def update_settings(
    data: SystemSettingsUpdate,
    admin: User = Depends(require_admin),
):
    await credential_service.set_system_setting(data.key, data.value)
    logger.info(f"Admin {admin.email} updated system setting '{data.key}'")
    return {"message": "Setting updated", "key": data.key, "value": data.value}


@router.get("/stats")
async def get_stats(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user_count = await db.execute(select(func.count(User.id)))
    total_users = user_count.scalar()

    strat_count = await db.execute(select(func.count(Strategy.id)))
    total_strategies = strat_count.scalar()

    trade_count = await db.execute(select(func.count(Trade.id)))
    total_trades = trade_count.scalar()

    pnl_result = await db.execute(
        select(func.sum(Trade.outcome_pnl)).where(Trade.outcome_pnl is not None)
    )
    total_pnl = pnl_result.scalar() or 0

    cost_result = await db.execute(select(func.sum(ModelCost.usd_cost)))
    total_costs = cost_result.scalar() or 0

    return {
        "total_users": total_users,
        "total_strategies": total_strategies,
        "total_trades": total_trades,
        "total_pnl": round(total_pnl, 4),
        "total_costs": round(total_costs, 4),
    }