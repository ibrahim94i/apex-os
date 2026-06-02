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

}



export default function AssetColumn({ symbol, state }: Props) {

  const label = ASSET_LABELS[symbol] || symbol;

  const marketStatus = state?.market_status ?? null;

  const isClosed = marketStatus?.is_open === false;



  return (

    <div className="asset-column">

      <h2 className="asset-column-title">

        {label} <span className="mono symbol">{symbol}</span>

      </h2>

      <MarketStatusPanel status={marketStatus} />

      {isClosed ? (

        <div className="market-closed-overlay card col-12">

          <div className="market-closed-icon">🔒</div>

          <h3>{t.marketClosed}</h3>

          <p>{marketStatus?.schedule_ar}</p>

          <p className="market-closed-hint">{t.marketClosedHint}</p>

        </div>

      ) : (

        <div className="grid asset-grid">

          <RegimePanel regime={state?.regime ?? null} />

          <SignalPanel

            signal={state?.latest_signal ?? null}

            currentPrice={state?.current_price ?? null}

          />

          <PriceChart

            currentPrice={state?.current_price ?? null}

            symbol={symbol}

          />

          <SignalHistory signals={state?.signal_history ?? []} />

          <ReasoningPanel consensus={state?.agent_consensus ?? null} />

        </div>

      )}

    </div>

  );

}


