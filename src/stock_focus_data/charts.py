from __future__ import annotations

import html
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

from stock_focus_data.config import UniverseEntry


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
        raise ValueError(
            f"daily chart history lacks analysis date {analysis_date}"
        )

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
    margin = max(
        span * 0.03,
        max(abs(raw_min), abs(raw_max)) * 0.005,
        0.01,
    )
    return ChartHistory(
        analysis_date=pd.Timestamp(analysis_date).date().isoformat(),
        overview=overview.drop(columns="_chart_session").reset_index(
            drop=True
        ),
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
        classic
        & values.between(candle_min, candle_max, inclusive="both")
    )
    return result


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
        method_label = (
            "Structural"
            if method == "multi_timeframe"
            else "Classic daily"
            if timeframe == "1d"
            else "Classic weekly"
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
            f"<td>{method}</td><td>{html.escape(timeframe)}</td>"
            f'<td class="{html.escape(str(record["side"]))}">'
            f'{html.escape(str(record["level_name"]))}</td>'
            f'<td>{_price(record["level_value"])}</td>'
            f'<td>{_percent(record["distance_pct"])}</td>'
            f'<td>{_text(record.get("touch_count"))}</td>'
            f'<td>{_price(record.get("strength_score"))}</td>'
            f'<td>{_text(record.get("contributing_timeframes"))}</td>'
            f"<td>{_text(reference)}</td><td>{drawn}</td>"
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
                "filename": (
                    f"{entry.symbol}-support-resistance-{analysis_date}"
                ),
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
            f'<td><a href="{html.escape(entry.symbol)}.html">'
            f"{html.escape(entry.symbol)}</a></td>"
            f"<td>{html.escape(entry.asset_type)}</td>"
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
