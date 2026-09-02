from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class SwingSettings:
    lookback_days: int | None
    window: int
    base_weight: float
    half_life_days: float


SWING_SETTINGS = {
    "1h": SwingSettings(90, 3, 1.0, 30.0),
    "1d": SwingSettings(365, 3, 2.0, 90.0),
    "1w": SwingSettings(None, 2, 3.0, 180.0),
}

CANDIDATE_COLUMNS = [
    "price",
    "timestamp_utc",
    "timeframe",
    "origin_kind",
    "candidate_weight",
]


def classic_pivots(high: float, low: float, close: float) -> dict[str, float]:
    """Return classic floor-trader pivot levels for one completed bar."""
    values = (float(high), float(low), float(close))
    high_value, low_value, close_value = values
    if (
        not all(math.isfinite(value) for value in values)
        or high_value < low_value
        or not low_value <= close_value <= high_value
    ):
        raise ValueError("invalid pivot reference high, low, or close")

    pivot = (high_value + low_value + close_value) / 3.0
    spread = high_value - low_value
    return {
        "pivot": pivot,
        "s1": 2.0 * pivot - high_value,
        "s2": pivot - spread,
        "s3": low_value - 2.0 * (high_value - pivot),
        "r1": 2.0 * pivot - low_value,
        "r2": pivot + spread,
        "r3": high_value + 2.0 * (pivot - low_value),
    }


def find_swing_candidates(
    frame: pd.DataFrame,
    timeframe: str,
    analysis_date: str,
) -> pd.DataFrame:
    """Find strict, fully confirmed swing highs and lows before a cutoff."""
    if timeframe not in SWING_SETTINGS:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    if frame.empty:
        return pd.DataFrame(columns=CANDIDATE_COLUMNS)

    settings = SWING_SETTINGS[timeframe]
    cutoff = pd.Timestamp(analysis_date).date()
    result = frame.copy()
    result["timestamp_utc"] = pd.to_datetime(
        result["timestamp_utc"], utc=True
    )
    result["_session_date"] = pd.to_datetime(
        result["session_date"]
    ).dt.date
    result = result.loc[result["_session_date"] <= cutoff]
    if timeframe == "1w" and "is_complete" in result.columns:
        result = result.loc[result["is_complete"].fillna(False).astype(bool)]
    if settings.lookback_days is not None:
        start = (
            pd.Timestamp(cutoff) - pd.Timedelta(days=settings.lookback_days)
        ).date()
        result = result.loc[result["_session_date"] >= start]
    result = result.sort_values("timestamp_utc").reset_index(drop=True)

    lows = pd.to_numeric(result["low"], errors="coerce").to_numpy(float)
    highs = pd.to_numeric(result["high"], errors="coerce").to_numpy(float)
    rows: list[dict[str, object]] = []
    width = settings.window
    for index in range(width, len(result) - width):
        neighbor_indexes = [
            position
            for position in range(index - width, index + width + 1)
            if position != index
        ]
        neighbor_lows = lows[neighbor_indexes]
        neighbor_highs = highs[neighbor_indexes]
        session_date = result.iloc[index]["_session_date"]
        age_days = max((cutoff - session_date).days, 0)
        recency = 0.5 ** (age_days / settings.half_life_days)
        weight = settings.base_weight * recency
        timestamp = result.iloc[index]["timestamp_utc"]
        if (
            np.isfinite(lows[index])
            and np.isfinite(neighbor_lows).all()
            and lows[index] < np.min(neighbor_lows)
        ):
            rows.append(
                {
                    "price": float(lows[index]),
                    "timestamp_utc": timestamp,
                    "timeframe": timeframe,
                    "origin_kind": "swing_low",
                    "candidate_weight": weight,
                }
            )
        if (
            np.isfinite(highs[index])
            and np.isfinite(neighbor_highs).all()
            and highs[index] > np.max(neighbor_highs)
        ):
            rows.append(
                {
                    "price": float(highs[index]),
                    "timestamp_utc": timestamp,
                    "timeframe": timeframe,
                    "origin_kind": "swing_high",
                    "candidate_weight": weight,
                }
            )
    return pd.DataFrame(rows, columns=CANDIDATE_COLUMNS)
