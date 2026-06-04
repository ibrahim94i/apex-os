"""Active account mode — Demo vs Real with configurable real balance."""

from app.config.accounts import (
    DEFAULT_ACCOUNT_MODE,
    REDIS_REAL_BALANCE_KEY,
    get_balance_for_mode,
    get_default_real_balance,
    get_label_for_mode,
    is_balance_editable,
)
from app.core.redis_client import cache_get, cache_set

REDIS_ACCOUNT_MODE_KEY = "apex:account_mode"


class AccountService:
    async def get_mode(self) -> str:
        cached = await cache_get(REDIS_ACCOUNT_MODE_KEY)
        if cached and cached.get("mode") in ("demo", "real"):
            return cached["mode"]
        return DEFAULT_ACCOUNT_MODE

    async def get_real_balance_override(self) -> float | None:
        cached = await cache_get(REDIS_REAL_BALANCE_KEY)
        if cached and "balance" in cached:
            try:
                return float(cached["balance"])
            except (TypeError, ValueError):
                return None
        return None

    async def set_mode(self, mode: str, balance: float | None = None) -> dict[str, str | float | bool]:
        if mode not in ("demo", "real"):
            mode = DEFAULT_ACCOUNT_MODE
        await cache_set(REDIS_ACCOUNT_MODE_KEY, {"mode": mode})
        if mode == "real" and balance is not None:
            await self.set_real_balance(balance)
        else:
            from app.services.agent_cache import invalidate_agent_llm_cache

            await invalidate_agent_llm_cache()
        return await self.get_status(mode)

    async def set_real_balance(self, balance: float) -> dict[str, str | float | bool]:
        if balance <= 0:
            balance = get_default_real_balance()
        await cache_set(REDIS_REAL_BALANCE_KEY, {"balance": round(balance, 2)})
        from app.services.agent_cache import invalidate_agent_llm_cache

        await invalidate_agent_llm_cache()
        return await self.get_status("real")

    async def get_balance(self) -> float:
        mode = await self.get_mode()
        if mode == "real":
            override = await self.get_real_balance_override()
            return get_balance_for_mode(mode, override)
        return get_balance_for_mode(mode)

    async def get_status(self, mode: str | None = None) -> dict[str, str | float | bool]:
        active = mode or await self.get_mode()
        real_override = await self.get_real_balance_override() if active == "real" else None
        return {
            "mode": active,
            "balance": get_balance_for_mode(active, real_override),
            "label_ar": get_label_for_mode(active),
            "balance_editable": is_balance_editable(active),
        }


account_service = AccountService()
