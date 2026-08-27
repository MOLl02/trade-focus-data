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
