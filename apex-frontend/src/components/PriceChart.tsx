"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  createChart,
  ColorType,
  CrosshairMode,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type Time,
  type IPriceLine,
} from "lightweight-charts";
import { t } from "@/lib/i18n";
import { CHART_TIMEFRAMES, fetchPriceBars, type ChartTimeframe } from "@/lib/api";
import { formatAssetPrice } from "@/lib/formatPrice";
import { displayPriceHint } from "@/lib/displayPrice";
import type { SNRLevels } from "@/types";

interface Props {
  currentPrice: number | null;
  symbol: string;
  displayPriceSource?: string | null;
}

function toChartTime(iso: string): number {
  return Math.floor(new Date(iso).getTime() / 1000);
}

function normalizeCandles(raw: CandlestickData[]): CandlestickData[] {
  const byTime = new Map<number, CandlestickData>();
  for (const bar of raw) {
    const tKey = bar.time as number;
    byTime.set(tKey, bar);
  }
  return Array.from(byTime.entries())
    .sort(([a], [b]) => a - b)
    .map(([, bar]) => bar);
}

function barBucketSec(timeframe: ChartTimeframe, nowMs = Date.now()): number {
  const sec = Math.floor(nowMs / 1000);
  switch (timeframe) {
    case "M5":
      return Math.floor(sec / 300) * 300;
    case "M15":
      return Math.floor(sec / 900) * 900;
    case "H1":
      return Math.floor(sec / 3600) * 3600;
    case "H4":
      return Math.floor(sec / 14400) * 14400;
    case "D1": {
      const day = new Date(nowMs);
      day.setUTCHours(0, 0, 0, 0);
      return Math.floor(day.getTime() / 1000);
    }
    default:
      return Math.floor(sec / 3600) * 3600;
  }
}

const SUPPORT_COLOR = "#3fb950";
const RESISTANCE_COLOR = "#f85149";
const LIVE_PRICE_COLOR = "#d4a017";

function applyLivePriceLine(
  series: ISeriesApi<"Candlestick">,
  price: number | null,
  existing: IPriceLine | null
): IPriceLine | null {
  if (existing) {
    try {
      series.removePriceLine(existing);
    } catch {
      /* ignore */
    }
  }
  if (price == null) return null;
  return series.createPriceLine({
    price,
    color: LIVE_PRICE_COLOR,
    lineWidth: 2,
    lineStyle: LineStyle.Solid,
    axisLabelVisible: true,
    title: "Live",
  });
}

function applySnrLines(series: ISeriesApi<"Candlestick">, snr: SNRLevels | null) {
  const lines: IPriceLine[] = [];
  if (!snr) return lines;

  const add = (price: number | null, color: string, title: string) => {
    if (price == null) return;
    lines.push(
      series.createPriceLine({
        price,
        color,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title,
      })
    );
  };

  add(snr.support_1, SUPPORT_COLOR, "S1");
  add(snr.support_2, SUPPORT_COLOR, "S2");
  add(snr.support_3, SUPPORT_COLOR, "S3");
  add(snr.resistance_1, RESISTANCE_COLOR, "R1");
  add(snr.resistance_2, RESISTANCE_COLOR, "R2");
  add(snr.resistance_3, RESISTANCE_COLOR, "R3");
  return lines;
}

