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

CLUSTER_COLUMNS = [
    "level_value",
    "touch_count",
    "strength_score",
    "contributing_timeframes",
    "last_touch_utc",
    "swing_low_count",
    "swing_high_count",
    "cluster_tolerance",
]

TIMEFRAME_ORDER = {"1h": 0, "1d": 1, "1w": 2}


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


def clustering_tolerance(current_price: float, atr_14: float | None) -> float:
    """Return a price- and volatility-scaled clustering radius."""
    price = float(current_price)
    if not math.isfinite(price) or price <= 0:
        raise ValueError("current price must be finite and positive")
    try:
        atr = float(atr_14) if atr_14 is not None else math.nan
    except (TypeError, ValueError):
        atr = math.nan
    atr_component = atr * 0.25 if math.isfinite(atr) and atr >= 0 else 0.0
    return max(price * 0.005, atr_component)


def cluster_candidates(
    candidates: pd.DataFrame,
    current_price: float,
    atr_14: float | None,
) -> pd.DataFrame:
    """Cluster ascending swing prices using a rolling weighted centroid."""
    tolerance = clustering_tolerance(current_price, atr_14)
    if candidates.empty:
        return pd.DataFrame(columns=CLUSTER_COLUMNS)
    ordered = candidates.copy()
    ordered["timestamp_utc"] = pd.to_datetime(
        ordered["timestamp_utc"], utc=True
    )
    ordered = ordered.sort_values(
        ["price", "timestamp_utc", "timeframe", "origin_kind"]
    ).reset_index(drop=True)
    clusters: list[dict[str, object]] = []
    for record in ordered.to_dict("records"):
        price = float(record["price"])
        weight = float(record["candidate_weight"])
        if not math.isfinite(price) or not math.isfinite(weight) or weight <= 0:
            continue
        if not clusters:
            clusters.append(
                {
                    "weighted_price_sum": price * weight,
                    "weight_sum": weight,
                    "members": [record],
                }
            )
            continue
        current = clusters[-1]
        centroid = float(current["weighted_price_sum"]) / float(
            current["weight_sum"]
        )
        if abs(price - centroid) > tolerance:
            clusters.append(
                {
                    "weighted_price_sum": price * weight,
                    "weight_sum": weight,
                    "members": [record],
                }
            )
            continue
        current["weighted_price_sum"] = (
            float(current["weighted_price_sum"]) + price * weight
        )
        current["weight_sum"] = float(current["weight_sum"]) + weight
        members = current["members"]
        if not isinstance(members, list):
            raise TypeError("cluster members must be a list")
        members.append(record)

    rows: list[dict[str, object]] = []
    for cluster in clusters:
        members = cluster["members"]
        if not isinstance(members, list):
            raise TypeError("cluster members must be a list")
        timeframes = sorted(
            {str(member["timeframe"]) for member in members},
            key=TIMEFRAME_ORDER.__getitem__,
        )
        rows.append(
            {
                "level_value": float(cluster["weighted_price_sum"])
                / float(cluster["weight_sum"]),
                "touch_count": len(members),
                "strength_score": float(cluster["weight_sum"]),
                "contributing_timeframes": "|".join(timeframes),
                "last_touch_utc": max(
                    member["timestamp_utc"] for member in members
                ),
                "swing_low_count": sum(
                    member["origin_kind"] == "swing_low" for member in members
                ),
                "swing_high_count": sum(
                    member["origin_kind"] == "swing_high" for member in members
                ),
                "cluster_tolerance": tolerance,
            }
        )
    return pd.DataFrame(rows, columns=CLUSTER_COLUMNS).sort_values(
        "level_value"
    ).reset_index(drop=True)


def select_nearest_levels(
    clusters: pd.DataFrame,
    current_price: float,
    count: int = 3,
) -> pd.DataFrame:
    """Classify clusters around price and return nearest levels on each side."""
    if count < 1 or count > 10:
        raise ValueError("level count must be between 1 and 10")
    output_columns = [*CLUSTER_COLUMNS, "side", "rank", "distance_pct"]
    if clusters.empty:
        return pd.DataFrame(columns=output_columns)
    support = (
        clusters.loc[clusters["level_value"] < current_price]
        .sort_values("level_value", ascending=False)
        .head(count)
        .copy()
    )
    resistance = (
        clusters.loc[clusters["level_value"] > current_price]
        .sort_values("level_value")
        .head(count)
        .copy()
    )
    support["side"] = "support"
    resistance["side"] = "resistance"
    support["rank"] = range(1, len(support) + 1)
    resistance["rank"] = range(1, len(resistance) + 1)
    result = pd.concat([support, resistance], ignore_index=True)
    result["distance_pct"] = result["level_value"] / float(current_price) - 1.0
    return result[output_columns]
