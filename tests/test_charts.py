import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stock_focus_data.charts import (
    build_manifest,
    build_symbol_figure,
    mark_drawn_levels,
    publish_chart_site,
    render_index,
    render_level_table,
    render_symbol_page,
    serialize_manifest,
    select_chart_history,
)
from stock_focus_data.config import UniverseEntry


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


def test_render_level_table_lists_hidden_classic_levels() -> None:
    levels = complete_level_frame()
    levels["drawn_on_chart"] = [True, True, False]

    table = render_level_table(levels)

    assert "R3" in table
    assert "150.00" in table
    assert "Not drawn" in table
    assert "1h|1d" in table


def test_render_symbol_page_is_offline_escaped_and_deterministic() -> None:
    daily = chart_daily_frame(start="2026-06-12", periods=55)
    analysis_date = str(daily.iloc[-1]["session_date"])
    history = select_chart_history(daily, analysis_date)
    levels = mark_drawn_levels(
        complete_level_frame(), history.candle_min, history.candle_max
    )
    figure = build_symbol_figure("AMD", history, levels, 120.0)
    compact = {
        "current_price": 120.0,
        "calculation_status": "complete",
        "warning": "<script>alert(1)</script>",
    }

    first = render_symbol_page(
        UniverseEntry("AMD", "stock"),
        analysis_date,
        compact,
        levels,
        figure,
        previous_symbol="AAPL",
        next_symbol="AMZN",
    )
    second = render_symbol_page(
        UniverseEntry("AMD", "stock"),
        analysis_date,
        compact,
        levels,
        figure,
        previous_symbol="AAPL",
        next_symbol="AMZN",
    )

    assert first == second
    assert 'id="support-resistance-amd"' in first
    assert "../../assets/plotly.min.js" in first
    assert "cdn.plot.ly" not in first
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in first
    assert '<a href="AAPL.html">Previous</a>' in first
    assert '<a href="AMZN.html">Next</a>' in first
    assert "Research visualization only" in first


def index_compact_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "AMD",
                "current_price": 120.0,
                "mt_support_1": 115.0,
                "mt_resistance_1": 125.0,
                "daily_pivot": 119.0,
                "weekly_pivot": 117.0,
                "calculation_status": "complete",
            },
            {
                "symbol": "SPCX",
                "current_price": 40.0,
                "mt_support_1": 38.0,
                "mt_resistance_1": 42.0,
                "daily_pivot": 39.5,
                "weekly_pivot": 41.0,
                "calculation_status": "complete",
            },
        ]
    )


def test_render_index_is_searchable_and_preserves_universe_order() -> None:
    entries = (
        UniverseEntry("AMD", "stock"),
        UniverseEntry("SPCX", "stock"),
    )

    page = render_index(entries, index_compact_frame(), "2026-09-01")

    assert 'id="symbol-search"' in page
    assert page.index("AMD.html") < page.index("SPCX.html")
    assert "manifest.json" in page
    assert "2026-09-01" in page


def test_manifest_is_complete_stable_and_has_no_wall_clock_time() -> None:
    entries = (
        UniverseEntry("AMD", "stock"),
        UniverseEntry("SPCX", "stock"),
    )
    ranges = {
        "AMD": ("2024-08-27", "2026-09-01"),
        "SPCX": ("2026-06-12", "2026-09-01"),
    }

    payload = build_manifest(entries, "2026-09-01", ranges, levels=3)
    first = serialize_manifest(payload)
    second = serialize_manifest(payload)

    assert first == second
    decoded = json.loads(first)
    assert decoded["analysis_date"] == "2026-09-01"
    assert decoded["files"] == [
        "AMD.html",
        "SPCX.html",
        "index.html",
        "manifest.json",
    ]
    assert [row["symbol"] for row in decoded["symbols"]] == ["AMD", "SPCX"]
    assert "generated_at" not in decoded


