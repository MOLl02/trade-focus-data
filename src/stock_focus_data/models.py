from enum import StrEnum

import pandas as pd


class Timeframe(StrEnum):
    HOUR = "1h"
    DAY = "1d"
    WEEK = "1w"


CANDLE_COLUMNS = (
    "symbol",
    "timeframe",
    "timestamp_utc",
    "session_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "vwap",
    "trade_count",
    "data_source",
    "retrieved_at_utc",
    "validation_status",
    "fallback_reason",
)


def empty_candle_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=CANDLE_COLUMNS)
