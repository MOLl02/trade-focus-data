import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pandas as pd

from stock_focus_data.models import CANDLE_COLUMNS, Timeframe, empty_candle_frame


ALPACA_TIMEFRAMES = {Timeframe.HOUR: "1Hour", Timeframe.DAY: "1Day"}


class AlpacaSource:
    def __init__(
        self,
        key_id: str,
        secret_key: str,
        base_url: str = "https://data.alpaca.markets",
        feed: str = "iex",
        client: httpx.Client | None = None,
        raw_directory: Path | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not key_id or not secret_key:
            raise ValueError("Alpaca credentials are required for fallback")
        self.base_url = base_url.rstrip("/")
        self.feed = feed
        self.client = client or httpx.Client(timeout=30.0)
        self.headers = {
            "APCA-API-KEY-ID": key_id,
            "APCA-API-SECRET-KEY": secret_key,
        }
        self.raw_directory = raw_directory
        self.sleeper = sleeper

    def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        if timeframe not in ALPACA_TIMEFRAMES:
            raise ValueError("Alpaca fetch supports only 1h and 1d; derive 1w from 1d")
        rows: list[dict[str, object]] = []
        token: str | None = None
        retrieved = datetime.now(UTC)
        page = 0
        while True:
            params = {
                "symbols": symbol,
                "timeframe": ALPACA_TIMEFRAMES[timeframe],
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": "10000",
                "adjustment": "split",
                "feed": self.feed,
                "sort": "asc",
            }
            if token:
                params["page_token"] = token
            for attempt in range(3):
                response = self.client.get(
                    f"{self.base_url}/v2/stocks/bars",
                    params=params,
                    headers=self.headers,
                )
                if self.raw_directory is not None:
                    self.raw_directory.mkdir(parents=True, exist_ok=True)
                    stamp = retrieved.strftime("%Y%m%dT%H%M%SZ")
                    raw_path = self.raw_directory / (
                        f"{symbol}-{timeframe.value}-{stamp}-"
                        f"page{page:03d}-attempt{attempt + 1}.json"
                    )
                    raw_path.write_text(response.text, encoding="utf-8")
                if response.status_code < 500:
                    break
                if attempt < 2:
                    self.sleeper(float(2**attempt))
            response.raise_for_status()
            payload = response.json()
            for bar in payload.get("bars", {}).get(symbol, []):
                timestamp = pd.Timestamp(bar["t"])
                if timestamp.tzinfo is None:
                    timestamp = timestamp.tz_localize("UTC")
                else:
                    timestamp = timestamp.tz_convert("UTC")
                rows.append(
                    {
                        "symbol": symbol,
                        "timeframe": timeframe.value,
                        "timestamp_utc": timestamp,
                        "session_date": timestamp.date().isoformat(),
                        "open": float(bar["o"]),
                        "high": float(bar["h"]),
                        "low": float(bar["l"]),
                        "close": float(bar["c"]),
                        "volume": int(bar["v"]),
                        "vwap": float(bar["vw"])
                        if bar.get("vw") is not None
                        else None,
                        "trade_count": int(bar["n"])
                        if bar.get("n") is not None
                        else None,
                        "data_source": "alpaca",
                        "retrieved_at_utc": pd.Timestamp(retrieved),
                        "validation_status": "pending",
                        "fallback_reason": "robinhood_missing_or_incomplete",
                    }
                )
            token = payload.get("next_page_token")
            if not token:
                break
            page += 1
        return (
            pd.DataFrame(rows, columns=CANDLE_COLUMNS)
            if rows
            else empty_candle_frame()
        )

