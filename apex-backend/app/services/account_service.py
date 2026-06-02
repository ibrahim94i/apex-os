"""Active account mode — Demo vs Real (Redis-backed)."""

from app.config.accounts import (
    DEFAULT_ACCOUNT_MODE,
    get_balance_for_mode,
    get_label_for_mode,
)
from app.core.redis_client import cache_get, cache_set

REDIS_ACCOUNT_MODE_KEY = "apex:account_mode"


class AccountService:
    async def get_mode(self) -> str:
        cached = await cache_get(REDIS_ACCOUNT_MODE_KEY)
        if cached and cached.get("mode") in ("demo", "real"):
            return cached["mode"]
        return DEFAULT_ACCOUNT_MODE

    async def set_mode(self, mode: str) -> dict[str, str | float]:
        if mode not in ("demo", "real"):
            mode = DEFAULT_ACCOUNT_MODE
        await cache_set(REDIS_ACCOUNT_MODE_KEY, {"mode": mode})
        return await self.get_status(mode)

    async def get_balance(self) -> float:
        mode = await self.get_mode()
        return get_balance_for_mode(mode)

    async def get_status(self, mode: str | None = None) -> dict[str, str | float]:
        active = mode or await self.get_mode()
        return {
            "mode": active,
            "balance": get_balance_for_mode(active),
            "label_ar": get_label_for_mode(active),
        }


account_service = AccountService()
