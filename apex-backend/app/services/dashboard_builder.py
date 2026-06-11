"""Build dashboard asset state with market hours masking."""

from app.core.cache import (
    get_agent_consensus,
    get_kill_switch_status,
    get_latest_price,
    get_latest_regime,
    get_latest_signal,
    get_signal_history,
)
from app.schemas import (
    AgentConsensus,
    DashboardStateSchema,
    KillSwitchStatus,
    KillSwitchStatusSchema,
    RegimeSnapshotSchema,
    TradingSignalSchema,
)
from app.services.market_status_service import build_market_status
from app.services.market_data_store import get_latest_price_from_db, get_latest_regime_from_db
from app.services.account_service import account_service
from app.services.consensus_display import patch_consensus_account_balance


async def build_asset_dashboard_state(symbol: str) -> DashboardStateSchema:
    market_status = await build_market_status(symbol)
    kill_data = await get_kill_switch_status()
    kill = (
        KillSwitchStatusSchema(**kill_data)
        if kill_data
        else KillSwitchStatusSchema(status=KillSwitchStatus.INACTIVE)
    )

    if not market_status.is_open:
        return DashboardStateSchema(
            symbol=symbol,
            kill_switch=kill,
            market_status=market_status,
            regime=None,
            latest_signal=None,
            agent_consensus=None,
            current_price=None,
            signal_history=[],
        )

    regime_data = await get_latest_regime(symbol)
    if not regime_data:
        regime_data = await get_latest_regime_from_db(symbol)

    signal_data = await get_latest_signal(symbol)
    history = await get_signal_history(symbol, 20)
    price_data = await get_latest_price(symbol)
    if not price_data:
        price_data = await get_latest_price_from_db(symbol)
    consensus_data = await get_agent_consensus(symbol)

    consensus = AgentConsensus(**consensus_data) if consensus_data else None
    if consensus:
        live_balance = await account_service.get_balance()
        consensus = patch_consensus_account_balance(consensus, live_balance)
        if not consensus.snr_state_ar:
            from app.services.snr_service import enrich_consensus_with_snr

            consensus = await enrich_consensus_with_snr(consensus, symbol, persist=False)

    return DashboardStateSchema(
        regime=RegimeSnapshotSchema(**regime_data) if regime_data else None,
        latest_signal=TradingSignalSchema(**signal_data) if signal_data else None,
        kill_switch=kill,
        signal_history=[TradingSignalSchema(**s) for s in history],
        current_price=price_data["price"] if price_data else None,
        symbol=symbol,
        agent_consensus=consensus,
        market_status=market_status,
    )
