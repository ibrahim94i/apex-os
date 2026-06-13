"use client";



import type { DashboardState } from "@/types";

import { ASSET_LABELS } from "@/types";

import { t } from "@/lib/i18n";

import RegimePanel from "./RegimePanel";

import SignalPanel from "./SignalPanel";

import SignalHistory from "./SignalHistory";

import PriceChart from "./PriceChart";

import ReasoningPanel from "./ReasoningPanel";

import MarketStatusPanel from "./MarketStatusPanel";



interface Props {
  symbol: string;
  state: DashboardState | null;
  /** Hide column heading when asset name is shown in tab bar */
  hideTitle?: boolean;
}



export default function AssetColumn({ symbol, state, hideTitle = false }: Props) {

  const label = ASSET_LABELS[symbol] || symbol;

  const marketStatus = state?.market_status ?? null;

  return (

    <div className="asset-column">

      {!hideTitle && (
        <h2 className="asset-column-title">
          {label} <span className="mono symbol">{symbol}</span>
        </h2>
      )}

      <MarketStatusPanel status={marketStatus} />

      <div className="grid asset-grid">

          <RegimePanel regime={state?.regime ?? null} />

          <SignalPanel
            signal={state?.latest_signal ?? null}
            currentPrice={state?.current_price ?? null}
            displayPrice={state?.display_price ?? null}
            displayPriceSource={state?.display_price_source ?? null}
            symbol={symbol}
            consensus={state?.agent_consensus ?? null}
          />
          <PriceChart
            currentPrice={state?.display_price ?? state?.current_price ?? null}
            symbol={symbol}
          />
          <SignalHistory signals={state?.signal_history ?? []} />
          <ReasoningPanel
            consensus={state?.agent_consensus ?? null}
            regime={state?.regime ?? null}
          />

      </div>

    </div>

  );

}


