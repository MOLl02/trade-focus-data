from datetime import UTC, datetime

import pandas as pd

from stock_focus_data.aggregation import aggregate_weekly


def test_aggregates_daily_bars_and_marks_current_week_incomplete() -> None:
    dates = pd.to_datetime(
        [
            "2026-08-17",
            "2026-08-18",
            "2026-08-19",
            "2026-08-20",
            "2026-08-21",
            "2026-08-24",
        ],
        utc=True,
    )
    daily = pd.DataFrame(
        {
            "symbol": "AMD",
            "timeframe": "1d",
            "timestamp_utc": dates,
            "session_date": [date.date().isoformat() for date in dates],
            "open": [10, 11, 12, 13, 14, 20],
            "high": [12, 13, 14, 15, 16, 22],
            "low": [9, 10, 11, 12, 13, 19],
            "close": [11, 12, 13, 14, 15, 21],
            "volume": [100, 110, 120, 130, 140, 200],
            "vwap": None,
            "trade_count": None,
            "data_source": "robinhood",
            "retrieved_at_utc": pd.Timestamp("2026-08-26T22:00:00Z"),
            "validation_status": "valid",
            "fallback_reason": None,
        }
    )
    weekly = aggregate_weekly(daily, datetime(2026, 8, 26, 22, tzinfo=UTC))
    first = weekly.iloc[0]
    assert (
        first["open"],
        first["high"],
        first["low"],
        first["close"],
        first["volume"],
    ) == (10, 16, 9, 15, 600)
    assert bool(first["is_complete"]) is True
    assert bool(weekly.iloc[-1]["is_complete"]) is False
