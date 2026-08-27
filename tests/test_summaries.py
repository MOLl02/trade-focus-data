import pandas as pd

from stock_focus_data.summaries import build_latest_summary


def test_summary_selects_latest_complete_row() -> None:
    frame = pd.DataFrame(
        [
            {
                "symbol": "AMD",
                "timeframe": "1d",
                "timestamp_utc": "2026-08-25T00:00:00Z",
                "close": 10.0,
                "volume": 100,
                "volume_avg_20": 90.0,
                "rsi_14": 55.0,
                "macd": 1.0,
                "macd_signal": 0.8,
                "macd_histogram": 0.2,
                "stoch_k_14": 60.0,
                "stoch_d_3": 58.0,
                "atr_14": 2.0,
                "sma_20": 9.5,
                "sma_50": 9.0,
                "sma_200": 8.0,
                "ema_12": 9.8,
                "ema_26": 9.2,
                "ema_50": 9.0,
                "distance_sma_20": 0.0526,
                "distance_sma_50": 0.1111,
                "distance_sma_200": 0.25,
                "return_1": 0.01,
                "return_5": 0.05,
                "return_20": 0.1,
                "relative_volume_20": 1.11,
                "realized_volatility_20": 0.3,
                "drawdown": -0.02,
                "high_52w": 12.0,
                "low_52w": 6.0,
                "range_52w_position": 0.667,
                "data_source": "robinhood",
                "validation_status": "valid",
                "retrieved_at_utc": "2026-08-26T22:00:00Z",
                "is_complete": True,
            },
            {
                "symbol": "AMD",
                "timeframe": "1d",
                "timestamp_utc": "2026-08-26T00:00:00Z",
                "close": 11.0,
                "volume": 50,
                "data_source": "robinhood",
                "validation_status": "valid",
                "retrieved_at_utc": "2026-08-26T22:00:00Z",
                "is_complete": False,
            },
        ]
    )
    summary = build_latest_summary([frame])
    assert len(summary) == 1
    assert summary.iloc[0]["close"] == 10.0
    assert summary.iloc[0]["trend_state"] == "above_sma_20_50_200"
    assert summary.iloc[0]["macd_state"] == "bullish"


def test_summary_marks_missing_symbol_timeframes() -> None:
    frame = pd.DataFrame(
        [
            {
                "symbol": "AMD",
                "timeframe": "1d",
                "timestamp_utc": "2026-08-25T00:00:00Z",
                "close": 10.0,
                "data_source": "robinhood",
                "validation_status": "valid",
                "retrieved_at_utc": "2026-08-26T22:00:00Z",
            }
        ]
    )
    summary = build_latest_summary([frame], expected_symbols=["AMD", "PLTR"])
    assert len(summary) == 6
    missing = summary.loc[summary["validation_status"] == "missing"]
    assert len(missing) == 5
    assert set(missing["symbol"]) == {"AMD", "PLTR"}

