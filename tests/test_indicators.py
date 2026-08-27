import math

import pandas as pd

from stock_focus_data.indicators import add_indicators


def trend_frame(timeframe: str = "1d", count: int = 260) -> pd.DataFrame:
    close = pd.Series(range(1, count + 1), dtype=float)
    dates = pd.date_range("2025-01-01", periods=count, freq="B", tz="UTC")
    return pd.DataFrame(
        {
            "symbol": "AMD",
            "timeframe": timeframe,
            "timestamp_utc": dates,
            "session_date": dates.date.astype(str),
            "open": close - 0.5,
            "high": close,
            "low": close - 1.0,
            "close": close,
            "volume": pd.Series(range(1000, 1000 + count), dtype=float),
            "vwap": None,
            "trade_count": None,
            "data_source": "robinhood",
            "retrieved_at_utc": pd.Timestamp("2026-08-26T22:00:00Z"),
            "validation_status": "valid",
            "fallback_reason": None,
        }
    )


def test_indicators_have_expected_values_on_monotonic_series() -> None:
    result = add_indicators(trend_frame())
    last = result.iloc[-1]
    assert last["sma_20"] == 250.5
    assert last["sma_200"] == 160.5
    assert last["rsi_14"] == 100.0
    assert last["drawdown"] == 0.0
    assert math.isclose(last["return_1"], 260 / 259 - 1)
    assert math.isclose(last["range_52w_position"], 1.0)
    assert {
        "macd",
        "macd_signal",
        "macd_histogram",
        "atr_14",
        "stoch_k_14",
        "stoch_d_3",
        "relative_volume_20",
        "realized_volatility_20",
    }.issubset(result.columns)


def test_insufficient_history_remains_null() -> None:
    result = add_indicators(trend_frame(count=10))
    assert pd.isna(result.iloc[-1]["sma_20"])
    assert pd.isna(result.iloc[-1]["rsi_14"])
    assert pd.isna(result.iloc[-1]["range_52w_position"])
