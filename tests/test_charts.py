import numpy as np
import pandas as pd
import pytest

from stock_focus_data.charts import (
    build_symbol_figure,
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


def complete_level_frame() -> pd.DataFrame:
    frame = chart_level_frame()
    frame.loc[1, "level_value"] = 110.0
    frame["touch_count"] = [4, pd.NA, pd.NA]
    frame["strength_score"] = [3.2, pd.NA, pd.NA]
    frame["contributing_timeframes"] = ["1h|1d", pd.NA, pd.NA]
    frame["last_touch_utc"] = [
        pd.Timestamp("2026-08-28T19:00:00Z"),
        pd.NaT,
        pd.NaT,
    ]
    frame["reference_period_end"] = [pd.NA, "2026-09-01", "2026-08-28"]
    return frame


def test_build_symbol_figure_has_two_panels_and_required_traces() -> None:
    daily = chart_daily_frame(start="2025-01-02", periods=430)
    analysis_date = str(daily.iloc[-1]["session_date"])
    history = select_chart_history(daily, analysis_date)
    levels = mark_drawn_levels(
        complete_level_frame(), history.candle_min, history.candle_max
    )

    figure = build_symbol_figure("AMD", history, levels, 120.0)

    roles = [trace.meta["role"] for trace in figure.data]
    assert roles.count("overview_close") == 1
    assert roles.count("overview_sma_50") == 1
    assert roles.count("overview_sma_200") == 1
    assert roles.count("analysis_close") == 1
    assert roles.count("candlestick") == 1
    assert roles.count("level") == 2
    assert figure.layout.yaxis.domain[0] > figure.layout.yaxis2.domain[1]
    assert figure.layout.xaxis2.rangeslider.visible is False


def test_build_symbol_figure_keeps_hover_fields_and_level_metadata() -> None:
    daily = chart_daily_frame(start="2026-06-12", periods=55)
    analysis_date = str(daily.iloc[-1]["session_date"])
    history = select_chart_history(daily, analysis_date)
    levels = mark_drawn_levels(
        complete_level_frame(), history.candle_min, history.candle_max
    )

    figure = build_symbol_figure("SPCX", history, levels, 120.0)

    candle = next(
        trace for trace in figure.data if trace.meta["role"] == "candlestick"
    )
    assert "Volume" in candle.hovertemplate
    assert "RSI(14)" in candle.hovertemplate
    assert "Provider" in candle.hovertemplate
    level_traces = [
        trace for trace in figure.data if trace.meta["role"] == "level"
    ]
    assert {trace.meta["method"] for trace in level_traces} == {
        "multi_timeframe",
        "classic",
    }
    assert all(trace.xaxis == "x2" for trace in level_traces)
