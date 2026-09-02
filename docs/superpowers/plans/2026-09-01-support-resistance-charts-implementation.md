# Interactive Support and Resistance Charts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate an offline, interactive two-panel HTML chart and complete level table for every configured symbol, plus a searchable index, manifest, CLI command, documentation, and the requested pull request.

**Architecture:** A focused `charts.py` module selects deterministic daily-history windows, classifies level visibility, constructs Plotly figures, renders escaped HTML, and publishes a complete versioned site from staged files. The CLI recalculates support and resistance directly from the stored hourly/daily/weekly data so chart levels always match the selected analysis date. Project-authored pages share one local Plotly JavaScript bundle and are validated before publication.

**Tech Stack:** Python 3.11+, pandas 2.2+, NumPy, PyArrow/Parquet, Plotly 6.x, Typer, pytest, HTML/CSS/JavaScript, Git, GitHub pull requests.

## Global Constraints

- Generate one interactive HTML page for every entry in `config/universe.yaml`; the production universe contains exactly 32 entries.
- Use all retained daily history up to two calendar years for the overview and six calendar months for the candlestick zoom; shorter listings use all available history.
- Recalculate levels through `build_support_resistance` for the same common analysis date instead of reading possibly stale published level files.
- Draw every multi-timeframe structural level; draw classic daily/weekly levels only inside the original zoom candle range including its margin; list every level in the table.
- Use `plotly>=6,<7` and one shared local `charts/assets/plotly.min.js`; generated pages must not require a CDN.
- Default output is `charts/support_resistance/{analysis_date}/` with one page per symbol, `index.html`, and `manifest.json`.
- Stage all project-authored output before publication and preserve the existing analysis-date site when calculation, validation, or rendering fails.
- Use stable symbol ordering, div identifiers, numeric formatting, JSON ordering, links, and page content; do not embed a wall-clock generation timestamp.
- Escape every data-derived HTML string and never include credentials, environment values, or raw provider payloads.
- Keep the feature research-only: no predictions, signals, alerts, position sizing, or orders.
- Follow red-green-refactor for every production behavior and commit after each independently testable task.

---

## File structure

- Create `src/stock_focus_data/charts.py`: chart-window selection, level visibility, Plotly figures, HTML/index/manifest rendering, site construction, and staged publication.
- Create `tests/test_charts.py`: unit and integration tests for every chart-module boundary.
- Modify `src/stock_focus_data/cli.py`: register `chart-support-resistance` and print its deterministic summary.
- Modify `tests/test_cli.py`: exercise the chart command with the existing one-symbol fixture.
- Modify `pyproject.toml`: declare `plotly>=6,<7`.
- Modify `README.md`: add the chart command and primary output path.
- Modify `docs/DATA_USAGE_GUIDE.md`: explain generation, local/Git use, panels, hover fields, level filtering, and limitations.
- Modify `docs/superpowers/specs/2026-09-01-support-resistance-charts-design.md`: mark the design implemented after verification.
- Create `charts/assets/plotly.min.js`: shared Plotly browser runtime generated from the installed Python package.
- Create `charts/support_resistance/2026-09-01/index.html`, `manifest.json`, and 32 symbol pages: committed production artifacts.

### Task 1: Select chart windows and classify visible levels

**Files:**
- Create: `src/stock_focus_data/charts.py`
- Create: `tests/test_charts.py`
- Modify: `pyproject.toml:10-17`

**Interfaces:**
- Consumes: daily derived frames with `timestamp_utc`, `session_date`, `open`, `high`, `low`, `close`, and `volume`; long level frames produced by `build_support_resistance`.
- Produces: `ChartHistory`, `select_chart_history(daily, analysis_date)`, and `mark_drawn_levels(levels, candle_min, candle_max)`.

- [ ] **Step 1: Write failing window and level-visibility tests**

Create `tests/test_charts.py`:

```python
from pathlib import Path

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
```

- [ ] **Step 2: Run the tests and verify the expected red failure**

Run:

```powershell
$env:PYTHONPATH='.vendor;src'
python -m pytest tests/test_charts.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'stock_focus_data.charts'`.

- [ ] **Step 3: Add the Plotly dependency declaration and minimal pure implementation**

Add to `pyproject.toml` dependencies after PyArrow:

```toml
  "plotly>=6,<7",
```

Create `src/stock_focus_data/charts.py`:

```python
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class ChartHistory:
    analysis_date: str
    overview: pd.DataFrame
    zoom: pd.DataFrame
    candle_min: float
    candle_max: float


def select_chart_history(
    daily: pd.DataFrame,
    analysis_date: str,
) -> ChartHistory:
    required = {
        "timestamp_utc",
        "session_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }
    missing = sorted(required.difference(daily.columns))
    if missing:
        raise ValueError(f"daily chart history missing columns: {missing}")
    cutoff = pd.Timestamp(analysis_date).normalize()
    frame = daily.copy()
    frame["timestamp_utc"] = pd.to_datetime(
        frame["timestamp_utc"], utc=True
    )
    frame["_chart_session"] = pd.to_datetime(
        frame["session_date"]
    ).dt.normalize()
    frame = frame.loc[frame["_chart_session"] <= cutoff]
    frame = frame.sort_values("timestamp_utc").reset_index(drop=True)
    if frame.empty or not frame["_chart_session"].eq(cutoff).any():
        raise ValueError(f"daily chart history lacks analysis date {analysis_date}")

    overview_start = cutoff - pd.DateOffset(years=2)
    zoom_start = cutoff - pd.DateOffset(months=6)
    overview = frame.loc[frame["_chart_session"] >= overview_start].copy()
    zoom = frame.loc[frame["_chart_session"] >= zoom_start].copy()
    raw_min = float(zoom["low"].min())
    raw_max = float(zoom["high"].max())
    if not math.isfinite(raw_min) or not math.isfinite(raw_max):
        raise ValueError("zoom history contains non-finite high or low")
    if raw_min <= 0 or raw_max < raw_min:
        raise ValueError("zoom history contains invalid high or low")
    span = raw_max - raw_min
    margin = max(span * 0.03, max(abs(raw_min), abs(raw_max)) * 0.005, 0.01)
    return ChartHistory(
        analysis_date=pd.Timestamp(analysis_date).date().isoformat(),
        overview=overview.drop(columns="_chart_session").reset_index(drop=True),
        zoom=zoom.drop(columns="_chart_session").reset_index(drop=True),
        candle_min=raw_min - margin,
        candle_max=raw_max + margin,
    )


def mark_drawn_levels(
    levels: pd.DataFrame,
    candle_min: float,
    candle_max: float,
) -> pd.DataFrame:
    if candle_min >= candle_max:
        raise ValueError("candle range must increase")
    required = {"method", "level_value"}
    missing = sorted(required.difference(levels.columns))
    if missing:
        raise ValueError(f"level table missing columns: {missing}")
    result = levels.copy()
    values = pd.to_numeric(result["level_value"], errors="coerce")
    if not np.isfinite(values).all():
        raise ValueError("level table contains non-finite values")
    structural = result["method"].eq("multi_timeframe")
    classic = result["method"].eq("classic")
    if not (structural | classic).all():
        raise ValueError("level table contains an unsupported method")
    result["drawn_on_chart"] = structural | (
        classic & values.between(candle_min, candle_max, inclusive="both")
    )
    return result
```

