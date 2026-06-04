"""Candlestick pattern detection — pandas rules + pandas-ta Doji when available."""

from __future__ import annotations

from typing import Literal

import pandas as pd

from app.engines.indicator_engine import OHLCVBar
from app.schemas.agent import CandlestickPatternSchema

PatternSignal = Literal["bullish", "bearish", "neutral"]

_MIN_BARS = 5
_DOJI_BODY_RATIO = 0.10
_STAR_BODY_RATIO = 0.30
_LARGE_BODY_RATIO = 0.55


def _candle_parts(o: float, h: float, l: float, c: float) -> tuple[float, float, float, float, float]:
    body = abs(c - o)
    rng = h - l
    if rng <= 0:
        return body, 0.0, 0.0, rng, 0.0
    upper = h - max(o, c)
    lower = min(o, c) - l
    return body, upper, lower, rng, body / rng


def _is_bullish(o: float, c: float) -> bool:
    return c >= o


def _is_bearish(o: float, c: float) -> bool:
    return c < o


class CandlestickPatternEngine:
    """Detect key reversal/continuation candlestick patterns on the latest H1 bars."""

    def detect(self, bars: list[OHLCVBar]) -> list[CandlestickPatternSchema]:
        if len(bars) < _MIN_BARS:
            return []

        df = pd.DataFrame(
            {
                "open": [b.open for b in bars],
                "high": [b.high for b in bars],
                "low": [b.low for b in bars],
                "close": [b.close for b in bars],
            }
        )

        found: list[CandlestickPatternSchema] = []
        found.extend(self._detect_with_pandas_ta(df))
        found.extend(self._detect_with_rules(df))

        return self._dedupe(found)

    def _detect_with_pandas_ta(self, df: pd.DataFrame) -> list[CandlestickPatternSchema]:
        out: list[CandlestickPatternSchema] = []
        try:
            import pandas_ta as ta
        except ImportError:
            return out

        try:
            doji = ta.cdl_doji(df["open"], df["high"], df["low"], df["close"])
            if doji is not None and len(doji) and float(doji.iloc[-1]) != 0:
                out.append(
                    CandlestickPatternSchema(
                        pattern="DOJI",
                        name_ar="دوجي",
                        signal="neutral",
                        bar_offset=0,
                        strength=1.0,
                        source="pandas-ta",
                    )
                )
        except Exception:
            pass

        try:
            import talib

            talib_checks: list[tuple[str, str, str, PatternSignal | None]] = [
                ("CDLDOJI", "DOJI", "دوجي", "neutral"),
                ("CDLHAMMER", "HAMMER", "مطرقة", "bullish"),
                ("CDLMORNINGSTAR", "MORNING_STAR", "نجمة الصباح", "bullish"),
                ("CDLEVENINGSTAR", "EVENING_STAR", "نجمة المساء", "bearish"),
                ("CDLSHOOTINGSTAR", "SHOOTING_STAR", "نجم هابط", "bearish"),
                ("CDLENGULFING", "ENGULFING", "ابتلاع", None),
            ]
            for func_name, pattern_id, name_ar, fixed_signal in talib_checks:
                func = getattr(talib, func_name, None)
                if func is None:
                    continue
                series = func(
                    df["open"].values,
                    df["high"].values,
                    df["low"].values,
                    df["close"].values,
                )
                val = float(series[-1])
                if val == 0:
                    continue
                if pattern_id == "ENGULFING":
                    if val > 0:
                        out.append(
                            CandlestickPatternSchema(
                                pattern="BULLISH_ENGULFING",
                                name_ar="ابتلاع صعودي",
                                signal="bullish",
                                bar_offset=0,
                                strength=1.0,
                                source="TA-Lib",
                            )
                        )
                    else:
                        out.append(
                            CandlestickPatternSchema(
                                pattern="BEARISH_ENGULFING",
                                name_ar="ابتلاع هبوطي",
                                signal="bearish",
                                bar_offset=0,
                                strength=1.0,
                                source="TA-Lib",
                            )
                        )
                    continue
                signal: PatternSignal = fixed_signal or "neutral"
                if val < 0 and signal == "bullish":
                    signal = "bearish"
                elif val < 0 and signal == "bearish":
                    signal = "bullish"
                out.append(
                    CandlestickPatternSchema(
                        pattern=pattern_id,
                        name_ar=name_ar,
                        signal=signal,
                        bar_offset=0,
                        strength=min(abs(val) / 100.0, 1.0),
                        source="TA-Lib",
                    )
                )
        except ImportError:
            pass

        return out

    def _detect_with_rules(self, df: pd.DataFrame) -> list[CandlestickPatternSchema]:
        out: list[CandlestickPatternSchema] = []
        n = len(df)

        o, h, l, c = (
            float(df["open"].iloc[-1]),
            float(df["high"].iloc[-1]),
            float(df["low"].iloc[-1]),
            float(df["close"].iloc[-1]),
        )
        body, upper, lower, rng, body_ratio = _candle_parts(o, h, l, c)

        if rng > 0 and body_ratio <= _DOJI_BODY_RATIO:
            out.append(
                CandlestickPatternSchema(
                    pattern="DOJI",
                    name_ar="دوجي",
                    signal="neutral",
                    bar_offset=0,
                    strength=1.0 - body_ratio / _DOJI_BODY_RATIO,
                    source="pandas",
                )
            )
        elif body > 0 and lower >= 2 * body and upper <= body * 0.5:
            out.append(
                CandlestickPatternSchema(
                    pattern="HAMMER",
                    name_ar="مطرقة",
                    signal="bullish",
                    bar_offset=0,
                    strength=min(lower / (body * 3), 1.0),
                    source="pandas",
                )
            )

        elif body > 0 and upper >= 2 * body and lower <= body * 0.5:
            out.append(
                CandlestickPatternSchema(
                    pattern="SHOOTING_STAR",
                    name_ar="نجم هابط",
                    signal="bearish",
                    bar_offset=0,
                    strength=min(upper / (body * 3), 1.0),
                    source="pandas",
                )
            )

        if n >= 2:
            o1, c1 = float(df["open"].iloc[-2]), float(df["close"].iloc[-2])
            o2, c2 = o, c
            b1, _, _, _, _ = _candle_parts(o1, float(df["high"].iloc[-2]), float(df["low"].iloc[-2]), c1)
            b2 = body
            if b1 > 0 and b2 > 0:
                if _is_bearish(o1, c1) and _is_bullish(o2, c2) and o2 <= c1 and c2 >= o1:
                    out.append(
                        CandlestickPatternSchema(
                            pattern="BULLISH_ENGULFING",
                            name_ar="ابتلاع صعودي",
                            signal="bullish",
                            bar_offset=0,
                            strength=min(b2 / b1, 1.0),
                            source="pandas",
                        )
                    )
                if _is_bullish(o1, c1) and _is_bearish(o2, c2) and o2 >= c1 and c2 <= o1:
                    out.append(
                        CandlestickPatternSchema(
                            pattern="BEARISH_ENGULFING",
                            name_ar="ابتلاع هبوطي",
                            signal="bearish",
                            bar_offset=0,
                            strength=min(b2 / b1, 1.0),
                            source="pandas",
                        )
                    )

        if n >= 3:
            if self._is_morning_star(df, -3, -2, -1):
                out.append(
                    CandlestickPatternSchema(
                        pattern="MORNING_STAR",
                        name_ar="نجمة الصباح",
                        signal="bullish",
                        bar_offset=0,
                        strength=0.85,
                        source="pandas",
                    )
                )
            elif self._is_evening_star(df, -3, -2, -1):
                out.append(
                    CandlestickPatternSchema(
                        pattern="EVENING_STAR",
                        name_ar="نجمة المساء",
                        signal="bearish",
                        bar_offset=0,
                        strength=0.85,
                        source="pandas",
                    )
                )

        return out

    @staticmethod
    def _is_morning_star(df: pd.DataFrame, i1: int, i2: int, i3: int) -> bool:
        o1, h1, l1, c1 = df.iloc[i1][["open", "high", "low", "close"]]
        o2, h2, l2, c2 = df.iloc[i2][["open", "high", "low", "close"]]
        o3, h3, l3, c3 = df.iloc[i3][["open", "high", "low", "close"]]
        b1, _, _, r1, br1 = _candle_parts(o1, h1, l1, c1)
        b2, _, _, r2, br2 = _candle_parts(o2, h2, l2, c2)
        b3, _, _, r3, br3 = _candle_parts(o3, h3, l3, c3)
        if r1 <= 0 or r2 <= 0 or r3 <= 0:
            return False
        if not (_is_bearish(o1, c1) and br1 >= _LARGE_BODY_RATIO):
            return False
        if br2 > _STAR_BODY_RATIO:
            return False
        mid = (o1 + c1) / 2
        return _is_bullish(o3, c3) and br3 >= _LARGE_BODY_RATIO and c3 > mid

    @staticmethod
    def _is_evening_star(df: pd.DataFrame, i1: int, i2: int, i3: int) -> bool:
        o1, h1, l1, c1 = df.iloc[i1][["open", "high", "low", "close"]]
        o2, h2, l2, c2 = df.iloc[i2][["open", "high", "low", "close"]]
        o3, h3, l3, c3 = df.iloc[i3][["open", "high", "low", "close"]]
        b1, _, _, r1, br1 = _candle_parts(o1, h1, l1, c1)
        b2, _, _, r2, br2 = _candle_parts(o2, h2, l2, c2)
        b3, _, _, r3, br3 = _candle_parts(o3, h3, l3, c3)
        if r1 <= 0 or r2 <= 0 or r3 <= 0:
            return False
        if not (_is_bullish(o1, c1) and br1 >= _LARGE_BODY_RATIO):
            return False
        if br2 > _STAR_BODY_RATIO:
            return False
        mid = (o1 + c1) / 2
        return _is_bearish(o3, c3) and br3 >= _LARGE_BODY_RATIO and c3 < mid

    @staticmethod
    def _dedupe(patterns: list[CandlestickPatternSchema]) -> list[CandlestickPatternSchema]:
        seen: set[tuple[str, int]] = set()
        out: list[CandlestickPatternSchema] = []
        for p in patterns:
            key = (p.pattern, p.bar_offset)
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
        return out


candlestick_engine = CandlestickPatternEngine()
