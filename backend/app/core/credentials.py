import base64
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.models.models import ApiKey, SystemSetting

logger = logging.getLogger(__name__)

_CACHE_TTL = timedelta(seconds=30)

settings = get_settings()


def _derive_fernet_key(secret: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())


class CredentialService:
    def __init__(self):
        self._fernet = Fernet(_derive_fernet_key(settings.SECRET_KEY))
        self._cache: dict[int, dict] = {}
        self._cache_times: dict[int, datetime] = {}

    def _is_cache_valid(self, user_id: int) -> bool:
        if user_id not in self._cache:
            return False
        age = datetime.now(timezone.utc) - self._cache_times[user_id]
        return age < _CACHE_TTL

    def invalidate_cache(self, user_id: int) -> None:
        self._cache.pop(user_id, None)
        self._cache_times.pop(user_id, None)

    async def store_keys(self, user_id: int, service: str, api_key: str, api_secret: str) -> None:
        encrypted_key = self._fernet.encrypt(api_key.encode()).decode()
        encrypted_secret = self._fernet.encrypt(api_secret.encode()).decode()

        async with async_session_factory() as db:
            result = await db.execute(
                select(ApiKey).where(
                    ApiKey.user_id == user_id,
                    ApiKey.exchange == service,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.api_key_encrypted = encrypted_key
                existing.api_secret_encrypted = encrypted_secret
            else:
                db.add(ApiKey(
                    user_id=user_id,
                    exchange=service,
                    api_key_encrypted=encrypted_key,
                    api_secret_encrypted=encrypted_secret,
                ))
            await db.commit()

        self.invalidate_cache(user_id)
        logger.info(f"Stored API keys for user {user_id} / service {service}")

    async def get_keys(self, user_id: int, service: str) -> Optional[dict]:
        if self._is_cache_valid(user_id):
            cached = self._cache[user_id]
            return cached.get(service)

        async with async_session_factory() as db:
            result = await db.execute(
                select(ApiKey).where(
                    ApiKey.user_id == user_id,
                    ApiKey.exchange == service,
                )
            )
            row = result.scalar_one_or_none()

        if row:
            try:
                decrypted_key = self._fernet.decrypt(row.api_key_encrypted.encode()).decode()
                decrypted_secret = self._fernet.decrypt(row.api_secret_encrypted.encode()).decode()
            except Exception as e:
                logger.error(f"Failed to decrypt key for user {user_id}: {e}")
                return None
            key_data = {"service": service, "api_key": decrypted_key, "api_secret": decrypted_secret}
        else:
            key_data = None

        if user_id not in self._cache:
            self._cache[user_id] = {}
        self._cache[user_id][service] = key_data
        self._cache_times[user_id] = datetime.now(timezone.utc)

        return key_data

    async def delete_keys(self, user_id: int, service: str) -> bool:
        async with async_session_factory() as db:
            result = await db.execute(
                select(ApiKey).where(
                    ApiKey.user_id == user_id,
                    ApiKey.exchange == service,
                )
            )
            row = result.scalar_one_or_none()
            if row:
                await db.delete(row)
                await db.commit()
                self.invalidate_cache(user_id)
                return True
        return False

    async def get_effective_key(self, user_id: int, service: str, env_key: str = "") -> Optional[str]:
        keys = await self.get_keys(user_id, service)
        if keys:
            return keys["api_key"]
        return env_key or None

    async def get_effective_secret(self, user_id: int, service: str, env_secret: str = "") -> Optional[str]:
        keys = await self.get_keys(user_id, service)
        if keys:
            return keys["api_secret"]
        return env_secret or None

    async def get_stored_services(self, user_id: int) -> list[dict]:
        async with async_session_factory() as db:
            result = await db.execute(
                select(ApiKey).where(ApiKey.user_id == user_id)
            )
            rows = result.scalars().all()
        masked = []
        for row in rows:
            key_plain = ""
            try:
                key_plain = self._fernet.decrypt(row.api_key_encrypted.encode()).decode()
            except Exception:
                pass
            if len(key_plain) > 12:
                key_preview = key_plain[:8] + "****" + key_plain[-4:]
            elif key_plain:
                key_preview = key_plain[:4] + "****"
            else:
                key_preview = "****"
            masked.append({
                "id": row.id,
                "service": row.exchange,
                "key_preview": key_preview,
            })
        return masked

    async def get_system_setting(self, key: str, default: str = "") -> str:
        async with async_session_factory() as db:
            result = await db.execute(
                select(SystemSetting).where(SystemSetting.key == key)
            )
            row = result.scalar_one_or_none()
        return row.value if row else default

    async def get_all_system_settings(self) -> dict[str, str]:
        async with async_session_factory() as db:
            result = await db.execute(select(SystemSetting))
            rows = result.scalars().all()
        return {row.key: row.value for row in rows}

    async def set_system_setting(self, key: str, value: str) -> None:
        async with async_session_factory() as db:
            result = await db.execute(
                select(SystemSetting).where(SystemSetting.key == key)
            )
            row = result.scalar_one_or_none()
            if row:
                row.value = value
            else:
                db.add(SystemSetting(key=key, value=value))
            await db.commit()
        logger.info(f"System setting '{key}' updated to '{value}'")


credential_service = CredentialService()