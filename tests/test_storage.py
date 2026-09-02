from pathlib import Path

import pandas as pd

from stock_focus_data.models import Timeframe
import stock_focus_data.storage as storage_module
from stock_focus_data.storage import CandleStore, write_manifest


def candle(source: str, close: float, retrieved: str) -> pd.DataFrame:
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
                "close": close,
                "volume": 100,
                "vwap": None,
                "trade_count": None,
                "data_source": source,
                "retrieved_at_utc": retrieved,
                "validation_status": "pending",
                "fallback_reason": None,
            }
        ]
    )


def test_merge_is_idempotent_and_prefers_robinhood(tmp_path: Path) -> None:
    store = CandleStore(tmp_path)
    store.merge(candle("alpaca", 10.5, "2026-08-26T20:00:00Z"))
    store.merge(candle("robinhood", 11.0, "2026-08-26T19:00:00Z"))
    store.merge(candle("robinhood", 11.0, "2026-08-26T19:00:00Z"))
    result = store.read("AMD", Timeframe.DAY)
    assert len(result) == 1
    assert result.iloc[0]["data_source"] == "robinhood"
    assert result.iloc[0]["close"] == 11.0


def test_daily_merge_deduplicates_provider_timestamp_conventions(
    tmp_path: Path,
) -> None:
    store = CandleStore(tmp_path)
    alpaca = candle("alpaca", 10.5, "2026-08-26T20:00:00Z").assign(
        timestamp_utc="2026-08-25T04:00:00Z"
    )
    store.merge(alpaca)
    store.merge(candle("robinhood", 11.0, "2026-08-26T19:00:00Z"))

    result = store.read("AMD", Timeframe.DAY)
    assert len(result) == 1
    assert result.iloc[0]["data_source"] == "robinhood"


def test_trim_removes_bars_outside_requested_window(tmp_path: Path) -> None:
    store = CandleStore(tmp_path)
    rows = pd.concat(
        [
            candle("robinhood", 9.0, "2026-08-26T19:00:00Z").assign(
                timestamp_utc="2024-08-26T00:00:00Z",
                session_date="2024-08-26",
            ),
            candle("robinhood", 10.0, "2026-08-26T19:00:00Z").assign(
                timestamp_utc="2024-08-27T00:00:00Z",
                session_date="2024-08-27",
            ),
            candle("robinhood", 11.0, "2026-08-26T19:00:00Z"),
        ],
        ignore_index=True,
    )
    store.merge(rows)

    removed = store.trim(
        Timeframe.DAY,
        pd.Timestamp("2024-08-27T00:00:00Z"),
        pd.Timestamp("2026-08-26T23:59:59Z"),
    )

    result = store.read("AMD", Timeframe.DAY)
    assert removed == 1
    assert result["session_date"].tolist() == ["2024-08-27", "2026-08-25"]


def test_trim_removes_hourly_bars_outside_regular_session(
    tmp_path: Path,
) -> None:
    store = CandleStore(tmp_path)
    rows = pd.concat(
        [
            candle("alpaca", 10.0, "2026-08-26T19:00:00Z").assign(
                timeframe="1h",
                timestamp_utc="2026-08-26T12:00:00Z",
            ),
            candle("alpaca", 11.0, "2026-08-26T19:00:00Z").assign(
                timeframe="1h",
                timestamp_utc="2026-08-26T13:00:00Z",
            ),
        ],
        ignore_index=True,
    )
    store.merge(rows)

    removed = store.trim(
        Timeframe.HOUR,
        pd.Timestamp("2026-08-26T00:00:00Z"),
        pd.Timestamp("2026-08-26T23:59:59Z"),
    )

    result = store.read("AMD", Timeframe.HOUR)
    assert removed == 1
    assert result["timestamp_utc"].tolist() == [
        pd.Timestamp("2026-08-26T13:00:00Z")
    ]


def test_manifests_do_not_collide_within_same_second(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FixedDatetime:
        @classmethod
        def now(cls, timezone):
            return pd.Timestamp("2026-08-26T22:00:00Z").to_pydatetime()

    monkeypatch.setattr(storage_module, "datetime", FixedDatetime)
    first = write_manifest(tmp_path, {"run": 1})
    second = write_manifest(tmp_path, {"run": 2})
    assert first != second
    assert first.exists()
    assert second.exists()
