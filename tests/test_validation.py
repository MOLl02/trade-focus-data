import pandas as pd
import pytest

from stock_focus_data.validation import DataValidationError, validate_candles


def valid_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "AMD",
                "timeframe": "1d",
                "timestamp_utc": "2026-08-25T00:00:00Z",
                "session_date": "2026-08-25",
                "open": 10.0,
                "high": 12.0,
                "low": 9.0,
                "close": 11.0,
                "volume": 100,
                "vwap": None,
                "trade_count": None,
                "data_source": "robinhood",
                "retrieved_at_utc": "2026-08-26T00:00:00Z",
                "validation_status": "pending",
                "fallback_reason": None,
            },
            {
                "symbol": "AMD",
                "timeframe": "1d",
                "timestamp_utc": "2026-08-25T00:00:00Z",
                "session_date": "2026-08-25",
                "open": 10.0,
                "high": 12.0,
                "low": 9.0,
                "close": 11.0,
                "volume": 100,
                "vwap": None,
                "trade_count": None,
                "data_source": "robinhood",
                "retrieved_at_utc": "2026-08-26T00:00:00Z",
                "validation_status": "pending",
                "fallback_reason": None,
            },
        ]
    )


def test_validation_deduplicates_and_marks_valid() -> None:
    result = validate_candles(valid_frame())
    assert len(result) == 1
    assert result.iloc[0]["validation_status"] == "valid"


def test_validation_rejects_impossible_ohlc() -> None:
    frame = valid_frame().iloc[:1].copy()
    frame.loc[:, "high"] = 8.0
    with pytest.raises(DataValidationError, match="invalid OHLC relationship"):
        validate_candles(frame)


def test_validation_rejects_negative_volume() -> None:
    frame = valid_frame().iloc[:1].copy()
    frame.loc[:, "volume"] = -1
    with pytest.raises(DataValidationError, match="negative volume"):
        validate_candles(frame)