- [ ] **Step 4: Run the focused tests and verify green**

Run:

```powershell
$env:PYTHONPATH='.vendor;src'
python -m pytest tests/test_charts.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Commit the pure chart-data layer**

```powershell
git add pyproject.toml src/stock_focus_data/charts.py tests/test_charts.py
git commit -m "feat: select support and resistance chart data"
```

### Task 2: Construct the interactive two-panel Plotly figure

**Files:**
- Modify: `src/stock_focus_data/charts.py`
- Modify: `tests/test_charts.py`

**Interfaces:**
- Consumes: `ChartHistory` and the marked level frame from Task 1.
- Produces: `build_symbol_figure(symbol, history, levels, current_price) -> plotly.graph_objects.Figure`.

- [ ] **Step 1: Install the declared dependency in the local project environment**

Run with the bundled project Python:

```powershell
python -m pip install --disable-pip-version-check --target .vendor "plotly>=6,<7"
```

Expected: Plotly 6.x and its missing dependencies install successfully. Do not commit `.vendor`.

- [ ] **Step 2: Write failing figure-structure and hover tests**

Append to `tests/test_charts.py`:

```python
from stock_focus_data.charts import build_symbol_figure


def complete_level_frame() -> pd.DataFrame:
    frame = chart_level_frame()
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
```

- [ ] **Step 3: Run the new tests and verify red**

Run:

```powershell
$env:PYTHONPATH='.vendor;src'
python -m pytest tests/test_charts.py::test_build_symbol_figure_has_two_panels_and_required_traces tests/test_charts.py::test_build_symbol_figure_keeps_hover_fields_and_level_metadata -q
```

Expected: collection fails because `build_symbol_figure` is not defined.

- [ ] **Step 4: Add the complete figure builder**

Add these imports and definitions to `src/stock_focus_data/charts.py`:

```python
import plotly.graph_objects as go
from plotly.subplots import make_subplots


SIDE_COLORS = {
    "support": "#198754",
    "resistance": "#d62728",
    "pivot": "#2563eb",
}
METHOD_DASHES = {
    "multi_timeframe": "solid",
    "1d": "dash",
    "1w": "dot",
}


def _optional_values(
    frame: pd.DataFrame,
    column: str,
    default: object,
) -> list[object]:
    if column not in frame.columns:
        return [default] * len(frame)
    return frame[column].where(frame[column].notna(), default).tolist()


def _level_width(rank: int) -> float:
    return 2.6 if rank <= 1 else 2.0 if rank == 2 else 1.5


def _level_opacity(rank: int) -> float:
    return 0.92 if rank <= 1 else 0.75 if rank == 2 else 0.58


