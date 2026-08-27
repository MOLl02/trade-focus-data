from datetime import UTC, datetime

import pandas as pd

from stock_focus_data.collection import collect_symbol
from stock_focus_data.models import Timeframe, empty_candle_frame


class FakeAlpaca:
    def __init__(self) -> None:
        self.calls = 0

    def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        self.calls += 1
        return pd.DataFrame(
            [
                {
                    "symbol": symbol,
                    "timeframe": timeframe.value,
                    "timestamp_utc": start,
                    "session_date": start.date().isoformat(),
                    "open": 10.0,
                    "high": 12.0,
                    "low": 9.0,
                    "close": 11.0,
                    "volume": 100,
                    "vwap": None,
                    "trade_count": None,
                    "data_source": "alpaca",
                    "retrieved_at_utc": end,
                    "validation_status": "pending",
                    "fallback_reason": "robinhood_missing_or_incomplete",
                }
            ]
        )


def test_valid_robinhood_rows_avoid_fallback() -> None:
    fallback = FakeAlpaca()
    start = datetime(2026, 8, 25, tzinfo=UTC)
    end = datetime(2026, 8, 26, tzinfo=UTC)
    robinhood = fallback.get_bars(
        "AMD", Timeframe.DAY, start, end
    ).assign(data_source="robinhood", fallback_reason=None)
    fallback.calls = 0
    result, status = collect_symbol(
        "AMD", Timeframe.DAY, start, end, robinhood, fallback
    )
    assert fallback.calls == 0
    assert status["source"] == "robinhood"
    assert set(result["data_source"]) == {"robinhood"}


def test_empty_robinhood_rows_use_alpaca() -> None:
    fallback = FakeAlpaca()
    start = datetime(2026, 8, 25, tzinfo=UTC)
    result, status = collect_symbol(
        "AMD",
        Timeframe.DAY,
        start,
        datetime(2026, 8, 26, tzinfo=UTC),
        empty_candle_frame(),
        fallback,
    )
    assert fallback.calls == 1
    assert status["source"] == "alpaca"
    assert set(result["data_source"]) == {"alpaca"}
