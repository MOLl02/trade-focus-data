import numpy as np
import pandas as pd
import pytest

from stock_focus_data.charts import (
    mark_drawn_levels,
    select_chart_history,
)


def chart_daily_frame(
    start: str = "2024-01-02",
    periods: int = 700,
) -> pd.DataFrame:
    dates = pd.date_range(start, periods=periods, freq="B", tz="UTC")
    close = pd.Series(np.linspace(80.0, 120.0, periods))
    return pd.DataFrame(
        {
            "symbol": "AMD",
            "timeframe": "1d",
            "timestamp_utc": dates,
            "session_date": dates.strftime("%Y-%m-%d"),
            "open": close - 0.5,
            "high": close + 2.0,
            "low": close - 2.0,
            "close": close,
            "volume": 1_000_000,
            "sma_50": close.rolling(50).mean(),
            "sma_200": close.rolling(200).mean(),
            "rsi_14": 55.0,
            "data_source": "robinhood",
        }
    )


def chart_level_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "method": "multi_timeframe",
                "reference_timeframe": "multi",
                "level_name": "S1",
                "side": "support",
                "rank": 1,
                "level_value": 50.0,
                "distance_pct": -0.5,
            },
            {
                "method": "classic",
                "reference_timeframe": "1d",
                "level_name": "P",
                "side": "pivot",
                "rank": 0,
                "level_value": 90.0,
                "distance_pct": -0.1,
            },
            {
                "method": "classic",
                "reference_timeframe": "1w",
                "level_name": "R3",
                "side": "resistance",
                "rank": 3,
                "level_value": 150.0,
                "distance_pct": 0.5,
            },
        ]
    )


def test_select_chart_history_uses_two_year_and_six_month_windows() -> None:
    daily = chart_daily_frame()
    analysis_date = str(daily.iloc[-1]["session_date"])

    result = select_chart_history(daily, analysis_date)

    cutoff = pd.Timestamp(analysis_date)
    assert pd.Timestamp(result.overview["session_date"].min()) >= (
        cutoff - pd.DateOffset(years=2)
    )
    assert pd.Timestamp(result.zoom["session_date"].min()) >= (
        cutoff - pd.DateOffset(months=6)
    )
    assert str(result.overview.iloc[-1]["session_date"]) == analysis_date
    assert str(result.zoom.iloc[-1]["session_date"]) == analysis_date
    assert result.candle_min < float(result.zoom["low"].min())
    assert result.candle_max > float(result.zoom["high"].max())


def test_select_chart_history_uses_all_short_listing_rows() -> None:
    daily = chart_daily_frame(start="2026-06-12", periods=55)
    analysis_date = str(daily.iloc[-1]["session_date"])

    result = select_chart_history(daily, analysis_date)

    assert len(result.overview) == 55
    assert len(result.zoom) == 55


def test_select_chart_history_rejects_missing_analysis_date() -> None:
    with pytest.raises(ValueError, match="analysis date"):
        select_chart_history(chart_daily_frame(periods=20), "2026-09-01")


def test_mark_drawn_levels_keeps_structural_and_filters_classic() -> None:
    result = mark_drawn_levels(chart_level_frame(), 80.0, 120.0)

    assert result["drawn_on_chart"].tolist() == [True, True, False]
