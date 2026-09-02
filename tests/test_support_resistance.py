import numpy as np
import pandas as pd
import pytest

from stock_focus_data.support_resistance import (
    classic_pivots,
    find_swing_candidates,
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
