import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from stock_focus_data.models import CANDLE_COLUMNS, Timeframe, empty_candle_frame


class AlpacaImportSource:
    @staticmethod
    def load(
        path: Path,
        timeframe: Timeframe,
        retrieved_at: datetime,
    ) -> pd.DataFrame:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows: list[dict[str, object]] = []
        retrieved_timestamp = pd.Timestamp(retrieved_at)
        if retrieved_timestamp.tzinfo is None:
            retrieved_timestamp = retrieved_timestamp.tz_localize("UTC")
        else:
            retrieved_timestamp = retrieved_timestamp.tz_convert("UTC")
        for symbol, bars in payload.get("bars", {}).items():
            for bar in bars or []:
                timestamp = pd.Timestamp(bar["timestamp"])
                if timestamp.tzinfo is None:
                    timestamp = timestamp.tz_localize("UTC")
                else:
                    timestamp = timestamp.tz_convert("UTC")
                if timeframe is Timeframe.DAY:
                    market_date = timestamp.tz_convert(
                        "America/New_York"
                    ).date()
                    timestamp = pd.Timestamp(market_date, tz="UTC")
                if timeframe is Timeframe.HOUR:
                    market_hour = timestamp.tz_convert(
                        "America/New_York"
                    ).hour
                    if market_hour < 9 or market_hour > 15:
                        continue
                rows.append(
                    {
                        "symbol": str(symbol).upper(),
                        "timeframe": timeframe.value,
                        "timestamp_utc": timestamp,
                        "session_date": timestamp.date().isoformat(),
                        "open": float(bar["open"]),
                        "high": float(bar["high"]),
                        "low": float(bar["low"]),
                        "close": float(bar["close"]),
                        "volume": int(bar["volume"]),
                        "vwap": float(bar["vwap"])
                        if bar.get("vwap") is not None
                        else None,
                        "trade_count": int(bar["trade_count"])
                        if bar.get("trade_count") is not None
                        else None,
                        "data_source": "alpaca",
                        "retrieved_at_utc": retrieved_timestamp,
                        "validation_status": "pending",
                        "fallback_reason": "robinhood_missing_or_incomplete",
                    }
                )
        if not rows:
            return empty_candle_frame()
        frame = pd.DataFrame(rows, columns=CANDLE_COLUMNS)
        frame["timestamp_utc"] = frame["timestamp_utc"].astype(
            "datetime64[ns, UTC]"
        )
        frame["retrieved_at_utc"] = frame["retrieved_at_utc"].astype(
            "datetime64[ns, UTC]"
        )
        return frame
