import numpy as np
import pandas as pd

from stock_focus_data.models import CANDLE_COLUMNS


class DataValidationError(ValueError):
    pass


def validate_candles(frame: pd.DataFrame) -> pd.DataFrame:
    missing = set(CANDLE_COLUMNS).difference(frame.columns)
    if missing:
        raise DataValidationError(f"missing columns: {sorted(missing)}")
    if frame.empty:
        return frame.copy()
    result = frame.copy()
    result["timestamp_utc"] = pd.to_datetime(
        result["timestamp_utc"], utc=True, errors="raise"
    )
    result["retrieved_at_utc"] = pd.to_datetime(
        result["retrieved_at_utc"], utc=True, errors="raise"
    )
    prices = result[["open", "high", "low", "close"]].astype(float)
    if not np.isfinite(prices.to_numpy()).all():
        raise DataValidationError("non-finite price")
    if (prices <= 0).any().any():
        raise DataValidationError("non-positive price")
    if (result["volume"].astype(float) < 0).any():
        raise DataValidationError("negative volume")
    upper = prices[["open", "close", "low"]].max(axis=1)
    lower = prices[["open", "close", "high"]].min(axis=1)
    if (prices["high"] < upper).any() or (prices["low"] > lower).any():
        raise DataValidationError("invalid OHLC relationship")
    result = result.sort_values(
        ["symbol", "timeframe", "timestamp_utc", "retrieved_at_utc"]
    )
    result = result.drop_duplicates(
        ["symbol", "timeframe", "timestamp_utc"], keep="last"
    )
    result["validation_status"] = "valid"
    return result.reset_index(drop=True)
