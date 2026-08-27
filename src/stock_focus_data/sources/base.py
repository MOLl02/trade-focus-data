from datetime import datetime
from typing import Protocol

import pandas as pd

from stock_focus_data.models import Timeframe


class MarketDataSource(Protocol):
    def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Return normalized bars in the canonical candle schema."""

