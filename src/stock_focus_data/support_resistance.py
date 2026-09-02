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

LONG_COLUMNS = [
    "symbol",
    "analysis_date",
    "current_price",
    "method",
    "reference_timeframe",
    "level_name",
    "side",
    "rank",
    "level_value",
    "distance_pct",
    "touch_count",
    "strength_score",
    "contributing_timeframes",
    "last_touch_utc",
    "reference_period_end",
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


def compact_columns(levels: int = 3) -> list[str]:
    """Return the stable wide-output schema for a requested level count."""
    if levels < 1 or levels > 10:
        raise ValueError("level count must be between 1 and 10")
    columns = [
        "symbol",
        "analysis_date",
        "current_price",
        "price_timestamp_utc",
        "calculation_status",
        "warning",
    ]
    for side in ("support", "resistance"):
        for rank in range(1, levels + 1):
            prefix = f"mt_{side}_{rank}"
            columns.extend(
                [
                    prefix,
                    f"{prefix}_distance_pct",
                    f"{prefix}_touch_count",
                    f"{prefix}_strength_score",
                    f"{prefix}_timeframes",
                    f"{prefix}_last_touch_utc",
                ]
            )
    columns.extend(
        [
            "daily_reference_date",
            "daily_pivot",
            "daily_s1",
            "daily_s2",
            "daily_s3",
            "daily_r1",
            "daily_r2",
            "daily_r3",
            "weekly_reference_period_end",
            "weekly_pivot",
            "weekly_s1",
            "weekly_s2",
            "weekly_s3",
            "weekly_r1",
            "weekly_r2",
            "weekly_r3",
        ]
    )
    return columns


def _classic_long_rows(
    symbol: str,
    analysis_date: str,
    current_price: float,
    timeframe: str,
    reference_period_end: str,
    pivots: dict[str, float],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for name in ("pivot", "s1", "s2", "s3", "r1", "r2", "r3"):
        side = (
            "pivot"
            if name == "pivot"
            else "support"
            if name.startswith("s")
            else "resistance"
        )
        rank = 0 if name == "pivot" else int(name[1])
        value = pivots[name]
        rows.append(
            {
                "symbol": symbol,
                "analysis_date": analysis_date,
                "current_price": current_price,
                "method": "classic",
                "reference_timeframe": timeframe,
                "level_name": name.upper() if name != "pivot" else "P",
                "side": side,
                "rank": rank,
                "level_value": value,
                "distance_pct": value / current_price - 1.0,
                "touch_count": pd.NA,
                "strength_score": pd.NA,
                "contributing_timeframes": pd.NA,
                "last_touch_utc": pd.NaT,
                "reference_period_end": reference_period_end,
            }
        )
    return rows


def _completed_weekly_rows(
    weekly: pd.DataFrame,
    analysis_date: str,
) -> pd.DataFrame:
    if weekly.empty or "is_complete" not in weekly.columns:
        return weekly.iloc[0:0].copy()
    completed = weekly.loc[
        (weekly["session_date"].astype(str) <= analysis_date)
        & weekly["is_complete"].fillna(False).astype(bool)
    ].copy()
    if not completed.empty:
        completed["timestamp_utc"] = pd.to_datetime(
            completed["timestamp_utc"], utc=True
        )
    return completed.sort_values("timestamp_utc")


def calculate_symbol_levels(
    symbol: str,
    hourly: pd.DataFrame,
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    analysis_date: str,
    levels: int = 3,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Calculate compact and long-form levels for one symbol."""
    if levels < 1 or levels > 10:
        raise ValueError("level count must be between 1 and 10")
    target = daily.loc[daily["session_date"].astype(str) == analysis_date]
    if len(target) != 1:
        raise ValueError(f"{symbol} requires one daily row on {analysis_date}")
    daily_row = target.iloc[0]
    current_price = float(daily_row["close"])
    if not math.isfinite(current_price) or current_price <= 0:
        raise ValueError(f"{symbol} current price must be finite and positive")
    daily_pivots = classic_pivots(
        float(daily_row["high"]),
        float(daily_row["low"]),
        current_price,
    )
    atr_value = daily_row.get("atr_14", math.nan)

    warnings: list[str] = []
    if hourly.empty:
        warnings.append("missing_hourly")
    completed_weekly = _completed_weekly_rows(weekly, analysis_date)
    if completed_weekly.empty:
        warnings.append("missing_completed_weekly")

    candidate_frames = [
        find_swing_candidates(hourly, "1h", analysis_date),
        find_swing_candidates(daily, "1d", analysis_date),
        find_swing_candidates(completed_weekly, "1w", analysis_date),
    ]
    candidates = pd.concat(candidate_frames, ignore_index=True)
    clusters = cluster_candidates(candidates, current_price, atr_value)
    selected = select_nearest_levels(clusters, current_price, levels)

    compact: dict[str, object] = {
        column: pd.NA for column in compact_columns(levels)
    }
    compact.update(
        {
            "symbol": symbol,
            "analysis_date": analysis_date,
            "current_price": current_price,
            "price_timestamp_utc": pd.to_datetime(
                daily_row["timestamp_utc"], utc=True
            ),
            "calculation_status": "partial" if warnings else "complete",
            "warning": "|".join(warnings),
            "daily_reference_date": analysis_date,
        }
    )
    for name, value in daily_pivots.items():
        compact[f"daily_{name}"] = value

    long_rows = _classic_long_rows(
        symbol,
        analysis_date,
        current_price,
        "1d",
        analysis_date,
        daily_pivots,
    )
    if not completed_weekly.empty:
        weekly_row = completed_weekly.iloc[-1]
        weekly_reference = str(weekly_row["session_date"])
        weekly_pivots = classic_pivots(
            float(weekly_row["high"]),
            float(weekly_row["low"]),
            float(weekly_row["close"]),
        )
        compact["weekly_reference_period_end"] = weekly_reference
        for name, value in weekly_pivots.items():
            compact[f"weekly_{name}"] = value
        long_rows.extend(
            _classic_long_rows(
                symbol,
                analysis_date,
                current_price,
                "1w",
                weekly_reference,
                weekly_pivots,
            )
        )

    for record in selected.to_dict("records"):
        side = str(record["side"])
        rank = int(record["rank"])
        prefix = f"mt_{side}_{rank}"
        compact[prefix] = record["level_value"]
        compact[f"{prefix}_distance_pct"] = record["distance_pct"]
        compact[f"{prefix}_touch_count"] = record["touch_count"]
        compact[f"{prefix}_strength_score"] = record["strength_score"]
        compact[f"{prefix}_timeframes"] = record["contributing_timeframes"]
        compact[f"{prefix}_last_touch_utc"] = record["last_touch_utc"]
        long_rows.append(
            {
                "symbol": symbol,
                "analysis_date": analysis_date,
                "current_price": current_price,
                "method": "multi_timeframe",
                "reference_timeframe": "multi",
                "level_name": (
                    "S" if side == "support" else "R"
                ) + str(rank),
                "side": side,
                "rank": rank,
                "level_value": record["level_value"],
                "distance_pct": record["distance_pct"],
                "touch_count": record["touch_count"],
                "strength_score": record["strength_score"],
                "contributing_timeframes": record[
                    "contributing_timeframes"
                ],
                "last_touch_utc": record["last_touch_utc"],
                "reference_period_end": pd.NA,
            }
        )
    ordered_compact = {
        column: compact[column] for column in compact_columns(levels)
    }
    return ordered_compact, long_rows
