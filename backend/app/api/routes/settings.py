from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.credentials import credential_service
from app.models.models import User

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SaveKeysRequest(BaseModel):
    api_key: str
    api_secret: str = ""


@router.get("/keys")
async def get_services(
    current_user: User = Depends(get_current_user),
):
    services = await credential_service.get_stored_services(current_user.id)
    return {"services": services}


@router.put("/keys/{service}")
async def save_keys(
    service: str,
    data: SaveKeysRequest,
    current_user: User = Depends(get_current_user),
):
    if service not in ("openrouter", "binance"):
        raise HTTPException(status_code=400, detail="Service must be 'openrouter' or 'binance'")
    await credential_service.store_keys(current_user.id, service, data.api_key, data.api_secret)
    return {"message": f"{service} keys saved"}


@router.delete("/keys/{service}")
async def delete_keys(
    service: str,
    current_user: User = Depends(get_current_user),
):
    deleted = await credential_service.delete_keys(current_user.id, service)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No keys found for {service}")
    return {"message": f"{service} keys removed"}