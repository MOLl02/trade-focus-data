import numpy as np
import pandas as pd
import pytest

from stock_focus_data.support_resistance import (
    LONG_COLUMNS,
    calculate_symbol_levels,
    classic_pivots,
    cluster_candidates,
    clustering_tolerance,
    compact_columns,
    find_swing_candidates,
    select_nearest_levels,
)


def test_classic_pivots_match_known_values() -> None:
    result = classic_pivots(high=110.0, low=90.0, close=100.0)

    assert result == {
        "pivot": 100.0,
        "s1": 90.0,
        "s2": 80.0,
        "s3": 70.0,
        "r1": 110.0,
        "r2": 120.0,
        "r3": 130.0,
    }


@pytest.mark.parametrize(
    ("high", "low", "close"),
    [
        (90.0, 110.0, 100.0),
        (110.0, 90.0, 120.0),
        (110.0, 90.0, 80.0),
        (np.nan, 90.0, 100.0),
        (110.0, np.inf, 100.0),
    ],
)
def test_classic_pivots_reject_invalid_reference_prices(
    high: float,
    low: float,
    close: float,
) -> None:
    with pytest.raises(ValueError, match="invalid pivot reference"):
        classic_pivots(high=high, low=low, close=close)


def price_frame(
    timeframe: str,
    dates: list[str],
    highs: list[float],
    lows: list[float],
    closes: list[float] | None = None,
    complete: list[bool] | None = None,
) -> pd.DataFrame:
    close_values = closes if closes is not None else [
        (high + low) / 2.0 for high, low in zip(highs, lows, strict=True)
    ]
    timestamps = pd.to_datetime(dates, utc=True)
    frame = pd.DataFrame(
        {
            "symbol": "AMD",
            "timeframe": timeframe,
            "timestamp_utc": timestamps,
            "session_date": timestamps.strftime("%Y-%m-%d"),
            "open": close_values,
            "high": highs,
            "low": lows,
            "close": close_values,
            "volume": 1000,
            "atr_14": 2.0,
        }
    )
    if complete is not None:
        frame["is_complete"] = complete
    return frame


def test_find_swing_candidates_requires_strict_confirmed_window() -> None:
    frame = price_frame(
        "1d",
        [
            "2026-01-01",
            "2026-01-02",
            "2026-01-03",
            "2026-01-04",
            "2026-01-05",
            "2026-01-06",
            "2026-01-07",
        ],
        highs=[10, 11, 12, 20, 12, 11, 10],
        lows=[8, 7, 6, 1, 6, 7, 8],
    )

    result = find_swing_candidates(frame, "1d", "2026-01-07")

    assert result[["price", "origin_kind"]].to_dict("records") == [
        {"price": 1.0, "origin_kind": "swing_low"},
        {"price": 20.0, "origin_kind": "swing_high"},
    ]
    assert set(result["timeframe"]) == {"1d"}
    assert result["candidate_weight"].gt(0).all()


def test_find_swing_candidates_excludes_edges_ties_and_future_rows() -> None:
    frame = price_frame(
        "1d",
        pd.date_range("2026-01-01", periods=9, tz="UTC").astype(str).tolist(),
        highs=[30, 11, 12, 20, 20, 12, 11, 10, 40],
        lows=[0, 7, 6, 1, 1, 6, 7, 8, -5],
    )

    result = find_swing_candidates(frame, "1d", "2026-01-08")

    assert result.empty


def test_find_swing_candidates_excludes_incomplete_week() -> None:
    dates = pd.date_range("2025-11-07", periods=7, freq="W-FRI", tz="UTC")
    frame = price_frame(
        "1w",
        dates.astype(str).tolist(),
        highs=[10, 11, 20, 11, 10, 9, 30],
        lows=[8, 7, 1, 7, 8, 9, 0],
        complete=[True, True, True, True, True, True, False],
    )

    result = find_swing_candidates(frame, "1w", "2025-12-19")

    assert set(result["timestamp_utc"]) == {dates[2]}
    assert set(result["origin_kind"]) == {"swing_low", "swing_high"}


def test_clustering_tolerance_uses_larger_price_or_atr_scale() -> None:
    assert clustering_tolerance(100.0, 1.0) == 0.5
    assert clustering_tolerance(100.0, 8.0) == 2.0
    assert clustering_tolerance(100.0, np.nan) == 0.5


def test_cluster_candidates_calculates_weighted_level_and_metadata() -> None:
    candidates = pd.DataFrame(
        [
            {
                "price": 90.0,
                "timestamp_utc": pd.Timestamp("2026-08-01T00:00:00Z"),
                "timeframe": "1h",
                "origin_kind": "swing_low",
                "candidate_weight": 1.0,
            },
            {
                "price": 90.4,
                "timestamp_utc": pd.Timestamp("2026-08-20T00:00:00Z"),
                "timeframe": "1w",
                "origin_kind": "swing_high",
                "candidate_weight": 3.0,
            },
            {
                "price": 95.0,
                "timestamp_utc": pd.Timestamp("2026-08-25T00:00:00Z"),
                "timeframe": "1d",
                "origin_kind": "swing_low",
                "candidate_weight": 2.0,
            },
        ]
    )

    result = cluster_candidates(candidates, current_price=100.0, atr_14=2.0)

    assert len(result) == 2
    first = result.iloc[0]
    assert np.isclose(first["level_value"], 90.3)
    assert first["touch_count"] == 2
    assert first["strength_score"] == 4.0
    assert first["contributing_timeframes"] == "1h|1w"
    assert first["swing_low_count"] == 1
    assert first["swing_high_count"] == 1
    assert first["last_touch_utc"] == pd.Timestamp("2026-08-20T00:00:00Z")


