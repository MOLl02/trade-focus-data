import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from stock_focus_data.models import CANDLE_COLUMNS, Timeframe, empty_candle_frame


class RobinhoodImportSource:
    @staticmethod
    def load(
        path: Path,
        timeframe: Timeframe,
        retrieved_at: datetime,
    ) -> pd.DataFrame:
        payload = json.loads(path.read_text(encoding="utf-8"))
        results = payload.get("data", {}).get("results", [])
        rows: list[dict[str, object]] = []
        retrieved_timestamp = pd.Timestamp(retrieved_at)
        if retrieved_timestamp.tzinfo is None:
            retrieved_timestamp = retrieved_timestamp.tz_localize("UTC")
        else:
            retrieved_timestamp = retrieved_timestamp.tz_convert("UTC")
        for result in results:
            symbol = str(result["symbol"]).upper()
            for bar in result.get("bars") or []:
                if bar is None or bar.get("interpolated", False):
                    continue
                timestamp = pd.Timestamp(bar["begins_at"])
                if timestamp.tzinfo is None:
                    timestamp = timestamp.tz_localize("UTC")
                else:
                    timestamp = timestamp.tz_convert("UTC")
                open_price = float(bar["open_price"])
                high_price = float(bar["high_price"])
                low_price = float(bar["low_price"])
                close_price = float(bar["close_price"])
                if (
                    low_price > min(open_price, close_price)
                    or high_price < max(open_price, close_price)
                    or low_price > high_price
                ):
                    continue
                rows.append(
                    {
                        "symbol": symbol,
                        "timeframe": timeframe.value,
                        "timestamp_utc": timestamp,
                        "session_date": timestamp.date().isoformat(),
                        "open": open_price,
                        "high": high_price,
                        "low": low_price,
                        "close": close_price,
                        "volume": int(bar["volume"]),
                        "vwap": None,
                        "trade_count": None,
                        "data_source": "robinhood",
                        "retrieved_at_utc": retrieved_timestamp,
                        "validation_status": "pending",
                        "fallback_reason": None,
                    }
                )
        if not rows:
            return empty_candle_frame()
        frame = pd.DataFrame(rows, columns=CANDLE_COLUMNS)
        frame["timestamp_utc"] = frame["timestamp_utc"].astype("datetime64[ns, UTC]")
        frame["retrieved_at_utc"] = frame["retrieved_at_utc"].astype(
            "datetime64[ns, UTC]"
        )
        return frame
