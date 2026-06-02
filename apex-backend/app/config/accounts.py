"""Demo and Real account configuration."""

from typing import Literal

AccountModeType = Literal["demo", "real"]

ACCOUNT_CONFIG: dict[AccountModeType, dict[str, str | float]] = {
    "demo": {
        "balance": 10_000.0,
        "label_ar": "تجريبي",
        "description_ar": "للاختبار فقط — رأس المال 10,000$",
    },
    "real": {
        "balance": 100.0,
        "label_ar": "حقيقي",
        "description_ar": "للتداول الحقيقي — رأس المال 100$",
    },
}

DEFAULT_ACCOUNT_MODE: AccountModeType = "demo"


def get_balance_for_mode(mode: str) -> float:
    cfg = ACCOUNT_CONFIG.get(mode)  # type: ignore[arg-type]
    if cfg is None:
        cfg = ACCOUNT_CONFIG[DEFAULT_ACCOUNT_MODE]
    return float(cfg["balance"])


def get_label_for_mode(mode: str) -> str:
    cfg = ACCOUNT_CONFIG.get(mode)  # type: ignore[arg-type]
    if cfg is None:
        cfg = ACCOUNT_CONFIG[DEFAULT_ACCOUNT_MODE]
    return str(cfg["label_ar"])
