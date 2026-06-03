"""Demo and Real account configuration."""

from typing import Literal

from app.config import settings

AccountModeType = Literal["demo", "real"]

ACCOUNT_CONFIG: dict[AccountModeType, dict[str, str | float]] = {
    "demo": {
        "balance": 10_000.0,
        "label_ar": "تجريبي",
        "description_ar": "للاختبار فقط — رأس المال 10,000$",
        "balance_editable": False,
    },
    "real": {
        "balance": 100.0,
        "label_ar": "حقيقي",
        "description_ar": "للتداول الحقيقي — رأس المال قابل للتعديل",
        "balance_editable": True,
    },
}

DEFAULT_ACCOUNT_MODE: AccountModeType = "demo"
REDIS_REAL_BALANCE_KEY = "apex:real_balance"


def get_demo_balance() -> float:
    return float(settings.demo_account_balance)


def get_default_real_balance() -> float:
    return float(settings.real_account_balance)


def get_balance_for_mode(mode: str, real_balance_override: float | None = None) -> float:
    if mode == "demo":
        return get_demo_balance()
    if mode == "real":
        if real_balance_override is not None:
            return float(real_balance_override)
        return get_default_real_balance()
    return get_demo_balance()


def get_label_for_mode(mode: str) -> str:
    cfg = ACCOUNT_CONFIG.get(mode)  # type: ignore[arg-type]
    if cfg is None:
        cfg = ACCOUNT_CONFIG[DEFAULT_ACCOUNT_MODE]
    return str(cfg["label_ar"])


def is_balance_editable(mode: str) -> bool:
    cfg = ACCOUNT_CONFIG.get(mode)  # type: ignore[arg-type]
    if cfg is None:
        return False
    return bool(cfg.get("balance_editable", False))