def build_symbol_figure(
    symbol: str,
    history: ChartHistory,
    levels: pd.DataFrame,
    current_price: float,
) -> go.Figure:
    if not math.isfinite(float(current_price)) or float(current_price) <= 0:
        raise ValueError("current price must be finite and positive")
    if "drawn_on_chart" not in levels.columns:
        raise ValueError("levels must be marked before figure construction")

    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=False,
        row_heights=[0.42, 0.58],
        vertical_spacing=0.09,
        subplot_titles=(
            f"{symbol} retained daily overview",
            f"Six-month daily candlestick through {history.analysis_date}",
        ),
    )
    overview = history.overview
    zoom = history.zoom
    figure.add_trace(
        go.Scatter(
            x=overview["timestamp_utc"],
            y=overview["close"],
            mode="lines",
            name="Close",
            line={"color": "#111827", "width": 2.0},
            hovertemplate="%{x|%Y-%m-%d}<br>Close: %{y:.2f}<extra></extra>",
            meta={"role": "overview_close"},
        ),
        row=1,
        col=1,
    )
    for column, label, color, role in (
        ("sma_50", "SMA 50", "#f59e0b", "overview_sma_50"),
        ("sma_200", "SMA 200", "#7c3aed", "overview_sma_200"),
    ):
        if column in overview.columns and overview[column].notna().any():
            figure.add_trace(
                go.Scatter(
                    x=overview["timestamp_utc"],
                    y=overview[column],
                    mode="lines",
                    name=label,
                    line={"color": color, "width": 1.4},
                    hovertemplate=(
                        f"%{{x|%Y-%m-%d}}<br>{label}: %{{y:.2f}}"
                        "<extra></extra>"
                    ),
                    meta={"role": role},
                ),
                row=1,
                col=1,
            )
    figure.add_trace(
        go.Scatter(
            x=[overview.iloc[-1]["timestamp_utc"]],
            y=[float(current_price)],
            mode="markers",
            name="Analysis close",
            marker={"color": "#2563eb", "size": 9, "symbol": "diamond"},
            hovertemplate=(
                "%{x|%Y-%m-%d}<br>Analysis close: %{y:.2f}<extra></extra>"
            ),
            meta={"role": "analysis_close"},
        ),
        row=1,
        col=1,
    )

    customdata = np.asarray(
        list(
            zip(
                _optional_values(zoom, "volume", 0),
                _optional_values(zoom, "rsi_14", "N/A"),
                _optional_values(zoom, "data_source", "unknown"),
                strict=True,
            )
        ),
        dtype=object,
    )
    figure.add_trace(
        go.Candlestick(
            x=zoom["timestamp_utc"],
            open=zoom["open"],
            high=zoom["high"],
            low=zoom["low"],
            close=zoom["close"],
            name="Daily OHLC",
            increasing={"line": {"color": "#198754"}},
            decreasing={"line": {"color": "#d62728"}},
            customdata=customdata,
            hovertemplate=(
                "<b>%{x|%Y-%m-%d}</b><br>Open: %{open:.2f}"
                "<br>High: %{high:.2f}<br>Low: %{low:.2f}"
                "<br>Close: %{close:.2f}<br>Volume: %{customdata[0]:,.0f}"
                "<br>RSI(14): %{customdata[1]}"
                "<br>Provider: %{customdata[2]}<extra></extra>"
            ),
            meta={"role": "candlestick"},
        ),
        row=2,
        col=1,
    )

    x_start = zoom.iloc[0]["timestamp_utc"]
    x_end = zoom.iloc[-1]["timestamp_utc"]
    drawn = levels.loc[levels["drawn_on_chart"].astype(bool)].copy()
    for record in drawn.to_dict("records"):
        method = str(record["method"])
        timeframe = str(record["reference_timeframe"])
        side = str(record["side"])
        rank = int(record["rank"])
        value = float(record["level_value"])
        distance = float(record["distance_pct"])
        method_label = "Structural" if method == "multi_timeframe" else (
            "Classic daily" if timeframe == "1d" else "Classic weekly"
        )
        label = f"{method_label} {record['level_name']}"
        figure.add_trace(
            go.Scatter(
                x=[x_start, x_end],
                y=[value, value],
                mode="lines",
                name=f"{label} {value:.2f}",
                line={
                    "color": SIDE_COLORS[side],
                    "dash": METHOD_DASHES[
                        method if method == "multi_timeframe" else timeframe
                    ],
                    "width": _level_width(rank),
                },
                opacity=_level_opacity(rank),
                customdata=[[label, distance], [label, distance]],
                hovertemplate=(
                    "%{customdata[0]}<br>Value: %{y:.2f}"
                    "<br>Distance: %{customdata[1]:+.2%}<extra></extra>"
                ),
                meta={
                    "role": "level",
                    "method": method,
                    "reference_timeframe": timeframe,
                    "level_name": str(record["level_name"]),
                },
            ),
            row=2,
            col=1,
        )

    y_values = drawn["level_value"].astype(float).tolist()
    y_min = min([history.candle_min, *y_values])
    y_max = max([history.candle_max, *y_values])
    y_padding = max((y_max - y_min) * 0.02, 0.01)
    figure.update_layout(
        template="plotly_white",
        height=960,
        margin={"l": 60, "r": 30, "t": 75, "b": 55},
        hovermode="closest",
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.03,
            "xanchor": "left",
            "x": 0,
        },
        meta={"symbol": symbol, "analysis_date": history.analysis_date},
    )
    figure.update_xaxes(
        rangebreaks=[{"bounds": ["sat", "mon"]}],
        showgrid=True,
        gridcolor="#e5e7eb",
    )
    figure.update_yaxes(title_text="Price", row=1, col=1)
    figure.update_yaxes(
        title_text="Price",
        range=[y_min - y_padding, y_max + y_padding],
        row=2,
        col=1,
    )
    figure.update_xaxes(rangeslider_visible=False, row=2, col=1)
    return figure
```

- [ ] **Step 5: Run all chart tests and verify green**

Run:

```powershell
$env:PYTHONPATH='.vendor;src'
python -m pytest tests/test_charts.py -q
```

Expected: `6 passed`.

- [ ] **Step 6: Commit figure construction**

```powershell
git add src/stock_focus_data/charts.py tests/test_charts.py
git commit -m "feat: build interactive support and resistance figures"
```

### Task 3: Render deterministic symbol pages and complete level tables

**Files:**
- Modify: `src/stock_focus_data/charts.py`
- Modify: `tests/test_charts.py`

**Interfaces:**
- Consumes: a Plotly `Figure`, marked levels, one compact output row, and adjacent symbols.
- Produces: `render_level_table(levels) -> str` and `render_symbol_page(...) -> str`.

- [ ] **Step 1: Write failing page/table tests**

Append to `tests/test_charts.py`:

```python
from stock_focus_data.config import UniverseEntry
from stock_focus_data.charts import render_level_table, render_symbol_page


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
```

- [ ] **Step 2: Run the page tests and verify red**

Run:

```powershell
$env:PYTHONPATH='.vendor;src'
python -m pytest tests/test_charts.py::test_render_level_table_lists_hidden_classic_levels tests/test_charts.py::test_render_symbol_page_is_offline_escaped_and_deterministic -q
```

Expected: import fails because the render functions are not defined.

- [ ] **Step 3: Implement escaped deterministic page rendering**

Add imports, constants, and functions to `src/stock_focus_data/charts.py`:

```python
import html
from collections.abc import Mapping

import plotly.io as pio

from stock_focus_data.config import UniverseEntry


PAGE_STYLE = """
:root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
body { margin: 0; background: #f4f6f8; color: #111827; }
header, main, footer { max-width: 1680px; margin: 0 auto; padding: 18px 24px; }
header { display: flex; gap: 20px; align-items: center; justify-content: space-between; flex-wrap: wrap; }
nav { display: flex; gap: 12px; }
a { color: #1d4ed8; text-decoration: none; }
a:hover { text-decoration: underline; }
.badges { display: flex; gap: 8px; flex-wrap: wrap; }
.badge { border-radius: 999px; background: #e5e7eb; padding: 5px 10px; font-size: 0.88rem; }
.layout { display: grid; grid-template-columns: minmax(0, 2fr) minmax(360px, 0.8fr); gap: 18px; align-items: start; }
.panel { background: white; border: 1px solid #d1d5db; border-radius: 12px; box-shadow: 0 2px 8px rgb(15 23 42 / 8%); overflow: hidden; }
.table-wrap { max-height: 960px; overflow: auto; }
table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
th, td { border-bottom: 1px solid #e5e7eb; padding: 7px 8px; text-align: right; white-space: nowrap; }
th { position: sticky; top: 0; z-index: 1; background: #f8fafc; }
th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) { text-align: left; }
.support { color: #147a43; }
.resistance { color: #b42318; }
.pivot { color: #1d4ed8; }
.note { color: #4b5563; font-size: 0.9rem; }
@media (max-width: 1100px) { .layout { grid-template-columns: 1fr; } .table-wrap { max-height: none; } }
""".strip()