def support_history(symbol: str, timeframe: str) -> pd.DataFrame:
    if timeframe == "1d":
        frame = chart_daily_frame(start="2026-01-02", periods=175)
        frame["symbol"] = symbol
        frame["timeframe"] = timeframe
        frame["atr_14"] = 4.0
        return frame
    if timeframe == "1h":
        dates = pd.date_range("2026-06-01", periods=240, freq="h", tz="UTC")
    else:
        dates = pd.date_range("2026-01-02", periods=35, freq="W-FRI", tz="UTC")
    base = np.linspace(90.0, 110.0, len(dates))
    frame = pd.DataFrame(
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "timestamp_utc": dates,
            "session_date": dates.strftime("%Y-%m-%d"),
            "open": base,
            "high": base + 3.0 + np.sin(np.arange(len(dates))) * 2.0,
            "low": base - 3.0 - np.sin(np.arange(len(dates))) * 2.0,
            "close": base,
            "volume": 1000,
            "atr_14": 4.0,
            "data_source": "robinhood" if timeframe != "1w" else "derived",
        }
    )
    if timeframe == "1w":
        frame["is_complete"] = True
    return frame


def write_chart_site_fixture(root: Path, symbols: tuple[str, ...]) -> None:
    derived = root / "derived"
    derived.mkdir(parents=True, exist_ok=True)
    for symbol in symbols:
        for timeframe in ("1h", "1d", "1w"):
            support_history(symbol, timeframe).to_parquet(
                derived / f"{symbol}-{timeframe}.parquet", index=False
            )


def test_publish_chart_site_writes_complete_offline_site(tmp_path: Path) -> None:
    root = tmp_path / "data"
    output_root = tmp_path / "charts" / "support_resistance"
    entries = (
        UniverseEntry("AMD", "stock"),
        UniverseEntry("SPCX", "stock"),
    )
    write_chart_site_fixture(root, ("AMD", "SPCX"))

    result = publish_chart_site(root, entries, output_root, levels=3)

    target = output_root / result.analysis_date
    assert result.symbol_count == 2
    assert (target / "index.html").exists()
    assert (target / "manifest.json").exists()
    assert (target / "AMD.html").exists()
    assert (target / "SPCX.html").exists()
    assert (output_root.parent / "assets" / "plotly.min.js").exists()
    assert "../../assets/plotly.min.js" in (target / "AMD.html").read_text(
        encoding="utf-8"
    )


def test_publish_chart_site_is_byte_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "data"
    output_root = tmp_path / "charts" / "support_resistance"
    entries = (UniverseEntry("AMD", "stock"),)
    write_chart_site_fixture(root, ("AMD",))

    first = publish_chart_site(root, entries, output_root, levels=3)
    target = output_root / first.analysis_date
    hashes_before = {
        path.name: path.read_bytes()
        for path in sorted(target.iterdir())
        if path.is_file()
    }
    publish_chart_site(root, entries, output_root, levels=3)
    hashes_after = {
        path.name: path.read_bytes()
        for path in sorted(target.iterdir())
        if path.is_file()
    }

    assert hashes_after == hashes_before


def test_render_failure_preserves_existing_site(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stock_focus_data.charts as charts_module

    root = tmp_path / "data"
    output_root = tmp_path / "charts" / "support_resistance"
    entries = (UniverseEntry("AMD", "stock"),)
    write_chart_site_fixture(root, ("AMD",))
    analysis_date = str(support_history("AMD", "1d").iloc[-1]["session_date"])
    target = output_root / analysis_date
    target.mkdir(parents=True)
    sentinel = target / "index.html"
    sentinel.write_text("existing site", encoding="utf-8")

    def fail_render(*args, **kwargs):
        raise RuntimeError("render failed")

    monkeypatch.setattr(charts_module, "render_symbol_page", fail_render)

    with pytest.raises(RuntimeError, match="render failed"):
        publish_chart_site(root, entries, output_root, levels=3)

    assert sentinel.read_text(encoding="utf-8") == "existing site"
