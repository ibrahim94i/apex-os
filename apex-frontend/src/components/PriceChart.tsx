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

interface Props {
  currentPrice: number | null;
  symbol: string;
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
    };
  }, []);

  useEffect(() => {
    if (!currentPrice || !seriesRef.current) return;

    const nowSec = Math.floor(Date.now() / 1000);
    const minute = (Math.floor(nowSec / 60) * 60) as Time;

    if (lastBarRef.current && lastBarRef.current.time === minute) {
      const bar = lastBarRef.current;
      bar.close = currentPrice;
      bar.high = Math.max(bar.high, currentPrice);
      bar.low = Math.min(bar.low, currentPrice);
      seriesRef.current.update(bar);
    } else {
      const newBar: CandlestickData = {
        time: minute,
        open: currentPrice,
        high: currentPrice,
        low: currentPrice,
        close: currentPrice,
      };
      seriesRef.current.update(newBar);
      lastBarRef.current = newBar;
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
