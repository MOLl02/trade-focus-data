from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
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