def _missing(value: object) -> bool:
    return value is None or value is pd.NA or bool(pd.isna(value))


def _text(value: object, fallback: str = "—") -> str:
    return fallback if _missing(value) else html.escape(str(value))


def _price(value: object) -> str:
    return "—" if _missing(value) else f"{float(value):,.2f}"


def _percent(value: object) -> str:
    return "—" if _missing(value) else f"{float(value):+.2%}"


def render_level_table(levels: pd.DataFrame) -> str:
    rows: list[str] = []
    for record in levels.to_dict("records"):
        method = (
            "Structural"
            if record["method"] == "multi_timeframe"
            else "Classic"
        )
        timeframe = (
            "Multi"
            if record["reference_timeframe"] == "multi"
            else str(record["reference_timeframe"])
        )
        drawn = "Drawn" if bool(record["drawn_on_chart"]) else "Not drawn"
        reference = record.get("reference_period_end")
        if _missing(reference):
            reference = record.get("last_touch_utc")
        rows.append(
            "<tr>"
            f'<td>{method}</td><td>{html.escape(timeframe)}</td>'
            f'<td class="{html.escape(str(record["side"]))}">'
            f'{html.escape(str(record["level_name"]))}</td>'
            f'<td>{_price(record["level_value"])}</td>'
            f'<td>{_percent(record["distance_pct"])}</td>'
            f'<td>{_text(record.get("touch_count"))}</td>'
            f'<td>{_price(record.get("strength_score"))}</td>'
            f'<td>{_text(record.get("contributing_timeframes"))}</td>'
            f'<td>{_text(reference)}</td><td>{drawn}</td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>Method</th><th>TF</th><th>Level</th><th>Value</th>"
        "<th>Distance</th><th>Touches</th><th>Strength</th>"
        "<th>Contributors</th><th>Reference</th><th>Chart</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _nav_link(symbol: str | None, label: str) -> str:
    if symbol is None:
        return f'<span aria-disabled="true">{label}</span>'
    safe_symbol = html.escape(symbol)
    return f'<a href="{safe_symbol}.html">{label}</a>'


def render_symbol_page(
    entry: UniverseEntry,
    analysis_date: str,
    compact: Mapping[str, object],
    levels: pd.DataFrame,
    figure: go.Figure,
    previous_symbol: str | None,
    next_symbol: str | None,
    plotly_asset_path: str = "../../assets/plotly.min.js",
) -> str:
    symbol = html.escape(entry.symbol)
    warning = _text(compact.get("warning"), "None")
    plot = pio.to_html(
        figure,
        include_plotlyjs=plotly_asset_path,
        full_html=False,
        div_id=f"support-resistance-{entry.symbol.lower()}",
        config={
            "responsive": True,
            "displaylogo": False,
            "scrollZoom": True,
            "toImageButtonOptions": {
                "format": "png",
                "filename": f"{entry.symbol}-support-resistance-{analysis_date}",
                "height": 960,
                "width": 1500,
                "scale": 2,
            },
        },
    )
    table = render_level_table(levels)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{symbol} support and resistance — {html.escape(analysis_date)}</title>
  <style>{PAGE_STYLE}</style>
</head>
<body>
<header>
  <div>
    <a href="index.html">← All symbols</a>
    <h1>{symbol} support and resistance</h1>
    <div class="badges">
      <span class="badge">Analysis {html.escape(analysis_date)}</span>
      <span class="badge">Close {_price(compact["current_price"])}</span>
      <span class="badge">{_text(compact["calculation_status"])}</span>
    </div>
    <p class="note">Warning: {warning}</p>
  </div>
  <nav>{_nav_link(previous_symbol, "Previous")} {_nav_link(next_symbol, "Next")}</nav>
</header>
<main class="layout">
  <section class="panel" aria-label="Interactive price chart">{plot}</section>
  <section class="panel" aria-label="Complete level table">{table}</section>
</main>
<footer class="note">Research visualization only. Historical levels are not forecasts or trading recommendations.</footer>
</body>
</html>
"""
```

- [ ] **Step 4: Run all chart tests and verify green**

Run:

```powershell
$env:PYTHONPATH='.vendor;src'
python -m pytest tests/test_charts.py -q
```

Expected: `8 passed`.

- [ ] **Step 5: Commit deterministic symbol-page rendering**

```powershell
git add src/stock_focus_data/charts.py tests/test_charts.py
git commit -m "feat: render offline symbol chart pages"
```

### Task 4: Render the searchable index and deterministic manifest

**Files:**
- Modify: `src/stock_focus_data/charts.py`
- Modify: `tests/test_charts.py`

**Interfaces:**
- Consumes: configured entries, compact output rows, analysis date, and per-symbol history ranges.
- Produces: `render_index`, `build_manifest`, and `serialize_manifest`.

- [ ] **Step 1: Write failing index and manifest tests**

Append to `tests/test_charts.py`:

```python
import json

from stock_focus_data.charts import (
    build_manifest,
    render_index,
    serialize_manifest,
)


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
    assert decoded["files"] == ["AMD.html", "SPCX.html", "index.html", "manifest.json"]
    assert [row["symbol"] for row in decoded["symbols"]] == ["AMD", "SPCX"]
    assert "generated_at" not in decoded
```

- [ ] **Step 2: Run the tests and verify red**

Run:

```powershell
$env:PYTHONPATH='.vendor;src'
python -m pytest tests/test_charts.py::test_render_index_is_searchable_and_preserves_universe_order tests/test_charts.py::test_manifest_is_complete_stable_and_has_no_wall_clock_time -q
```

Expected: import fails because the index/manifest functions are not defined.

- [ ] **Step 3: Implement the index and manifest**

Add `json` to the module imports and add:

```python
import json
from collections.abc import Sequence


INDEX_STYLE = """
body { margin: 0; padding: 24px; background: #f4f6f8; color: #111827; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
main { max-width: 1280px; margin: 0 auto; }
input { width: min(100%, 420px); padding: 10px 12px; border: 1px solid #9ca3af; border-radius: 8px; font-size: 1rem; }
.table-wrap { margin-top: 18px; overflow-x: auto; background: white; border: 1px solid #d1d5db; border-radius: 12px; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px 12px; border-bottom: 1px solid #e5e7eb; text-align: right; white-space: nowrap; }
th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) { text-align: left; }
a { color: #1d4ed8; text-decoration: none; }
a:hover { text-decoration: underline; }
.note { color: #4b5563; }
""".strip()


def render_index(
    entries: Sequence[UniverseEntry],
    compact: pd.DataFrame,
    analysis_date: str,
) -> str:
    indexed = compact.set_index("symbol", drop=False)
    rows: list[str] = []
    for entry in entries:
        if entry.symbol not in indexed.index:
            raise ValueError(f"compact chart data missing {entry.symbol}")
        record = indexed.loc[entry.symbol]
        rows.append(
            f'<tr data-symbol="{html.escape(entry.symbol)}">'
            f'<td><a href="{html.escape(entry.symbol)}.html">{html.escape(entry.symbol)}</a></td>'
            f'<td>{html.escape(entry.asset_type)}</td>'
            f'<td>{_price(record["current_price"])}</td>'
            f'<td>{_price(record.get("mt_support_1"))}</td>'
            f'<td>{_price(record.get("mt_resistance_1"))}</td>'
            f'<td>{_price(record.get("daily_pivot"))}</td>'
            f'<td>{_price(record.get("weekly_pivot"))}</td>'
            f'<td>{_text(record["calculation_status"])}</td></tr>'
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Support and resistance charts — {html.escape(analysis_date)}</title>
<style>{INDEX_STYLE}</style></head><body><main>
<h1>Support and resistance charts</h1>
<p class="note">Analysis date {html.escape(analysis_date)} · {len(entries)} symbols · <a href="manifest.json">Manifest</a></p>
<label for="symbol-search">Search symbol</label><br>
<input id="symbol-search" type="search" autocomplete="off" placeholder="AMD, QQQ, SPCX…">
<div class="table-wrap"><table id="symbol-table"><thead><tr>
<th>Symbol</th><th>Type</th><th>Close</th><th>Structural S1</th>
<th>Structural R1</th><th>Daily P</th><th>Weekly P</th><th>Status</th>
</tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p class="note">Research visualization only. Historical levels are not forecasts or trading recommendations.</p>
</main><script>
const search = document.getElementById('symbol-search');
search.addEventListener('input', () => {{
  const query = search.value.trim().toUpperCase();
  document.querySelectorAll('#symbol-table tbody tr').forEach((row) => {{
    row.hidden = !row.dataset.symbol.includes(query);
  }});
}});
</script></body></html>
"""


def build_manifest(
    entries: Sequence[UniverseEntry],
    analysis_date: str,
    history_ranges: Mapping[str, tuple[str, str]],
    levels: int,
) -> dict[str, object]:
    symbols = []
    for entry in entries:
        if entry.symbol not in history_ranges:
            raise ValueError(f"manifest history range missing {entry.symbol}")
        start, end = history_ranges[entry.symbol]
        symbols.append(
            {
                "symbol": entry.symbol,
                "asset_type": entry.asset_type,
                "history_start": start,
                "history_end": end,
                "page": f"{entry.symbol}.html",
            }
        )
    files = sorted([f"{entry.symbol}.html" for entry in entries])
    files.extend(["index.html", "manifest.json"])
    return {
        "schema_version": 1,
        "analysis_date": analysis_date,
        "level_count_per_side": levels,
        "plotly_asset": "../../assets/plotly.min.js",
        "files": files,
        "symbols": symbols,
    }


def serialize_manifest(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
```

- [ ] **Step 4: Run all chart tests and verify green**

Run:

```powershell
$env:PYTHONPATH='.vendor;src'
python -m pytest tests/test_charts.py -q
```

Expected: `10 passed`.

- [ ] **Step 5: Commit the index and manifest**

```powershell
git add src/stock_focus_data/charts.py tests/test_charts.py
git commit -m "feat: add chart index and manifest"
```

### Task 5: Build and publish a complete chart site safely

**Files:**
- Modify: `src/stock_focus_data/charts.py`
- Modify: `tests/test_charts.py`

**Interfaces:**
- Consumes: `build_support_resistance`, configured entries, daily derived files, and all rendering functions from Tasks 1-4.
- Produces: `ChartSiteResult` and `publish_chart_site(data_root, entries, output_root, analysis_date, levels)`.

- [ ] **Step 1: Write failing integration, preservation, and repeatability tests**

Append to `tests/test_charts.py`:

```python
from stock_focus_data.charts import publish_chart_site


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
```

- [ ] **Step 2: Run the integration tests and verify red**

Run:

```powershell
$env:PYTHONPATH='.vendor;src'
python -m pytest tests/test_charts.py::test_publish_chart_site_writes_complete_offline_site tests/test_charts.py::test_publish_chart_site_is_byte_deterministic tests/test_charts.py::test_render_failure_preserves_existing_site -q
```

Expected: import fails because `publish_chart_site` is not defined.

- [ ] **Step 3: Implement site construction and staged publication**

Add imports and definitions to `src/stock_focus_data/charts.py`:

```python
import os
import shutil
import tempfile
from pathlib import Path

from plotly.offline import get_plotlyjs

from stock_focus_data.support_resistance import build_support_resistance


@dataclass(frozen=True, slots=True)
class ChartSiteResult:
    analysis_date: str
    symbol_count: int
    output_directory: Path
    index_path: Path
    manifest_path: Path


@dataclass(frozen=True, slots=True)
class _ChartSiteBundle:
    analysis_date: str
    pages: dict[str, str]
    index_html: str
    manifest_json: str
    plotly_javascript: str


def _history_range(daily: pd.DataFrame, analysis_date: str) -> tuple[str, str]:
    sessions = pd.to_datetime(daily["session_date"])
    sessions = sessions.loc[sessions <= pd.Timestamp(analysis_date)]
    if sessions.empty:
        raise ValueError("daily chart history has no rows through analysis date")
    return sessions.min().date().isoformat(), sessions.max().date().isoformat()


def _build_chart_site(
    data_root: Path,
    entries: Sequence[UniverseEntry],
    analysis_date: str | None,
    levels: int,
) -> _ChartSiteBundle:
    compact, long, selected_date = build_support_resistance(
        data_root,
        entries,
        analysis_date=analysis_date,
        levels=levels,
    )
    compact_by_symbol = compact.set_index("symbol", drop=False)
    pages: dict[str, str] = {}
    history_ranges: dict[str, tuple[str, str]] = {}
    symbols = [entry.symbol for entry in entries]
    for index, entry in enumerate(entries):
        daily_path = data_root / "derived" / f"{entry.symbol}-1d.parquet"
        if not daily_path.exists():
            raise ValueError(f"missing daily chart history for {entry.symbol}")
        daily = pd.read_parquet(daily_path)
        history = select_chart_history(daily, selected_date)
        history_ranges[entry.symbol] = _history_range(daily, selected_date)
        symbol_levels = long.loc[long["symbol"].eq(entry.symbol)].copy()
        symbol_levels = mark_drawn_levels(
            symbol_levels,
            history.candle_min,
            history.candle_max,
        )
        compact_row = compact_by_symbol.loc[entry.symbol].to_dict()
        figure = build_symbol_figure(
            entry.symbol,
            history,
            symbol_levels,
            float(compact_row["current_price"]),
        )
        pages[f"{entry.symbol}.html"] = render_symbol_page(
            entry,
            selected_date,
            compact_row,
            symbol_levels,
            figure,
            previous_symbol=symbols[index - 1] if index > 0 else None,
            next_symbol=symbols[index + 1] if index + 1 < len(symbols) else None,
        )
    manifest = build_manifest(entries, selected_date, history_ranges, levels)
    return _ChartSiteBundle(
        analysis_date=selected_date,
        pages=pages,
        index_html=render_index(entries, compact, selected_date),
        manifest_json=serialize_manifest(manifest),
        plotly_javascript=get_plotlyjs(),
    )


def _replace_directory(staged: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if staged.resolve().parent == target.resolve().parent:
        raise ValueError("staging and target directories must be distinct")
    backup = target.with_name(f".{target.name}.backup")
    if backup.exists():
        raise RuntimeError(f"stale chart backup requires inspection: {backup}")
    if target.exists():
        os.replace(target, backup)
    try:
        os.replace(staged, target)
    except BaseException:
        if backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    if backup.exists():
        if backup.resolve().parent != target.parent.resolve():
            raise RuntimeError("refusing to remove chart backup outside target parent")
        shutil.rmtree(backup)


def publish_chart_site(
    data_root: Path,
    entries: Sequence[UniverseEntry],
    output_root: Path,
    analysis_date: str | None = None,
    levels: int = 3,
) -> ChartSiteResult:
    bundle = _build_chart_site(data_root, entries, analysis_date, levels)
    publication_parent = output_root.parent
    publication_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=publication_parent,
        prefix=".support-resistance-chart-stage-",
    ) as temporary_name:
        temporary = Path(temporary_name)
        staged_site = temporary / bundle.analysis_date
        staged_site.mkdir()
        for name, page in bundle.pages.items():
            (staged_site / name).write_text(page, encoding="utf-8")
        (staged_site / "index.html").write_text(
            bundle.index_html, encoding="utf-8"
        )
        (staged_site / "manifest.json").write_text(
            bundle.manifest_json, encoding="utf-8"
        )
        staged_asset = temporary / "plotly.min.js"
        staged_asset.write_text(bundle.plotly_javascript, encoding="utf-8")

        asset_target = output_root.parent / "assets" / "plotly.min.js"
        asset_target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged_asset, asset_target)
        target = output_root / bundle.analysis_date
        _replace_directory(staged_site, target)
    return ChartSiteResult(
        analysis_date=bundle.analysis_date,
        symbol_count=len(entries),
        output_directory=target,
        index_path=target / "index.html",
        manifest_path=target / "manifest.json",
    )
```

- [ ] **Step 4: Run the chart-module tests and verify green**

Run:

```powershell
$env:PYTHONPATH='.vendor;src'
python -m pytest tests/test_charts.py -q
```

Expected: `13 passed`.

- [ ] **Step 5: Run the pre-existing support/resistance tests as a compatibility checkpoint**

Run:

```powershell
$env:PYTHONPATH='.vendor;src'
python -m pytest tests/test_support_resistance.py tests/test_charts.py -q
```

Expected: all focused tests pass.

- [ ] **Step 6: Commit complete chart-site publication**

```powershell
git add src/stock_focus_data/charts.py tests/test_charts.py
git commit -m "feat: publish complete offline chart sites"
```

### Task 6: Add the chart CLI command

**Files:**
- Modify: `src/stock_focus_data/cli.py:16-20,282-end`
- Modify: `tests/test_cli.py:85-end`

**Interfaces:**
- Consumes: `publish_chart_site` and the existing universe loader.
- Produces: `stock-focus chart-support-resistance`.

- [ ] **Step 1: Write failing CLI tests**

Append to `tests/test_cli.py`:

```python
def test_chart_support_resistance_command_writes_site(tmp_path: Path) -> None:
    root = tmp_path / "data"
    config = tmp_path / "universe.yaml"
    output_root = tmp_path / "charts" / "support_resistance"
    write_cli_fixture(root, config)

    result = CliRunner().invoke(
        app,
        [
            "chart-support-resistance",
            "--root",
            str(root),
            "--config",
            str(config),
            "--output-root",
            str(output_root),
            "--levels",
            "3",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "symbols=1" in result.stdout
    assert "analysis_date=" in result.stdout
    date_directories = [path for path in output_root.iterdir() if path.is_dir()]
    assert len(date_directories) == 1
    assert (date_directories[0] / "AMD.html").exists()
    assert (date_directories[0] / "index.html").exists()


def test_chart_support_resistance_rejects_unshared_date(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    config = tmp_path / "universe.yaml"
    output_root = tmp_path / "charts" / "support_resistance"
    write_cli_fixture(root, config)

    result = CliRunner().invoke(
        app,
        [
            "chart-support-resistance",
            "--root",
            str(root),
            "--config",
            str(config),
            "--output-root",
            str(output_root),
            "--analysis-date",
            "1999-01-01",
        ],
    )

    assert result.exit_code != 0
    assert "not available for every symbol" in result.stdout
    assert not output_root.exists()
```

- [ ] **Step 2: Run the CLI tests and verify red**

Run:

```powershell
$env:PYTHONPATH='.vendor;src'
python -m pytest tests/test_cli.py::test_chart_support_resistance_command_writes_site tests/test_cli.py::test_chart_support_resistance_rejects_unshared_date -q
```

Expected: both fail because the command is not registered.

- [ ] **Step 3: Register the command**

Add the import near the top of `src/stock_focus_data/cli.py`:

```python
from stock_focus_data.charts import publish_chart_site
```

Add the command after `support_resistance`:

```python
@app.command("chart-support-resistance")
def chart_support_resistance(
    root: Path = typer.Option(Path("data")),
    config: Path = typer.Option(Path("config/universe.yaml")),
    output_root: Path = typer.Option(
        Path("charts/support_resistance"),
        "--output-root",
    ),
    analysis_date: str | None = typer.Option(None, "--analysis-date"),
    levels: int = typer.Option(3, min=1, max=10),
) -> None:
    """Generate offline interactive history and level charts."""
    try:
        result = publish_chart_site(
            root,
            load_universe(config),
            output_root,
            analysis_date=analysis_date,
            levels=levels,
        )
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(
        f"analysis_date={result.analysis_date} "
        f"symbols={result.symbol_count} index={result.index_path}"
    )
```

- [ ] **Step 4: Run all CLI tests and verify green**

Run:

```powershell
$env:PYTHONPATH='.vendor;src'
python -m pytest tests/test_cli.py -q
```

Expected: all CLI tests pass, including both chart-command tests.

- [ ] **Step 5: Run a full-suite checkpoint**

Run:

```powershell
$env:PYTHONPATH='.vendor;src'
python -m pytest -q
```

Expected: the original 49 tests plus all new tests pass.

- [ ] **Step 6: Commit the CLI**

```powershell
git add src/stock_focus_data/cli.py tests/test_cli.py
git commit -m "feat: add interactive chart CLI"
```

### Task 7: Document chart generation and use

**Files:**
- Modify: `README.md:58-70`
- Modify: `docs/DATA_USAGE_GUIDE.md:801-end`
- Modify: `docs/superpowers/specs/2026-09-01-support-resistance-charts-design.md:5`

**Interfaces:**
- Consumes: the final command and output contract.
- Produces: concise project instructions and detailed local/Git usage guidance.

- [ ] **Step 1: Add the README workflow**

Extend the support/resistance section in `README.md` with:

```markdown
Generate interactive history charts after refreshing and rebuilding:

```powershell
stock-focus chart-support-resistance --analysis-date 2026-09-01
```

Open `charts/support_resistance/2026-09-01/index.html` in a browser. The index links to one offline interactive chart for every configured symbol; all pages share `charts/assets/plotly.min.js`.
```

- [ ] **Step 2: Add the detailed guide section**

Append a new section to `docs/DATA_USAGE_GUIDE.md` covering exactly:

```markdown
## 27. Interactive support and resistance charts

Run:

```powershell
stock-focus chart-support-resistance --analysis-date 2026-09-01
```

Open locally:

```powershell
Start-Process charts/support_resistance/2026-09-01/index.html
```

After cloning from GitHub, install the package dependencies, run the command when you want to regenerate charts, or open the committed date directory directly. GitHub's source-code preview does not execute repository HTML; download or clone the repository and open `index.html` in a browser.

The upper panel shows up to two years of daily closes with SMA(50) and SMA(200). The lower panel shows six months of daily candlesticks. Hovering a candle shows OHLC, volume, RSI(14), and provider. Every structural level is drawn. Classic daily and weekly levels are drawn only inside the original zoom range, while the table always lists every calculated level.

The pages load the shared local `charts/assets/plotly.min.js`, so they remain interactive without internet access. Regenerate them after refreshing, rebuilding, and recalculating data. These historical levels are research references, not forecasts or trading recommendations.
```

- [ ] **Step 3: Mark the design implemented only after code tests pass**

Change the chart design status to:

```text
Status: implemented, production verification pending
```

- [ ] **Step 4: Verify documentation references and Markdown fences**

Run:

```powershell
Select-String -Path README.md,docs/DATA_USAGE_GUIDE.md -Pattern "chart-support-resistance","plotly.min.js","index.html"
python -c "from pathlib import Path; files=[Path('README.md'),Path('docs/DATA_USAGE_GUIDE.md')]; assert all(p.read_text(encoding='utf-8').count(chr(96)*3)%2==0 for p in files); print('Markdown fences balanced')"
git diff --check
```

Expected: both documents contain the command/output references, fences are balanced, and `git diff --check` exits zero.

- [ ] **Step 5: Commit documentation**

```powershell
git add README.md docs/DATA_USAGE_GUIDE.md docs/superpowers/specs/2026-09-01-support-resistance-charts-design.md
git commit -m "docs: explain interactive support and resistance charts"
```

### Task 8: Generate, validate, visually inspect, commit, push, and open the pull request

**Files:**
- Create: `charts/assets/plotly.min.js`
- Create: `charts/support_resistance/2026-09-01/index.html`
- Create: `charts/support_resistance/2026-09-01/manifest.json`
- Create: `charts/support_resistance/2026-09-01/{SYMBOL}.html` for all 32 symbols
- Modify: `docs/superpowers/specs/2026-09-01-support-resistance-charts-design.md:5`

**Interfaces:**
- Consumes: all refreshed derived histories through 2026-09-01 and the completed CLI.
- Produces: committed production artifacts and a GitHub pull request from `feature/support-resistance-charts` into `main`.

- [ ] **Step 1: Generate the production site**

Run:

```powershell
$env:PYTHONPATH='.vendor;src'
python -c "from stock_focus_data.cli import app; app()" chart-support-resistance --analysis-date 2026-09-01 --levels 3
```

Expected summary:

```text
analysis_date=2026-09-01 symbols=32 index=charts\support_resistance\2026-09-01\index.html
```

- [ ] **Step 2: Run production invariants**

Run this read-only validation:

```powershell
$env:PYTHONPATH='.vendor;src'
$code = @'
from pathlib import Path
import json
import re
from stock_focus_data.config import load_universe

entries = load_universe(Path("config/universe.yaml"))
symbols = [entry.symbol for entry in entries]
root = Path("charts/support_resistance/2026-09-01")
asset = Path("charts/assets/plotly.min.js")
assert asset.exists() and asset.stat().st_size > 1_000_000
manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
assert manifest["analysis_date"] == "2026-09-01"
assert [row["symbol"] for row in manifest["symbols"]] == symbols
assert len(manifest["files"]) == 34
assert (root / "index.html").exists()
for symbol in symbols:
    page = root / f"{symbol}.html"
    assert page.exists()
    text = page.read_text(encoding="utf-8")
    assert f"support-resistance-{symbol.lower()}" in text
    assert "../../assets/plotly.min.js" in text
    assert "cdn.plot.ly" not in text
    assert "Daily OHLC" in text
    assert "Complete level table" in text
index = (root / "index.html").read_text(encoding="utf-8")
links = re.findall(r'href="([A-Z]+\.html)"', index)
assert links == [f"{symbol}.html" for symbol in symbols]
print(f"Production site validation passed: {len(symbols)} symbol pages, offline asset, index, and manifest.")
'@
python -c $code
```

Expected: `Production site validation passed: 32 symbol pages, offline asset, index, and manifest.`

- [ ] **Step 3: Verify byte determinism**

In one PowerShell session, hash project-authored artifacts, regenerate, and compare:

```powershell
$before = Get-ChildItem charts\support_resistance\2026-09-01 -File | Sort-Object Name | ForEach-Object { "{0}:{1}" -f $_.Name,(Get-FileHash $_.FullName -Algorithm SHA256).Hash }
$env:PYTHONPATH='.vendor;src'
python -c "from stock_focus_data.cli import app; app()" chart-support-resistance --analysis-date 2026-09-01 --levels 3
$after = Get-ChildItem charts\support_resistance\2026-09-01 -File | Sort-Object Name | ForEach-Object { "{0}:{1}" -f $_.Name,(Get-FileHash $_.FullName -Algorithm SHA256).Hash }
if (Compare-Object $before $after) { throw "chart output is not deterministic" }
Write-Output "Deterministic chart regeneration passed"
```

Expected: `Deterministic chart regeneration passed`.

- [ ] **Step 4: Run the complete automated verification**

Run:

```powershell
$env:PYTHONPATH='.vendor;src'
python -m pytest -q
python -m compileall -q src
git diff --check
```

Expected: all tests pass, compilation exits zero, and no whitespace errors are reported.

- [ ] **Step 5: Visually inspect representative pages**

Serve the chart root locally:

```powershell
python -m http.server 8765 --directory charts
```

Open and inspect:

```text
http://127.0.0.1:8765/support_resistance/2026-09-01/AMD.html
http://127.0.0.1:8765/support_resistance/2026-09-01/SPCX.html
http://127.0.0.1:8765/support_resistance/2026-09-01/WOLF.html
```

Acceptance checklist for each page:

- Both panels render without console-visible errors.
- Candlestick hover shows OHLC, volume, RSI, and provider.
- Structural solid lines and eligible dashed/dotted classic lines render in the correct colors.
- The level table contains hidden classic values and marks them `Not drawn`.
- AMD uses the full overview, SPCX uses its shorter available history, and WOLF remains readable despite volatile price movement.
- Previous, next, and index links resolve.

- [ ] **Step 6: Mark the design verified and commit the production chart artifacts**

After Steps 1-5 pass, change the chart design status to:

```text
Status: implemented and verified
```

```powershell
git add charts/assets/plotly.min.js charts/support_resistance/2026-09-01 docs/superpowers/specs/2026-09-01-support-resistance-charts-design.md
git commit -m "data: add interactive charts through 2026-09-01"
```

- [ ] **Step 7: Run one final test and repository-state gate before external publication**

Run:

```powershell
$env:PYTHONPATH='.vendor;src'
python -m pytest -q
git status --short --branch
git log --oneline origin/main..HEAD
```

Expected: all tests pass; the working tree is clean; the branch is `feature/support-resistance-charts`; the log contains the original data/level work plus the chart design, implementation, docs, and generated charts.

- [ ] **Step 8: Push the requested branch**

Run:

```powershell
git push -u origin feature/support-resistance-charts
```

Expected: the remote branch is created without force-pushing.

- [ ] **Step 9: Create the requested pull request using the installed GitHub connector**

Call `github_create_pull_request` with:

```json
{
  "repository_full_name": "MOLl02/trade-focus-data",
  "base": "main",
  "head": "feature/support-resistance-charts",
  "title": "Add support/resistance data and interactive stock charts",
  "body": "## Summary\n- refresh hourly/daily/weekly market histories through 2026-09-01\n- calculate multi-timeframe structural levels and classic daily/weekly pivots for all 32 symbols\n- add offline interactive two-panel Plotly charts, searchable index, manifest, tests, and documentation\n\n## Verification\n- full pytest suite\n- deterministic 32-page production regeneration\n- production schema/level/link/offline-asset validation\n- visual inspection of AMD, SPCX, and WOLF\n\nResearch data and visualizations only; no trading execution."
}
```

Expected: GitHub returns an open pull request URL targeting `main`.

- [ ] **Step 10: Verify the remote pull request**

Use the GitHub connector to fetch the created pull request and confirm:

- Base is `main`.
- Head is `feature/support-resistance-charts`.
- Status is open.
- Changed files include `src/stock_focus_data/charts.py`, chart tests, documentation, and the generated chart directory.
- The pull-request URL is included in the final handoff.

---

## Plan self-review record

- Spec coverage: every approved requirement maps to Tasks 1-8, including two panels, full structural overlays, filtered classic overlays, complete tables, offline assets, index, manifest, staging, determinism, documentation, 32 production pages, visual inspection, branch push, and pull request.
- Placeholder scan: the plan contains no incomplete marker, deferred implementation instruction, or unnamed error-handling step. All function names, signatures, files, commands, and expected outcomes are explicit.
- Type consistency: `ChartHistory`, marked level frames, `build_symbol_figure`, renderer inputs, `ChartSiteResult`, and CLI usage retain the same names and types across tasks.
- Scope check: chart generation is one cohesive output pipeline; no independent application or deployment subsystem is included.
