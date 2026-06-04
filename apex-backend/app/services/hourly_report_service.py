"""Hourly dashboard report generation."""

from __future__ import annotations

from datetime import datetime, timezone

from app.config.assets import ACTIVE_SYMBOLS, ASSETS
from app.core.cache import get_agent_consensus, get_latest_regime, get_latest_signal, get_hourly_report, set_hourly_report
from app.schemas.market import HourlyReportAssetSchema, HourlyReportSchema
from app.services.market_status_service import build_market_status
from app.websocket.manager import broadcaster

REGIME_AR: dict[str, str] = {
    "TRENDING_UP": "اتجاه صاعد",
    "TRENDING_DOWN": "اتجاه هابط",
    "RANGING": "سوق جانبي",
    "VOLATILE": "تذبذب عالي",
    "UNKNOWN": "غير معروف",
}

DIRECTION_AR: dict[str, str] = {
    "LONG": "شراء",
    "SHORT": "بيع",
    "NEUTRAL": "محايد",
}


async def build_hourly_report(at: datetime | None = None) -> HourlyReportSchema:
    now = at or datetime.now(timezone.utc)
    entries: list[HourlyReportAssetSchema] = []

    for symbol in ACTIVE_SYMBOLS:
        asset = ASSETS[symbol]
        status = await build_market_status(symbol, now)
        regime_data = await get_latest_regime(symbol)
        signal_data = await get_latest_signal(symbol)
        consensus_data = await get_agent_consensus(symbol)

        if status.is_open and regime_data:
            direction_label = REGIME_AR.get(regime_data.get("regime", "UNKNOWN"), "غير معروف")
        else:
            direction_label = "السوق مغلق"

        last_dir = None
        last_conf_pct = None
        if signal_data:
            last_dir = DIRECTION_AR.get(signal_data.get("direction", ""), signal_data.get("direction"))
            last_conf_pct = round(float(signal_data.get("confidence", 0)) * 100, 1)

        agent_rec = None
        agent_conf_pct = None
        if status.is_open and consensus_data:
            agent_rec = DIRECTION_AR.get(
                consensus_data.get("final_direction", ""),
                consensus_data.get("final_direction"),
            )
            agent_conf_pct = round(float(consensus_data.get("final_confidence", 0)) * 100, 1)

        market_state = "مفتوح" if status.is_open else "مغلق"
        summary = (
            f"{asset.display_name_ar}: السوق {market_state} | "
            f"الاتجاه: {direction_label}"
        )
        if last_dir:
            summary += f" | آخر إشارة: {last_dir}"
            if last_conf_pct is not None:
                summary += f" ({last_conf_pct}%)"
        if agent_rec:
            summary += f" | توصية الوكلاء: {agent_rec}"
            if agent_conf_pct is not None:
                summary += f" ({agent_conf_pct}%)"

        entries.append(
            HourlyReportAssetSchema(
                symbol=symbol,
                display_name_ar=asset.display_name_ar,
                is_market_open=status.is_open,
                market_direction=direction_label,
                last_signal_direction=last_dir,
                last_signal_confidence_pct=last_conf_pct,
                agent_recommendation=agent_rec,
                agent_confidence_pct=agent_conf_pct,
                summary_ar=summary,
            )
        )

    return HourlyReportSchema(timestamp=now, assets=entries)


async def publish_hourly_report() -> HourlyReportSchema:
    report = await build_hourly_report()
    data = report.model_dump(mode="json")
    await set_hourly_report(data)
    await broadcaster.broadcast_hourly_report(data)
    return report
