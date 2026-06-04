"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type Time,
} from "lightweight-charts";
import { t } from "@/lib/i18n";
import { fetchPriceBars } from "@/lib/api";

interface Props {
  currentPrice: number | null;
  symbol: string;
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

export default function PriceChart({ currentPrice, symbol }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const lastBarRef = useRef<CandlestickData | null>(null);

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
    };
  }, []);

  useEffect(() => {
    if (!seriesRef.current || !symbol) return;

    let cancelled = false;
    fetchPriceBars(symbol)
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
          seriesRef.current.setData(candles);
          lastBarRef.current = candles[candles.length - 1] ?? null;
          chartRef.current?.timeScale().fitContent();
        } catch {
          /* ignore invalid bar ordering from chart library */
        }
      })
      .catch(() => null);

    return () => {
      cancelled = true;
    };
  }, [symbol]);

  useEffect(() => {
    if (!currentPrice || !seriesRef.current || !lastBarRef.current) return;

    const hourSec = Math.floor(Date.now() / 3600000) * 3600;
    const lastTime = lastBarRef.current.time as number;

    // lightweight-charts throws if update time is older than the last bar
    if (hourSec < lastTime) return;

    try {
      if (hourSec === lastTime) {
        const bar = { ...lastBarRef.current };
        bar.close = currentPrice;
        bar.high = Math.max(bar.high, currentPrice);
        bar.low = Math.min(bar.low, currentPrice);
        seriesRef.current.update(bar);
        lastBarRef.current = bar;
      } else {
        const newBar: CandlestickData = {
          time: hourSec as Time,
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
  }, [currentPrice]);

  return (
    <div className="card col-8">
      <div className="card-title">
        {t.livePriceChart} — <span className="mono">{symbol}</span>
      </div>
      <div ref={containerRef} className="chart-container" />
    </div>
  );
}