def test_select_nearest_levels_orders_each_side_by_distance() -> None:
    clusters = pd.DataFrame(
        {
            "level_value": [90.0, 95.0, 99.0, 100.0, 101.0, 105.0, 110.0],
            "touch_count": [1] * 7,
            "strength_score": [1.0] * 7,
            "contributing_timeframes": ["1d"] * 7,
            "last_touch_utc": [pd.Timestamp("2026-08-01T00:00:00Z")] * 7,
            "swing_low_count": [1] * 7,
            "swing_high_count": [0] * 7,
            "cluster_tolerance": [0.5] * 7,
        }
    )

    result = select_nearest_levels(clusters, current_price=100.0, count=2)

    assert result.loc[result["side"] == "support", "level_value"].tolist() == [
        99.0,
        95.0,
    ]
    assert result.loc[
        result["side"] == "resistance", "level_value"
    ].tolist() == [101.0, 105.0]
    assert result.groupby("side")["rank"].apply(list).to_dict() == {
        "resistance": [1, 2],
        "support": [1, 2],
    }
    assert result.loc[result["side"] == "support", "distance_pct"].lt(0).all()
    assert result.loc[result["side"] == "resistance", "distance_pct"].gt(0).all()


@pytest.mark.parametrize("count", [0, 11])
def test_select_nearest_levels_rejects_invalid_count(count: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 10"):
        select_nearest_levels(pd.DataFrame(), 100.0, count)


def test_calculate_symbol_levels_builds_classic_and_structural_outputs() -> None:
    daily_dates = pd.date_range("2025-12-01", periods=20, freq="B", tz="UTC")
    daily = price_frame(
        "1d",
        daily_dates.astype(str).tolist(),
        highs=[110 + index % 5 for index in range(20)],
        lows=[90 - index % 4 for index in range(20)],
        closes=[100 + index * 0.1 for index in range(20)],
    )
    daily.loc[daily.index[-1], ["high", "low", "close", "atr_14"]] = [
        110.0,
        90.0,
        100.0,
        4.0,
    ]
    hourly_dates = pd.date_range("2025-12-01", periods=21, freq="h", tz="UTC")
    hourly = price_frame(
        "1h",
        hourly_dates.astype(str).tolist(),
        highs=[100, 101, 102, 110, 102, 101, 100] * 3,
        lows=[98, 97, 96, 90, 96, 97, 98] * 3,
    )
    weekly_dates = pd.date_range("2025-10-31", periods=8, freq="W-FRI", tz="UTC")
    weekly = price_frame(
        "1w",
        weekly_dates.astype(str).tolist(),
        highs=[108, 109, 120, 109, 108, 107, 130, 140],
        lows=[92, 91, 80, 91, 92, 93, 70, 60],
        closes=[100, 100, 100, 100, 100, 100, 100, 100],
        complete=[True, True, True, True, True, True, False, False],
    )

    compact, long_rows = calculate_symbol_levels(
        "AMD",
        hourly,
        daily,
        weekly,
        daily_dates[-1].date().isoformat(),
        levels=3,
    )
    long = pd.DataFrame(long_rows, columns=LONG_COLUMNS)

    assert compact["symbol"] == "AMD"
    assert compact["current_price"] == 100.0
    assert compact["daily_pivot"] == 100.0
    assert compact["daily_s1"] == 90.0
    assert compact["daily_r1"] == 110.0
    assert compact["weekly_reference_period_end"] == (
        weekly_dates[5].date().isoformat()
    )
    assert compact["calculation_status"] == "complete"
    assert set(long["method"]) == {"classic", "multi_timeframe"}
    assert set(long.loc[long["method"] == "classic", "reference_timeframe"]) == {
        "1d",
        "1w",
    }
    assert list(compact) == compact_columns(3)


def test_calculate_symbol_levels_marks_missing_optional_history_partial() -> None:
    daily = price_frame(
        "1d",
        ["2026-09-01"],
        highs=[110.0],
        lows=[90.0],
        closes=[100.0],
    )

    compact, long_rows = calculate_symbol_levels(
        "AMD",
        pd.DataFrame(),
        daily,
        pd.DataFrame(),
        "2026-09-01",
        levels=3,
    )

    assert compact["calculation_status"] == "partial"
    assert compact["warning"] == "missing_hourly|missing_completed_weekly"
    assert compact["daily_pivot"] == 100.0
    assert pd.isna(compact["weekly_pivot"])
    assert {row["reference_timeframe"] for row in long_rows} == {"1d"}
