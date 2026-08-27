from datetime import datetime

import pandas as pd

from stock_focus_data.models import CANDLE_COLUMNS
from stock_focus_data.validation import validate_candles


def aggregate_weekly(daily: pd.DataFrame, now_utc: datetime) -> pd.DataFrame:
    validated = validate_candles(daily)
    if validated.empty:
        return validated.assign(is_complete=pd.Series(dtype=bool))
    frames: list[pd.DataFrame] = []
    for symbol, group in validated.groupby("symbol", sort=True):
        indexed = group.set_index("timestamp_utc").sort_index()
        weekly = (
            indexed.resample("W-FRI", label="right", closed="right")
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                    "retrieved_at_utc": "max",
                }
            )
            .dropna(subset=["open", "close"])
        )
        weekly["symbol"] = symbol
        weekly["timeframe"] = "1w"
        weekly["session_date"] = [
            timestamp.date().isoformat() for timestamp in weekly.index
        ]
        weekly["vwap"] = None
        weekly["trade_count"] = None
        weekly["data_source"] = "derived"
        weekly["validation_status"] = "pending"
        weekly["fallback_reason"] = None
        now_timestamp = pd.Timestamp(now_utc)
        if now_timestamp.tzinfo is None:
            now_timestamp = now_timestamp.tz_localize("UTC")
        else:
            now_timestamp = now_timestamp.tz_convert("UTC")
        now_naive = now_timestamp.tz_localize(None)
        current_period_label = (
            now_naive.to_period("W-FRI")
            .end_time.normalize()
            .tz_localize("UTC")
        )
        weekly["is_complete"] = weekly.index < current_period_label
        frames.append(weekly.reset_index())
    result = pd.concat(frames, ignore_index=True)
    core = validate_candles(result[list(CANDLE_COLUMNS)])
    complete = result.set_index(
        ["symbol", "timeframe", "timestamp_utc"]
    )["is_complete"]
    key = core.set_index(["symbol", "timeframe", "timestamp_utc"]).index
    core["is_complete"] = complete.reindex(key).to_numpy()
    return core
