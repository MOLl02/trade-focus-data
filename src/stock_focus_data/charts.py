from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class ChartHistory:
    analysis_date: str
    overview: pd.DataFrame
    zoom: pd.DataFrame
    candle_min: float
    candle_max: float


def select_chart_history(
    daily: pd.DataFrame,
    analysis_date: str,
) -> ChartHistory:
    required = {
        "timestamp_utc",
        "session_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }
    missing = sorted(required.difference(daily.columns))
    if missing:
        raise ValueError(f"daily chart history missing columns: {missing}")
    cutoff = pd.Timestamp(analysis_date).normalize()
    frame = daily.copy()
    frame["timestamp_utc"] = pd.to_datetime(
        frame["timestamp_utc"], utc=True
    )
    frame["_chart_session"] = pd.to_datetime(
        frame["session_date"]
    ).dt.normalize()
    frame = frame.loc[frame["_chart_session"] <= cutoff]
    frame = frame.sort_values("timestamp_utc").reset_index(drop=True)
    if frame.empty or not frame["_chart_session"].eq(cutoff).any():
        raise ValueError(
            f"daily chart history lacks analysis date {analysis_date}"
        )

    overview_start = cutoff - pd.DateOffset(years=2)
    zoom_start = cutoff - pd.DateOffset(months=6)
    overview = frame.loc[frame["_chart_session"] >= overview_start].copy()
    zoom = frame.loc[frame["_chart_session"] >= zoom_start].copy()
    raw_min = float(zoom["low"].min())
    raw_max = float(zoom["high"].max())
    if not math.isfinite(raw_min) or not math.isfinite(raw_max):
        raise ValueError("zoom history contains non-finite high or low")
    if raw_min <= 0 or raw_max < raw_min:
        raise ValueError("zoom history contains invalid high or low")
    span = raw_max - raw_min
    margin = max(
        span * 0.03,
        max(abs(raw_min), abs(raw_max)) * 0.005,
        0.01,
    )
    return ChartHistory(
        analysis_date=pd.Timestamp(analysis_date).date().isoformat(),
        overview=overview.drop(columns="_chart_session").reset_index(
            drop=True
        ),
        zoom=zoom.drop(columns="_chart_session").reset_index(drop=True),
        candle_min=raw_min - margin,
        candle_max=raw_max + margin,
    )


def mark_drawn_levels(
    levels: pd.DataFrame,
    candle_min: float,
    candle_max: float,
) -> pd.DataFrame:
    if candle_min >= candle_max:
        raise ValueError("candle range must increase")
    required = {"method", "level_value"}
    missing = sorted(required.difference(levels.columns))
    if missing:
        raise ValueError(f"level table missing columns: {missing}")
    result = levels.copy()
    values = pd.to_numeric(result["level_value"], errors="coerce")
    if not np.isfinite(values).all():
        raise ValueError("level table contains non-finite values")
    structural = result["method"].eq("multi_timeframe")
    classic = result["method"].eq("classic")
    if not (structural | classic).all():
        raise ValueError("level table contains an unsupported method")
    result["drawn_on_chart"] = structural | (
        classic
        & values.between(candle_min, candle_max, inclusive="both")
    )
    return result
