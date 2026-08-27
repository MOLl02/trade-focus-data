from datetime import UTC, datetime
from pathlib import Path

import httpx
import pandas as pd

from stock_focus_data.models import Timeframe
from stock_focus_data.sources.alpaca import AlpacaSource
from stock_focus_data.sources.alpaca_import import AlpacaImportSource


def test_alpaca_normalizes_bars_and_retries_transient_failure(
    tmp_path: Path,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.headers["APCA-API-KEY-ID"] == "key"
        assert request.url.params["timeframe"] == "1Day"
        if calls == 1:
            return httpx.Response(503, json={"message": "temporary"})
        return httpx.Response(
            200,
            json={
                "bars": {
                    "AMD": [
                        {
                            "t": "2026-08-25T04:00:00Z",
                            "o": 10,
                            "h": 12,
                            "l": 9,
                            "c": 11,
                            "v": 100,
                            "n": 50,
                            "vw": 10.8,
                        }
                    ]
                },
                "next_page_token": None,
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    source = AlpacaSource(
        "key",
        "secret",
        client=client,
        raw_directory=tmp_path,
        sleeper=lambda _: None,
    )
    frame = source.get_bars(
        "AMD",
        Timeframe.DAY,
        datetime(2026, 8, 25, tzinfo=UTC),
        datetime(2026, 8, 26, tzinfo=UTC),
    )
    assert calls == 2
    assert len(list(tmp_path.glob("AMD-1d-*.json"))) == 2
    assert len(frame) == 1
    assert frame.iloc[0]["vwap"] == 10.8
    assert frame.iloc[0]["trade_count"] == 50
    assert frame.iloc[0]["fallback_reason"] == "robinhood_missing_or_incomplete"


def test_parses_connected_alpaca_payload() -> None:
    frame = AlpacaImportSource.load(
        Path("tests/fixtures/alpaca_day.json"),
        Timeframe.DAY,
        datetime(2026, 8, 26, 22, tzinfo=UTC),
    )
    assert len(frame) == 1
    assert frame.iloc[0]["symbol"] == "CBRS"
    assert frame.iloc[0]["close"] == 182.245
    assert frame.iloc[0]["timestamp_utc"] == pd.Timestamp(
        "2026-08-26T00:00:00Z"
    )
    assert frame.iloc[0]["data_source"] == "alpaca"
    assert frame.iloc[0]["fallback_reason"] == "robinhood_missing_or_incomplete"


def test_connected_alpaca_hourly_import_keeps_regular_session_only() -> None:
    frame = AlpacaImportSource.load(
        Path("tests/fixtures/alpaca_hour.json"),
        Timeframe.HOUR,
        datetime(2026, 8, 26, 22, tzinfo=UTC),
    )
    assert len(frame) == 1
    assert frame.iloc[0]["timestamp_utc"] == pd.Timestamp(
        "2026-08-26T13:00:00Z"
    )
