"""Technical indicator computation engine."""

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from app.schemas import IndicatorSnapshotSchema


@dataclass
class OHLCVBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class IndicatorEngine:
    """Computes RSI, MACD, EMA, ATR, Bollinger Bands, ADX from OHLCV bars."""

    def __init__(self, min_bars: int = 200) -> None:
        self.min_bars = min_bars

    def _to_dataframe(self, bars: list[OHLCVBar]) -> pd.DataFrame:
        data = {
            "timestamp": [b.timestamp for b in bars],
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "volume": [b.volume for b in bars],
        }
        return pd.DataFrame(data)

    @staticmethod
    def _ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        prev_close = close.shift(1)
        tr = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    @staticmethod
    def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

        tr = pd.concat(
            [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
            axis=1,
        ).max(axis=1)

        atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        plus_di = 100 * (plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr)
        minus_di = 100 * (minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr)
        dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
        return dx.ewm(alpha=1 / period, adjust=False).mean()

    def compute(self, bars: list[OHLCVBar], symbol: str) -> IndicatorSnapshotSchema | None:
        if len(bars) < self.min_bars:
            return None

        df = self._to_dataframe(bars)
        close = df["close"]
        high = df["high"]
        low = df["low"]

        ema_9 = self._ema(close, 9)
        ema_21 = self._ema(close, 21)
        ema_50 = self._ema(close, 50)
        ema_200 = self._ema(close, 200)
        rsi = self._rsi(close, 14)
        atr = self._atr(high, low, close, 14)
        atr_avg_20 = float(atr.dropna().tail(20).mean()) if len(atr.dropna()) >= 20 else None
        adx = self._adx(high, low, close, 14)

        macd_line = self._ema(close, 12) - self._ema(close, 26)
        macd_signal = self._ema(macd_line, 9)
        macd_histogram = macd_line - macd_signal

        bb_middle = close.rolling(window=20).mean()
        bb_std = close.rolling(window=20).std()
        bb_upper = bb_middle + 2 * bb_std
        bb_lower = bb_middle - 2 * bb_std

        idx = -1
        return IndicatorSnapshotSchema(
            symbol=symbol,
            timestamp=bars[-1].timestamp,
            rsi=float(rsi.iloc[idx]) if not pd.isna(rsi.iloc[idx]) else None,
            macd=float(macd_line.iloc[idx]) if not pd.isna(macd_line.iloc[idx]) else None,
            macd_signal=float(macd_signal.iloc[idx]) if not pd.isna(macd_signal.iloc[idx]) else None,
            macd_histogram=float(macd_histogram.iloc[idx]) if not pd.isna(macd_histogram.iloc[idx]) else None,
            ema_9=float(ema_9.iloc[idx]) if not pd.isna(ema_9.iloc[idx]) else None,
            ema_21=float(ema_21.iloc[idx]) if not pd.isna(ema_21.iloc[idx]) else None,
            ema_50=float(ema_50.iloc[idx]) if not pd.isna(ema_50.iloc[idx]) else None,
            ema_200=float(ema_200.iloc[idx]) if not pd.isna(ema_200.iloc[idx]) else None,
            atr=float(atr.iloc[idx]) if not pd.isna(atr.iloc[idx]) else None,
            atr_avg_20=atr_avg_20,
            bb_upper=float(bb_upper.iloc[idx]) if not pd.isna(bb_upper.iloc[idx]) else None,
            bb_middle=float(bb_middle.iloc[idx]) if not pd.isna(bb_middle.iloc[idx]) else None,
            bb_lower=float(bb_lower.iloc[idx]) if not pd.isna(bb_lower.iloc[idx]) else None,
            adx=float(adx.iloc[idx]) if not pd.isna(adx.iloc[idx]) else None,
        )