export default function PriceChart({ currentPrice, symbol, displayPriceSource = null }: Props) {
  const [timeframe, setTimeframe] = useState<ChartTimeframe>("H1");
  const [chartReady, setChartReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const lastBarRef = useRef<CandlestickData | null>(null);
  const snrLinesRef = useRef<IPriceLine[]>([]);
  const livePriceLineRef = useRef<IPriceLine | null>(null);
  const liveUpdatesRef = useRef(true);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#161b22" },
        textColor: "#8b949e",
      },
      grid: {
        vertLines: { color: "#21262d" },
        horzLines: { color: "#21262d" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#30363d" },
      timeScale: { borderColor: "#30363d" },
      width: containerRef.current.clientWidth,
      height: 400,
    });

    const series = chart.addCandlestickSeries({
      upColor: "#00e87a",
      downColor: "#ff3d3d",
      borderUpColor: "#00e87a",
      borderDownColor: "#ff3d3d",
      wickUpColor: "#00e87a",
      wickDownColor: "#ff3d3d",
    });

    chartRef.current = chart;
    seriesRef.current = series;
    setChartReady(true);

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      lastBarRef.current = null;
      snrLinesRef.current = [];
      livePriceLineRef.current = null;
      setChartReady(false);
    };
  }, []);

  const applyBarsToChart = useCallback(
    (candles: CandlestickData[], snr: SNRLevels | null, enableLiveUpdates: boolean) => {
      if (!seriesRef.current || candles.length === 0) return;

      snrLinesRef.current.forEach((line) => {
        try {
          seriesRef.current?.removePriceLine(line);
        } catch {
          /* ignore */
        }
      });
      snrLinesRef.current = [];

      seriesRef.current.setData(candles);
      lastBarRef.current = candles[candles.length - 1] ?? null;
      snrLinesRef.current = applySnrLines(seriesRef.current, snr);
      liveUpdatesRef.current = enableLiveUpdates;
      chartRef.current?.timeScale().fitContent();
    },
    []
  );

  useEffect(() => {
    if (!chartReady || !seriesRef.current || !symbol) return;

    let cancelled = false;
    setLoading(true);

    fetchPriceBars(symbol, 200, timeframe)
      .then((data) => {
        if (cancelled || !seriesRef.current || !data.bars.length) return;
        const candles = normalizeCandles(
          data.bars.map((b) => ({
            time: toChartTime(b.timestamp) as Time,
            open: b.open,
            high: b.high,
            low: b.low,
            close: b.close,
          }))
        );
        try {
          applyBarsToChart(candles, data.snr, data.interval === timeframe);
        } catch {
          /* ignore invalid bar ordering from chart library */
        }
      })
      .catch(() => null)
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [symbol, timeframe, chartReady, applyBarsToChart]);

  useEffect(() => {
    if (!chartReady || !seriesRef.current) return;
    livePriceLineRef.current = applyLivePriceLine(
      seriesRef.current,
      currentPrice,
      livePriceLineRef.current
    );
  }, [currentPrice, chartReady]);

  useEffect(() => {
    if (!liveUpdatesRef.current) return;
    if (!currentPrice || !seriesRef.current || !lastBarRef.current) return;

    const bucketSec = barBucketSec(timeframe);
    const lastTime = lastBarRef.current.time as number;

    try {
      if (bucketSec < lastTime) {
        const bar = { ...lastBarRef.current };
        bar.close = currentPrice;
        bar.high = Math.max(bar.high, currentPrice);
        bar.low = Math.min(bar.low, currentPrice);
        seriesRef.current.update(bar);
        lastBarRef.current = bar;
        return;
      }

      if (bucketSec === lastTime) {
        const bar = { ...lastBarRef.current };
        bar.close = currentPrice;
        bar.high = Math.max(bar.high, currentPrice);
        bar.low = Math.min(bar.low, currentPrice);
        seriesRef.current.update(bar);
        lastBarRef.current = bar;
      } else {
        const newBar: CandlestickData = {
          time: bucketSec as Time,
          open: lastBarRef.current.close,
          high: Math.max(lastBarRef.current.close, currentPrice),
          low: Math.min(lastBarRef.current.close, currentPrice),
          close: currentPrice,
        };
        seriesRef.current.update(newBar);
        lastBarRef.current = newBar;
      }
    } catch {
      /* ignore out-of-order live tick */
    }
  }, [currentPrice, timeframe]);

  return (
    <div className="card col-8">
      <div className="card-title chart-title-row">
        <span>
          {t.livePriceChart} — <span className="mono">{symbol}</span>
        </span>
        <span className="chart-title-controls">
          {currentPrice != null && (
            <span className="chart-live-price-block">
              <span className="chart-live-price-value mono">
                {formatAssetPrice(currentPrice, symbol)}
              </span>
              {displayPriceSource != null && (
                <span className="chart-live-price-hint">{displayPriceHint(displayPriceSource)}</span>
              )}
            </span>
          )}
          <span className="chart-timeframe-group" role="group" aria-label={t.chartTimeframe}>
            {CHART_TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                type="button"
                className={`chart-timeframe-btn${timeframe === tf ? " active" : ""}`}
                aria-pressed={timeframe === tf}
                disabled={loading && timeframe === tf}
                onClick={() => {
                  if (tf !== timeframe) setTimeframe(tf);
                }}
              >
                {tf}
              </button>
            ))}
          </span>
          <span className="chart-snr-legend">
            <span className="snr-legend-item support">S1–S3</span>
            <span className="snr-legend-item resistance">R1–R3</span>
          </span>
        </span>
      </div>
      <div className="chart-wrapper">
        {loading && <div className="chart-loading">{t.loadingChart}</div>}
        <div ref={containerRef} className="chart-container" />
      </div>
    </div>
  );
}
