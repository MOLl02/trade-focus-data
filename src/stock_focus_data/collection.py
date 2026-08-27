from datetime import datetime

import pandas as pd

from stock_focus_data.models import Timeframe
from stock_focus_data.sources.base import MarketDataSource
from stock_focus_data.validation import DataValidationError, validate_candles


def collect_symbol(
    symbol: str,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    robinhood_frame: pd.DataFrame,
    fallback: MarketDataSource,
) -> tuple[pd.DataFrame, dict[str, object]]:
    if robinhood_frame.empty:
        preferred = robinhood_frame.copy()
    else:
        preferred = robinhood_frame.loc[
            (robinhood_frame["symbol"] == symbol)
            & (robinhood_frame["timeframe"] == timeframe.value)
        ].copy()
    try:
        preferred = validate_candles(preferred)
    except DataValidationError:
        preferred = preferred.iloc[0:0].copy()
    if not preferred.empty:
        return preferred, {
            "symbol": symbol,
            "timeframe": timeframe.value,
            "source": "robinhood",
            "rows": len(preferred),
            "fallback_reason": None,
        }
    fallback_frame = validate_candles(
        fallback.get_bars(symbol, timeframe, start, end)
    )
    if fallback_frame.empty:
        raise DataValidationError(f"no valid bars for {symbol} {timeframe.value}")
    return fallback_frame, {
        "symbol": symbol,
        "timeframe": timeframe.value,
        "source": "alpaca",
        "rows": len(fallback_frame),
        "fallback_reason": "robinhood_missing_or_incomplete",
    }
