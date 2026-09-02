# Support and Resistance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Calculate multi-timeframe structural support/resistance and classic daily/weekly pivot levels for every configured symbol, expose the calculation through the CLI, and generate verified CSV and Parquet outputs from the data through 2026-09-01.

**Architecture:** Add one pure calculation module with small functions for classic formulas, swing discovery, clustering, level selection, per-symbol assembly, and universe coordination. Keep file writes and CLI argument handling in `cli.py`; keep calculated outputs separate from candle histories and restrict summary discovery to timeframe history filenames.

**Tech Stack:** Python 3.11+, pandas 2.2+, NumPy, PyArrow/Parquet, Typer, pytest, YAML universe configuration.

## Global Constraints

- Implement both approved methods: multi-timeframe structural levels and traditional classic pivots.
- Structural lookbacks are 90 calendar days for `1h`, 365 calendar days for `1d`, and all retained completed `1w` rows.
- Swing confirmation windows are 3 bars on each side for `1h` and `1d`, and 2 bars on each side for `1w`.
- Timeframe base weights are `1h=1.0`, `1d=2.0`, and `1w=3.0`; recency half-lives are 30, 90, and 180 days respectively.
- Cluster tolerance is `max(current_price * 0.005, daily_atr_14 * 0.25)`; fall back to `current_price * 0.005` when ATR is unavailable.
- Default to three supports and three resistances; accept 1 through 10 through the CLI.
- Daily pivots use the common analysis-date bar; weekly pivots use the latest completed week ending on or before that date.
- Never use source rows after the analysis date or weekly rows where `is_complete` is false.
- Do not fabricate missing structural levels; use null compact fields and absent long-form rows.
- Preserve universe order in `data/latest/support_resistance.csv`.
- Write `data/latest/support_resistance.csv` and `data/derived/support_resistance_levels.parquet`.
- Add no runtime dependencies and do not place trades or publish to GitHub.
- Follow red-green TDD: every production behavior starts with a test that is observed failing for the intended reason.

---

## File Structure

- Create `src/stock_focus_data/support_resistance.py`: all pure formulas, swing detection, clustering, selection, per-symbol assembly, common-date selection, and universe building.
- Create `tests/test_support_resistance.py`: focused unit and repository-builder tests using synthetic frames.
- Modify `src/stock_focus_data/cli.py`: add the command, atomic output writing, and history-only summary discovery.
- Modify `tests/test_cli.py`: command success/failure, output writing, and summary compatibility tests.
- Modify `README.md`: command and output overview.
- Modify `docs/DATA_USAGE_GUIDE.md`: formulas, schemas, loading examples, interpretation, and limitations.
- Generate `data/latest/support_resistance.csv`: 32-row compact result.
- Generate `data/derived/support_resistance_levels.parquet`: long-form levels.

---

### Task 1: Classic Pivot Formulas

**Files:**
- Create: `src/stock_focus_data/support_resistance.py`
- Create: `tests/test_support_resistance.py`

**Interfaces:**
- Consumes: finite numeric reference high, low, and close values.
- Produces: `classic_pivots(high: float, low: float, close: float) -> dict[str, float]` with keys `pivot`, `s1`, `s2`, `s3`, `r1`, `r2`, `r3`.

- [ ] **Step 1: Write the failing formula and validation tests**

Create `tests/test_support_resistance.py` with:

```python
import math

import numpy as np
import pandas as pd
import pytest

from stock_focus_data.support_resistance import classic_pivots


def test_classic_pivots_match_known_values() -> None:
    result = classic_pivots(high=110.0, low=90.0, close=100.0)

    assert result == {
        "pivot": 100.0,
        "s1": 90.0,
        "s2": 80.0,
        "s3": 70.0,
        "r1": 110.0,
        "r2": 120.0,
        "r3": 130.0,
    }


@pytest.mark.parametrize(
    ("high", "low", "close"),
    [
        (90.0, 110.0, 100.0),
        (110.0, 90.0, 120.0),
        (110.0, 90.0, 80.0),
        (np.nan, 90.0, 100.0),
        (110.0, np.inf, 100.0),
    ],
)
def test_classic_pivots_reject_invalid_reference_prices(
    high: float,
    low: float,
    close: float,
) -> None:
    with pytest.raises(ValueError, match="invalid pivot reference"):
        classic_pivots(high=high, low=low, close=close)
```

- [ ] **Step 2: Run the tests and verify the missing-module failure**

Run:

```powershell
python -m pytest tests/test_support_resistance.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'stock_focus_data.support_resistance'`.

- [ ] **Step 3: Implement the exact classic formulas**

Create `src/stock_focus_data/support_resistance.py` with:

```python
from __future__ import annotations

import math


def classic_pivots(high: float, low: float, close: float) -> dict[str, float]:
    values = (float(high), float(low), float(close))
    high_value, low_value, close_value = values
    if (
        not all(math.isfinite(value) for value in values)
        or high_value < low_value
        or not low_value <= close_value <= high_value
    ):
        raise ValueError("invalid pivot reference high, low, or close")

    pivot = (high_value + low_value + close_value) / 3.0
    spread = high_value - low_value
    return {
        "pivot": pivot,
        "s1": 2.0 * pivot - high_value,
        "s2": pivot - spread,
        "s3": low_value - 2.0 * (high_value - pivot),
        "r1": 2.0 * pivot - low_value,
        "r2": pivot + spread,
        "r3": high_value + 2.0 * (pivot - low_value),
    }
```

- [ ] **Step 4: Run the focused tests and verify green**

Run:

```powershell
python -m pytest tests/test_support_resistance.py -q
```

Expected: `6 passed`.

- [ ] **Step 5: Commit the formula increment**

```powershell
git add src/stock_focus_data/support_resistance.py tests/test_support_resistance.py
git commit -m "feat: add classic pivot calculations"
```

---

### Task 2: Confirmed Multi-Timeframe Swing Candidates

**Files:**
- Modify: `src/stock_focus_data/support_resistance.py`
- Modify: `tests/test_support_resistance.py`

**Interfaces:**
- Consumes: one indicator-enriched history frame, timeframe code, and ISO analysis date.
- Produces: `find_swing_candidates(frame: pd.DataFrame, timeframe: str, analysis_date: str) -> pd.DataFrame` with `price`, `timestamp_utc`, `timeframe`, `origin_kind`, and `candidate_weight` fields.

- [ ] **Step 1: Add a reusable synthetic-frame helper and failing swing tests**

Append to `tests/test_support_resistance.py`:

```python
from stock_focus_data.support_resistance import find_swing_candidates


def price_frame(
    timeframe: str,
    dates: list[str],
    highs: list[float],
    lows: list[float],
    closes: list[float] | None = None,
    complete: list[bool] | None = None,
) -> pd.DataFrame:
    close_values = closes if closes is not None else [
        (high + low) / 2.0 for high, low in zip(highs, lows, strict=True)
    ]
    timestamps = pd.to_datetime(dates, utc=True)
    frame = pd.DataFrame(
        {
            "symbol": "AMD",
            "timeframe": timeframe,
            "timestamp_utc": timestamps,
            "session_date": timestamps.strftime("%Y-%m-%d"),
            "open": close_values,
            "high": highs,
            "low": lows,
            "close": close_values,
            "volume": 1000,
            "atr_14": 2.0,
        }
    )
    if complete is not None:
        frame["is_complete"] = complete
    return frame


def test_find_swing_candidates_requires_strict_confirmed_window() -> None:
    frame = price_frame(
        "1d",
        [
            "2026-01-01",
            "2026-01-02",
            "2026-01-03",
            "2026-01-04",
            "2026-01-05",
            "2026-01-06",
            "2026-01-07",
        ],
        highs=[10, 11, 12, 20, 12, 11, 10],
        lows=[8, 7, 6, 1, 6, 7, 8],
    )

    result = find_swing_candidates(frame, "1d", "2026-01-07")

    assert result[["price", "origin_kind"]].to_dict("records") == [
        {"price": 1.0, "origin_kind": "swing_low"},
        {"price": 20.0, "origin_kind": "swing_high"},
    ]
    assert set(result["timeframe"]) == {"1d"}
    assert result["candidate_weight"].gt(0).all()


def test_find_swing_candidates_excludes_edges_ties_and_future_rows() -> None:
    frame = price_frame(
        "1d",
        pd.date_range("2026-01-01", periods=9, tz="UTC").astype(str).tolist(),
        highs=[30, 11, 12, 20, 20, 12, 11, 10, 40],
        lows=[0, 7, 6, 1, 1, 6, 7, 8, -5],
    )

    result = find_swing_candidates(frame, "1d", "2026-01-08")

    assert result.empty


def test_find_swing_candidates_excludes_incomplete_week() -> None:
    dates = pd.date_range("2025-11-07", periods=7, freq="W-FRI", tz="UTC")
    frame = price_frame(
        "1w",
        dates.astype(str).tolist(),
        highs=[10, 11, 20, 11, 10, 9, 30],
        lows=[8, 7, 1, 7, 8, 9, 0],
        complete=[True, True, True, True, True, True, False],
    )

    result = find_swing_candidates(frame, "1w", "2025-12-19")

    assert set(result["timestamp_utc"]) == {dates[2]}
    assert set(result["origin_kind"]) == {"swing_low", "swing_high"}
```

- [ ] **Step 2: Run the focused swing tests and verify red**

Run:

```powershell
python -m pytest tests/test_support_resistance.py -q
```

Expected: import fails because `find_swing_candidates` is not defined.

- [ ] **Step 3: Implement timeframe settings, cutoff handling, and strict pivots**

Add these imports and definitions to `support_resistance.py`:

```python
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class SwingSettings:
    lookback_days: int | None
    window: int
    base_weight: float
    half_life_days: float


SWING_SETTINGS = {
    "1h": SwingSettings(90, 3, 1.0, 30.0),
    "1d": SwingSettings(365, 3, 2.0, 90.0),
    "1w": SwingSettings(None, 2, 3.0, 180.0),
}

CANDIDATE_COLUMNS = [
    "price",
    "timestamp_utc",
    "timeframe",
    "origin_kind",
    "candidate_weight",
]


def find_swing_candidates(
    frame: pd.DataFrame,
    timeframe: str,
    analysis_date: str,
) -> pd.DataFrame:
    if timeframe not in SWING_SETTINGS:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    if frame.empty:
        return pd.DataFrame(columns=CANDIDATE_COLUMNS)

    settings = SWING_SETTINGS[timeframe]
    cutoff = pd.Timestamp(analysis_date).date()
    result = frame.copy()
    result["timestamp_utc"] = pd.to_datetime(
        result["timestamp_utc"], utc=True
    )
    result["_session_date"] = pd.to_datetime(
        result["session_date"]
    ).dt.date
    result = result.loc[result["_session_date"] <= cutoff]
    if timeframe == "1w" and "is_complete" in result.columns:
        result = result.loc[result["is_complete"].fillna(False)]
    if settings.lookback_days is not None:
        start = cutoff - pd.Timedelta(days=settings.lookback_days)
        result = result.loc[result["_session_date"] >= start]
    result = result.sort_values("timestamp_utc").reset_index(drop=True)

    lows = pd.to_numeric(result["low"], errors="coerce").to_numpy(float)
    highs = pd.to_numeric(result["high"], errors="coerce").to_numpy(float)
    rows: list[dict[str, object]] = []
    width = settings.window
    for index in range(width, len(result) - width):
        neighbor_indexes = [
            position
            for position in range(index - width, index + width + 1)
            if position != index
        ]
        session_date = result.iloc[index]["_session_date"]
        age_days = max((cutoff - session_date).days, 0)
        recency = 0.5 ** (age_days / settings.half_life_days)
        weight = settings.base_weight * recency
        timestamp = result.iloc[index]["timestamp_utc"]
        if np.isfinite(lows[index]) and lows[index] < np.min(lows[neighbor_indexes]):
            rows.append(
                {
                    "price": float(lows[index]),
                    "timestamp_utc": timestamp,
                    "timeframe": timeframe,
                    "origin_kind": "swing_low",
                    "candidate_weight": weight,
                }
            )
        if np.isfinite(highs[index]) and highs[index] > np.max(highs[neighbor_indexes]):
            rows.append(
                {
                    "price": float(highs[index]),
                    "timestamp_utc": timestamp,
                    "timeframe": timeframe,
                    "origin_kind": "swing_high",
                    "candidate_weight": weight,
                }
            )
    return pd.DataFrame(rows, columns=CANDIDATE_COLUMNS)
```

- [ ] **Step 4: Run focused and existing indicator tests**

Run:

```powershell
python -m pytest tests/test_support_resistance.py tests/test_indicators.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit the swing increment**

```powershell
git add src/stock_focus_data/support_resistance.py tests/test_support_resistance.py
git commit -m "feat: detect confirmed multi-timeframe swings"
```

---

### Task 3: Volatility-Aware Clustering and Nearest-Level Ranking

**Files:**
- Modify: `src/stock_focus_data/support_resistance.py`
- Modify: `tests/test_support_resistance.py`

**Interfaces:**
- Consumes: candidate frame, current price, optional daily ATR, and requested count.
- Produces: `clustering_tolerance`, `cluster_candidates`, and `select_nearest_levels` with deterministic cluster metadata and side/rank fields.

- [ ] **Step 1: Add failing tolerance, clustering, and ordering tests**

Append to the test file:

```python
from stock_focus_data.support_resistance import (
    cluster_candidates,
    clustering_tolerance,
    select_nearest_levels,
)


def test_clustering_tolerance_uses_larger_price_or_atr_scale() -> None:
    assert clustering_tolerance(100.0, 1.0) == 0.5
    assert clustering_tolerance(100.0, 8.0) == 2.0
    assert clustering_tolerance(100.0, np.nan) == 0.5


def test_cluster_candidates_calculates_weighted_level_and_metadata() -> None:
    candidates = pd.DataFrame(
        [
            {
                "price": 90.0,
                "timestamp_utc": pd.Timestamp("2026-08-01T00:00:00Z"),
                "timeframe": "1h",
                "origin_kind": "swing_low",
                "candidate_weight": 1.0,
            },
            {
                "price": 90.4,
                "timestamp_utc": pd.Timestamp("2026-08-20T00:00:00Z"),
                "timeframe": "1w",
                "origin_kind": "swing_high",
                "candidate_weight": 3.0,
            },
            {
                "price": 95.0,
                "timestamp_utc": pd.Timestamp("2026-08-25T00:00:00Z"),
                "timeframe": "1d",
                "origin_kind": "swing_low",
                "candidate_weight": 2.0,
            },
        ]
    )

    result = cluster_candidates(candidates, current_price=100.0, atr_14=2.0)

    assert len(result) == 2
    first = result.iloc[0]
    assert math.isclose(first["level_value"], 90.3)
    assert first["touch_count"] == 2
    assert first["strength_score"] == 4.0
    assert first["contributing_timeframes"] == "1h|1w"
    assert first["swing_low_count"] == 1
    assert first["swing_high_count"] == 1
    assert first["last_touch_utc"] == pd.Timestamp("2026-08-20T00:00:00Z")


def test_select_nearest_levels_orders_each_side_by_distance() -> None:
    clusters = pd.DataFrame(
        {
            "level_value": [90.0, 95.0, 99.0, 101.0, 105.0, 110.0],
            "touch_count": [1, 1, 1, 1, 1, 1],
            "strength_score": [1.0] * 6,
            "contributing_timeframes": ["1d"] * 6,
            "last_touch_utc": [pd.Timestamp("2026-08-01T00:00:00Z")] * 6,
            "swing_low_count": [1] * 6,
            "swing_high_count": [0] * 6,
        }
    )

    result = select_nearest_levels(clusters, current_price=100.0, count=2)

    assert result.loc[result["side"] == "support", "level_value"].tolist() == [
        99.0,
        95.0,
    ]
    assert result.loc[
        result["side"] == "resistance", "level_value"
    ].tolist() == [101.0, 105.0]
    assert result.groupby("side")["rank"].apply(list).to_dict() == {
        "resistance": [1, 2],
        "support": [1, 2],
    }
    assert result.loc[result["side"] == "support", "distance_pct"].lt(0).all()
    assert result.loc[result["side"] == "resistance", "distance_pct"].gt(0).all()


@pytest.mark.parametrize("count", [0, 11])
def test_select_nearest_levels_rejects_invalid_count(count: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 10"):
        select_nearest_levels(pd.DataFrame(), 100.0, count)
```

- [ ] **Step 2: Run the focused tests and verify missing-function failures**

Run:

```powershell
python -m pytest tests/test_support_resistance.py -q
```

Expected: import fails for the new clustering functions.

- [ ] **Step 3: Implement deterministic clustering and selection**

Add to `support_resistance.py`:

```python
CLUSTER_COLUMNS = [
    "level_value",
    "touch_count",
    "strength_score",
    "contributing_timeframes",
    "last_touch_utc",
    "swing_low_count",
    "swing_high_count",
    "cluster_tolerance",
]

TIMEFRAME_ORDER = {"1h": 0, "1d": 1, "1w": 2}


def clustering_tolerance(current_price: float, atr_14: float | None) -> float:
    price = float(current_price)
    if not math.isfinite(price) or price <= 0:
        raise ValueError("current price must be finite and positive")
    atr = float(atr_14) if atr_14 is not None else math.nan
    atr_component = atr * 0.25 if math.isfinite(atr) and atr >= 0 else 0.0
    return max(price * 0.005, atr_component)


def cluster_candidates(
    candidates: pd.DataFrame,
    current_price: float,
    atr_14: float | None,
) -> pd.DataFrame:
    tolerance = clustering_tolerance(current_price, atr_14)
    if candidates.empty:
        return pd.DataFrame(columns=CLUSTER_COLUMNS)
    ordered = candidates.sort_values(
        ["price", "timestamp_utc", "timeframe", "origin_kind"]
    ).reset_index(drop=True)
    clusters: list[dict[str, object]] = []
    for record in ordered.to_dict("records"):
        price = float(record["price"])
        weight = float(record["candidate_weight"])
        if not math.isfinite(price) or not math.isfinite(weight) or weight <= 0:
            continue
        if not clusters or abs(
            price
            - float(clusters[-1]["weighted_price_sum"])
            / float(clusters[-1]["weight_sum"])
        ) > tolerance:
            clusters.append(
                {
                    "weighted_price_sum": price * weight,
                    "weight_sum": weight,
                    "members": [record],
                }
            )
        else:
            clusters[-1]["weighted_price_sum"] = (
                float(clusters[-1]["weighted_price_sum"]) + price * weight
            )
            clusters[-1]["weight_sum"] = float(clusters[-1]["weight_sum"]) + weight
            members = clusters[-1]["members"]
            if not isinstance(members, list):
                raise TypeError("cluster members must be a list")
            members.append(record)

    rows: list[dict[str, object]] = []
    for cluster in clusters:
        members = list(cluster["members"])
        timeframes = sorted(
            {str(member["timeframe"]) for member in members},
            key=TIMEFRAME_ORDER.__getitem__,
        )
        rows.append(
            {
                "level_value": float(cluster["weighted_price_sum"])
                / float(cluster["weight_sum"]),
                "touch_count": len(members),
                "strength_score": float(cluster["weight_sum"]),
                "contributing_timeframes": "|".join(timeframes),
                "last_touch_utc": max(member["timestamp_utc"] for member in members),
                "swing_low_count": sum(
                    member["origin_kind"] == "swing_low" for member in members
                ),
                "swing_high_count": sum(
                    member["origin_kind"] == "swing_high" for member in members
                ),
                "cluster_tolerance": tolerance,
            }
        )
    return pd.DataFrame(rows, columns=CLUSTER_COLUMNS).sort_values(
        "level_value"
    ).reset_index(drop=True)


def select_nearest_levels(
    clusters: pd.DataFrame,
    current_price: float,
    count: int = 3,
) -> pd.DataFrame:
    if count < 1 or count > 10:
        raise ValueError("level count must be between 1 and 10")
    output_columns = [*CLUSTER_COLUMNS, "side", "rank", "distance_pct"]
    if clusters.empty:
        return pd.DataFrame(columns=output_columns)
    support = (
        clusters.loc[clusters["level_value"] < current_price]
        .sort_values("level_value", ascending=False)
        .head(count)
        .copy()
    )
    resistance = (
        clusters.loc[clusters["level_value"] > current_price]
        .sort_values("level_value")
        .head(count)
        .copy()
    )
    support["side"] = "support"
    resistance["side"] = "resistance"
    support["rank"] = range(1, len(support) + 1)
    resistance["rank"] = range(1, len(resistance) + 1)
    result = pd.concat([support, resistance], ignore_index=True)
    result["distance_pct"] = result["level_value"] / float(current_price) - 1.0
    return result[output_columns]
```

- [ ] **Step 4: Run clustering tests and the full focused module**

Run:

```powershell
python -m pytest tests/test_support_resistance.py -q
```

Expected: all focused tests pass.

- [ ] **Step 5: Commit the clustering increment**

```powershell
git add src/stock_focus_data/support_resistance.py tests/test_support_resistance.py
git commit -m "feat: cluster and rank structural price levels"
```

---

### Task 4: Per-Symbol Compact and Long-Form Results

**Files:**
- Modify: `src/stock_focus_data/support_resistance.py`
- Modify: `tests/test_support_resistance.py`

**Interfaces:**
- Consumes: one symbol's hourly, daily, and weekly frames plus analysis date and level count.
- Produces: `calculate_symbol_levels(...) -> tuple[dict[str, object], list[dict[str, object]]]`, `compact_columns(levels)`, and `LONG_COLUMNS`.

- [ ] **Step 1: Add failing per-symbol output tests**

Append:

```python
from stock_focus_data.support_resistance import (
    LONG_COLUMNS,
    calculate_symbol_levels,
    compact_columns,
)


def test_calculate_symbol_levels_builds_classic_and_structural_outputs() -> None:
    daily_dates = pd.date_range("2025-12-01", periods=20, freq="B", tz="UTC")
    daily = price_frame(
        "1d",
        daily_dates.astype(str).tolist(),
        highs=[110 + index % 5 for index in range(20)],
        lows=[90 - index % 4 for index in range(20)],
        closes=[100 + index * 0.1 for index in range(20)],
    )
    daily.loc[daily.index[-1], ["high", "low", "close", "atr_14"]] = [
        110.0,
        90.0,
        100.0,
        4.0,
    ]
    hourly_dates = pd.date_range("2025-12-01", periods=21, freq="h", tz="UTC")
    hourly = price_frame(
        "1h",
        hourly_dates.astype(str).tolist(),
        highs=[100, 101, 102, 110, 102, 101, 100] * 3,
        lows=[98, 97, 96, 90, 96, 97, 98] * 3,
    )
    weekly_dates = pd.date_range("2025-10-31", periods=8, freq="W-FRI", tz="UTC")
    weekly = price_frame(
        "1w",
        weekly_dates.astype(str).tolist(),
        highs=[108, 109, 120, 109, 108, 107, 130, 140],
        lows=[92, 91, 80, 91, 92, 93, 70, 60],
        closes=[100, 100, 100, 100, 100, 100, 100, 100],
        complete=[True, True, True, True, True, True, False, False],
    )

    compact, long_rows = calculate_symbol_levels(
        "AMD", hourly, daily, weekly, daily_dates[-1].date().isoformat(), levels=3
    )
    long = pd.DataFrame(long_rows, columns=LONG_COLUMNS)

    assert compact["symbol"] == "AMD"
    assert compact["current_price"] == 100.0
    assert compact["daily_pivot"] == 100.0
    assert compact["daily_s1"] == 90.0
    assert compact["daily_r1"] == 110.0
    assert compact["weekly_reference_period_end"] == weekly_dates[5].date().isoformat()
    assert compact["calculation_status"] == "complete"
    assert set(long["method"]) == {"classic", "multi_timeframe"}
    assert set(long.loc[long["method"] == "classic", "reference_timeframe"]) == {
        "1d",
        "1w",
    }
    assert list(compact) == compact_columns(3)


def test_calculate_symbol_levels_marks_missing_optional_history_partial() -> None:
    daily = price_frame(
        "1d",
        ["2026-09-01"],
        highs=[110.0],
        lows=[90.0],
        closes=[100.0],
    )

    compact, long_rows = calculate_symbol_levels(
        "AMD",
        pd.DataFrame(),
        daily,
        pd.DataFrame(),
        "2026-09-01",
        levels=3,
    )

    assert compact["calculation_status"] == "partial"
    assert compact["warning"] == "missing_hourly|missing_completed_weekly"
    assert compact["daily_pivot"] == 100.0
    assert pd.isna(compact["weekly_pivot"])
    assert {row["reference_timeframe"] for row in long_rows} == {"1d"}
```

- [ ] **Step 2: Run the per-symbol tests and verify red**

Run:

```powershell
python -m pytest tests/test_support_resistance.py -q
```

Expected: import fails for `calculate_symbol_levels`, `compact_columns`, or `LONG_COLUMNS`.

- [ ] **Step 3: Implement schemas, reference selection, and row assembly**

Add these constants and helpers to `support_resistance.py`:

```python
LONG_COLUMNS = [
    "symbol",
    "analysis_date",
    "current_price",
    "method",
    "reference_timeframe",
    "level_name",
    "side",
    "rank",
    "level_value",
    "distance_pct",
    "touch_count",
    "strength_score",
    "contributing_timeframes",
    "last_touch_utc",
    "reference_period_end",
]


def compact_columns(levels: int = 3) -> list[str]:
    columns = [
        "symbol",
        "analysis_date",
        "current_price",
        "price_timestamp_utc",
        "calculation_status",
        "warning",
    ]
    for side in ("support", "resistance"):
        for rank in range(1, levels + 1):
            prefix = f"mt_{side}_{rank}"
            columns.extend(
                [
                    prefix,
                    f"{prefix}_distance_pct",
                    f"{prefix}_touch_count",
                    f"{prefix}_strength_score",
                    f"{prefix}_timeframes",
                    f"{prefix}_last_touch_utc",
                ]
            )
    columns.extend(
        [
            "daily_reference_date",
            "daily_pivot",
            "daily_s1",
            "daily_s2",
            "daily_s3",
            "daily_r1",
            "daily_r2",
            "daily_r3",
            "weekly_reference_period_end",
            "weekly_pivot",
            "weekly_s1",
            "weekly_s2",
            "weekly_s3",
            "weekly_r1",
            "weekly_r2",
            "weekly_r3",
        ]
    )
    return columns


def _classic_long_rows(
    symbol: str,
    analysis_date: str,
    current_price: float,
    timeframe: str,
    reference_period_end: str,
    pivots: dict[str, float],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for name in ("pivot", "s1", "s2", "s3", "r1", "r2", "r3"):
        side = "pivot" if name == "pivot" else "support" if name.startswith("s") else "resistance"
        rank = 0 if name == "pivot" else int(name[1])
        value = pivots[name]
        rows.append(
            {
                "symbol": symbol,
                "analysis_date": analysis_date,
                "current_price": current_price,
                "method": "classic",
                "reference_timeframe": timeframe,
                "level_name": name.upper() if name != "pivot" else "P",
                "side": side,
                "rank": rank,
                "level_value": value,
                "distance_pct": value / current_price - 1.0,
                "touch_count": pd.NA,
                "strength_score": pd.NA,
                "contributing_timeframes": pd.NA,
                "last_touch_utc": pd.NaT,
                "reference_period_end": reference_period_end,
            }
        )
    return rows
```

Implement `calculate_symbol_levels` with this behavior:

```python
def calculate_symbol_levels(
    symbol: str,
    hourly: pd.DataFrame,
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    analysis_date: str,
    levels: int = 3,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    if levels < 1 or levels > 10:
        raise ValueError("level count must be between 1 and 10")
    target = daily.loc[daily["session_date"].astype(str) == analysis_date]
    if len(target) != 1:
        raise ValueError(f"{symbol} requires one daily row on {analysis_date}")
    daily_row = target.iloc[0]
    current_price = float(daily_row["close"])
    daily_pivots = classic_pivots(
        float(daily_row["high"]),
        float(daily_row["low"]),
        current_price,
    )
    atr_value = daily_row.get("atr_14", math.nan)

    warnings: list[str] = []
    if hourly.empty:
        warnings.append("missing_hourly")
    completed_weekly = weekly.copy()
    if not completed_weekly.empty:
        completed_weekly = completed_weekly.loc[
            completed_weekly["session_date"].astype(str) <= analysis_date
        ]
        if "is_complete" in completed_weekly.columns:
            completed_weekly = completed_weekly.loc[
                completed_weekly["is_complete"].fillna(False)
            ]
    if completed_weekly.empty:
        warnings.append("missing_completed_weekly")

    candidate_frames = [
        find_swing_candidates(hourly, "1h", analysis_date),
        find_swing_candidates(daily, "1d", analysis_date),
        find_swing_candidates(completed_weekly, "1w", analysis_date),
    ]
    candidates = pd.concat(candidate_frames, ignore_index=True)
    clusters = cluster_candidates(candidates, current_price, atr_value)
    selected = select_nearest_levels(clusters, current_price, levels)

    compact: dict[str, object] = {
        column: pd.NA for column in compact_columns(levels)
    }
    compact.update(
        {
            "symbol": symbol,
            "analysis_date": analysis_date,
            "current_price": current_price,
            "price_timestamp_utc": daily_row["timestamp_utc"],
            "calculation_status": "partial" if warnings else "complete",
            "warning": "|".join(warnings),
            "daily_reference_date": analysis_date,
        }
    )
    for name, value in daily_pivots.items():
        compact[f"daily_{name}"] = value

    long_rows = _classic_long_rows(
        symbol,
        analysis_date,
        current_price,
        "1d",
        analysis_date,
        daily_pivots,
    )
    if not completed_weekly.empty:
        weekly_row = completed_weekly.sort_values("timestamp_utc").iloc[-1]
        weekly_reference = str(weekly_row["session_date"])
        weekly_pivots = classic_pivots(
            float(weekly_row["high"]),
            float(weekly_row["low"]),
            float(weekly_row["close"]),
        )
        compact["weekly_reference_period_end"] = weekly_reference
        for name, value in weekly_pivots.items():
            compact[f"weekly_{name}"] = value
        long_rows.extend(
            _classic_long_rows(
                symbol,
                analysis_date,
                current_price,
                "1w",
                weekly_reference,
                weekly_pivots,
            )
        )

    for record in selected.to_dict("records"):
        side = str(record["side"])
        rank = int(record["rank"])
        prefix = f"mt_{side}_{rank}"
        compact[prefix] = record["level_value"]
        compact[f"{prefix}_distance_pct"] = record["distance_pct"]
        compact[f"{prefix}_touch_count"] = record["touch_count"]
        compact[f"{prefix}_strength_score"] = record["strength_score"]
        compact[f"{prefix}_timeframes"] = record["contributing_timeframes"]
        compact[f"{prefix}_last_touch_utc"] = record["last_touch_utc"]
        long_rows.append(
            {
                "symbol": symbol,
                "analysis_date": analysis_date,
                "current_price": current_price,
                "method": "multi_timeframe",
                "reference_timeframe": "multi",
                "level_name": ("S" if side == "support" else "R") + str(rank),
                "side": side,
                "rank": rank,
                "level_value": record["level_value"],
                "distance_pct": record["distance_pct"],
                "touch_count": record["touch_count"],
                "strength_score": record["strength_score"],
                "contributing_timeframes": record["contributing_timeframes"],
                "last_touch_utc": record["last_touch_utc"],
                "reference_period_end": pd.NA,
            }
        )
    return {column: compact[column] for column in compact_columns(levels)}, long_rows
```

- [ ] **Step 4: Run per-symbol and full focused tests**

Run:

```powershell
python -m pytest tests/test_support_resistance.py -q
```

Expected: all focused tests pass.

- [ ] **Step 5: Commit the per-symbol increment**

```powershell
git add src/stock_focus_data/support_resistance.py tests/test_support_resistance.py
git commit -m "feat: assemble symbol support and resistance outputs"
```

---

### Task 5: Latest Common Date and Universe Builder

**Files:**
- Modify: `src/stock_focus_data/support_resistance.py`
- Modify: `tests/test_support_resistance.py`

**Interfaces:**
- Consumes: root path, ordered `UniverseEntry` sequence, optional date, and level count.
- Produces: `latest_common_analysis_date(...) -> str` and `build_support_resistance(...) -> tuple[pd.DataFrame, pd.DataFrame, str]`.

- [ ] **Step 1: Add failing common-date and builder tests**

Append:

```python
from pathlib import Path

from stock_focus_data.config import UniverseEntry
from stock_focus_data.support_resistance import (
    build_support_resistance,
    latest_common_analysis_date,
)


def test_latest_common_analysis_date_selects_latest_intersection() -> None:
    frames = {
        "AMD": price_frame(
            "1d",
            ["2026-08-31", "2026-09-01"],
            [11.0, 12.0],
            [9.0, 10.0],
            [10.0, 11.0],
        ),
        "PLTR": price_frame(
            "1d",
            ["2026-08-29", "2026-09-01"],
            [21.0, 22.0],
            [19.0, 20.0],
            [20.0, 21.0],
        ),
    }

    assert latest_common_analysis_date(frames) == "2026-09-01"
    assert latest_common_analysis_date(frames, "2026-09-01") == "2026-09-01"
    with pytest.raises(ValueError, match="not available for every symbol"):
        latest_common_analysis_date(frames, "2026-08-31")


def write_history(root: Path, symbol: str, timeframe: str, frame: pd.DataFrame) -> None:
    target = root / "derived" / f"{symbol}-{timeframe}.parquet"
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(target, index=False)


def test_build_support_resistance_preserves_universe_order(tmp_path: Path) -> None:
    root = tmp_path / "data"
    entries = (
        UniverseEntry("PLTR", "stock"),
        UniverseEntry("AMD", "stock"),
    )
    for symbol, base in (("PLTR", 20.0), ("AMD", 100.0)):
        daily = price_frame(
            "1d",
            ["2026-08-31", "2026-09-01"],
            [base + 2.0, base + 2.0],
            [base - 2.0, base - 2.0],
            [base, base],
        )
        hourly = price_frame(
            "1h",
            pd.date_range("2026-08-31", periods=8, freq="h", tz="UTC").astype(str).tolist(),
            [base + value for value in [1, 2, 3, 4, 3, 2, 1, 2]],
            [base - value for value in [1, 2, 3, 4, 3, 2, 1, 2]],
        )
        weekly = price_frame(
            "1w",
            ["2026-08-21", "2026-08-28", "2026-09-04"],
            [base + 4.0, base + 5.0, base + 6.0],
            [base - 4.0, base - 5.0, base - 6.0],
            [base, base, base],
            [True, True, False],
        )
        write_history(root, symbol, "1d", daily)
        write_history(root, symbol, "1h", hourly)
        write_history(root, symbol, "1w", weekly)

    compact, long, selected_date = build_support_resistance(root, entries)

    assert selected_date == "2026-09-01"
    assert compact["symbol"].tolist() == ["PLTR", "AMD"]
    assert len(compact) == 2
    assert compact["symbol"].nunique() == 2
    assert list(long.columns) == LONG_COLUMNS
    assert set(long["symbol"]) == {"AMD", "PLTR"}
```

- [ ] **Step 2: Run builder tests and verify red**

Run:

```powershell
python -m pytest tests/test_support_resistance.py -q
```

Expected: import fails for `latest_common_analysis_date` or `build_support_resistance`.

- [ ] **Step 3: Implement common-date selection and ordered building**

Add imports and functions:

```python
from collections.abc import Mapping, Sequence
from pathlib import Path

from stock_focus_data.config import UniverseEntry


def latest_common_analysis_date(
    daily_frames: Mapping[str, pd.DataFrame],
    requested: str | None = None,
) -> str:
    if not daily_frames:
        raise ValueError("no daily histories are available")
    date_sets = []
    for symbol, frame in daily_frames.items():
        if frame.empty or "session_date" not in frame:
            raise ValueError(f"missing daily history for {symbol}")
        date_sets.append(set(frame["session_date"].astype(str)))
    common = set.intersection(*date_sets)
    if requested is not None:
        selected = pd.Timestamp(requested).date().isoformat()
        if selected not in common:
            raise ValueError(f"analysis date {selected} is not available for every symbol")
        return selected
    if not common:
        raise ValueError("no common daily analysis date exists")
    return max(common)


def _read_history(root: Path, symbol: str, timeframe: str) -> pd.DataFrame:
    path = root / "derived" / f"{symbol}-{timeframe}.parquet"
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


def build_support_resistance(
    root: Path,
    entries: Sequence[UniverseEntry],
    analysis_date: str | None = None,
    levels: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    if levels < 1 or levels > 10:
        raise ValueError("level count must be between 1 and 10")
    symbols = [entry.symbol for entry in entries]
    if len(symbols) != len(set(symbols)):
        raise ValueError("universe contains duplicate symbols")
    frames = {
        symbol: {
            timeframe: _read_history(root, symbol, timeframe)
            for timeframe in ("1h", "1d", "1w")
        }
        for symbol in symbols
    }
    selected_date = latest_common_analysis_date(
        {symbol: frame_map["1d"] for symbol, frame_map in frames.items()},
        analysis_date,
    )
    compact_rows: list[dict[str, object]] = []
    long_rows: list[dict[str, object]] = []
    for symbol in symbols:
        frame_map = frames[symbol]
        compact, detail = calculate_symbol_levels(
            symbol,
            frame_map["1h"],
            frame_map["1d"],
            frame_map["1w"],
            selected_date,
            levels,
        )
        compact_rows.append(compact)
        long_rows.extend(detail)
    compact_frame = pd.DataFrame(compact_rows, columns=compact_columns(levels))
    if len(compact_frame) != len(symbols) or compact_frame["symbol"].nunique() != len(symbols):
        raise ValueError("compact output must contain one row per configured symbol")
    long_frame = pd.DataFrame(long_rows, columns=LONG_COLUMNS)
    return compact_frame, long_frame, selected_date
```

- [ ] **Step 4: Run focused and configuration tests**

Run:

```powershell
python -m pytest tests/test_support_resistance.py tests/test_config.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit the universe builder**

```powershell
git add src/stock_focus_data/support_resistance.py tests/test_support_resistance.py
git commit -m "feat: build levels for the configured universe"
```

---

### Task 6: CLI Command, Atomic Writes, and Summary Compatibility

**Files:**
- Modify: `src/stock_focus_data/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `build_support_resistance(root, entries, analysis_date, levels)`.
- Produces: `stock-focus support-resistance`, compact CSV, long Parquet, and summary discovery restricted to `*-1h.parquet`, `*-1d.parquet`, and `*-1w.parquet`.

- [ ] **Step 1: Add failing CLI output and summary-compatibility tests**

Add imports and helpers to `tests/test_cli.py`:

```python
import pandas as pd


def derived_frame(symbol: str, timeframe: str, complete: bool = True) -> pd.DataFrame:
    dates = (
        pd.date_range("2026-08-01", periods=20, freq="B", tz="UTC")
        if timeframe == "1d"
        else pd.date_range("2026-08-01", periods=20, freq="h", tz="UTC")
        if timeframe == "1h"
        else pd.date_range("2026-04-17", periods=20, freq="W-FRI", tz="UTC")
    )
    frame = pd.DataFrame(
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "timestamp_utc": dates,
            "session_date": dates.strftime("%Y-%m-%d"),
            "open": 100.0,
            "high": [104 + index % 4 for index in range(20)],
            "low": [96 - index % 4 for index in range(20)],
            "close": 100.0,
            "volume": 1000,
            "atr_14": 4.0,
            "data_source": "robinhood" if timeframe != "1w" else "derived",
            "validation_status": "valid",
            "retrieved_at_utc": pd.Timestamp("2026-09-02T00:00:00Z"),
        }
    )
    if timeframe == "1w":
        frame["is_complete"] = complete
    return frame


def write_cli_fixture(root: Path, config: Path) -> None:
    config.write_text(
        "symbols:\n  - symbol: AMD\n    asset_type: stock\n",
        encoding="utf-8",
    )
    derived = root / "derived"
    derived.mkdir(parents=True, exist_ok=True)
    for timeframe in ("1h", "1d", "1w"):
        derived_frame("AMD", timeframe).to_parquet(
            derived / f"AMD-{timeframe}.parquet", index=False
        )
```

Append tests:

```python
def test_support_resistance_command_writes_both_outputs(tmp_path: Path) -> None:
    root = tmp_path / "data"
    config = tmp_path / "universe.yaml"
    write_cli_fixture(root, config)

    result = CliRunner().invoke(
        app,
        [
            "support-resistance",
            "--root",
            str(root),
            "--config",
            str(config),
            "--levels",
            "3",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "symbols=1" in result.stdout
    compact_path = root / "latest" / "support_resistance.csv"
    long_path = root / "derived" / "support_resistance_levels.parquet"
    assert compact_path.exists()
    assert long_path.exists()
    assert len(pd.read_csv(compact_path)) == 1
    assert set(pd.read_parquet(long_path)["method"]) == {
        "classic",
        "multi_timeframe",
    }


def test_support_resistance_failure_preserves_existing_outputs(tmp_path: Path) -> None:
    root = tmp_path / "data"
    config = tmp_path / "universe.yaml"
    config.write_text(
        "symbols:\n  - symbol: AMD\n    asset_type: stock\n",
        encoding="utf-8",
    )
    compact_path = root / "latest" / "support_resistance.csv"
    long_path = root / "derived" / "support_resistance_levels.parquet"
    compact_path.parent.mkdir(parents=True, exist_ok=True)
    long_path.parent.mkdir(parents=True, exist_ok=True)
    compact_path.write_text("existing compact\n", encoding="utf-8")
    long_path.write_text("existing long\n", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["support-resistance", "--root", str(root), "--config", str(config)],
    )

    assert result.exit_code != 0
    assert compact_path.read_text(encoding="utf-8") == "existing compact\n"
    assert long_path.read_text(encoding="utf-8") == "existing long\n"


def test_summarize_ignores_support_resistance_parquet(tmp_path: Path) -> None:
    root = tmp_path / "data"
    config = tmp_path / "universe.yaml"
    write_cli_fixture(root, config)
    pd.DataFrame(
        [{"symbol": "AMD", "method": "classic", "level_value": 100.0}]
    ).to_parquet(root / "derived" / "support_resistance_levels.parquet", index=False)

    result = CliRunner().invoke(
        app,
        ["summarize", "--root", str(root), "--config", str(config)],
    )

    assert result.exit_code == 0, result.stdout
    assert "wrote 3 rows" in result.stdout
```

- [ ] **Step 2: Run the three new CLI tests and verify red**

Run:

```powershell
python -m pytest tests/test_cli.py -q
```

Expected: command tests fail because `support-resistance` is not registered, and the summary compatibility test fails when the non-history Parquet is read.

- [ ] **Step 3: Add imports, atomic writers, command, and history filtering**

Add to the imports in `cli.py`:

```python
import tempfile

from stock_focus_data.support_resistance import build_support_resistance
```

Add an atomic writer:

```python
def _write_support_resistance_outputs(
    compact: pd.DataFrame,
    long: pd.DataFrame,
    compact_target: Path,
    long_target: Path,
) -> None:
    compact_target.parent.mkdir(parents=True, exist_ok=True)
    long_target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=compact_target.parent, suffix=".csv", delete=False
    ) as handle:
        compact_temporary = Path(handle.name)
    with tempfile.NamedTemporaryFile(
        dir=long_target.parent, suffix=".parquet", delete=False
    ) as handle:
        long_temporary = Path(handle.name)
    try:
        compact.to_csv(compact_temporary, index=False)
        long.to_parquet(long_temporary, index=False)
        os.replace(compact_temporary, compact_target)
        os.replace(long_temporary, long_target)
    finally:
        compact_temporary.unlink(missing_ok=True)
        long_temporary.unlink(missing_ok=True)
```

Add the command after `summarize`:

```python
@app.command("support-resistance")
def support_resistance(
    root: Path = typer.Option(Path("data")),
    config: Path = typer.Option(Path("config/universe.yaml")),
    analysis_date: str | None = typer.Option(None, "--analysis-date"),
    levels: int = typer.Option(3, min=1, max=10),
) -> None:
    try:
        compact, long, selected_date = build_support_resistance(
            root,
            load_universe(config),
            analysis_date=analysis_date,
            levels=levels,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    compact_target = root / "latest" / "support_resistance.csv"
    long_target = root / "derived" / "support_resistance_levels.parquet"
    _write_support_resistance_outputs(
        compact,
        long,
        compact_target,
        long_target,
    )
    structural_count = int((long["method"] == "multi_timeframe").sum())
    typer.echo(
        f"analysis_date={selected_date} symbols={len(compact)} "
        f"structural_levels={structural_count} "
        f"compact={compact_target} long={long_target}"
    )
```

Replace the broad summary glob:

```python
paths = sorted((root / "derived").glob("*.parquet"))
```

with history-only discovery:

```python
paths = sorted(
    path
    for timeframe in ("1h", "1d", "1w")
    for path in (root / "derived").glob(f"*-{timeframe}.parquet")
)
```

- [ ] **Step 4: Run CLI tests and the complete suite**

Run:

```powershell
python -m pytest tests/test_cli.py -q
python -m pytest -q
```

Expected: all tests pass; the total exceeds the pre-feature baseline of 28 tests.

- [ ] **Step 5: Commit the CLI increment**

```powershell
git add src/stock_focus_data/cli.py tests/test_cli.py
git commit -m "feat: add support and resistance CLI outputs"
```

---

### Task 7: User Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/DATA_USAGE_GUIDE.md`

**Interfaces:**
- Consumes: final CLI and schemas from Tasks 1 through 6.
- Produces: copy-ready local/Git usage, formulas, schema explanations, examples, and limitations.

- [ ] **Step 1: Record documentation assertions before editing**

Run:

```powershell
Select-String -Path README.md,docs/DATA_USAGE_GUIDE.md -Pattern "support-resistance","support_resistance.csv","support_resistance_levels.parquet"
```

Expected: no matches.

- [ ] **Step 2: Add the concise README workflow**

Add a `## Support and resistance` section before `## Limitations` containing:

```markdown
## Support and resistance

After refreshing, rebuilding, and summarizing the market histories, calculate both multi-timeframe structural levels and classic daily/weekly pivots:

```powershell
stock-focus support-resistance
```

The compact 32-symbol view is `data/latest/support_resistance.csv`. Detailed level rows are in `data/derived/support_resistance_levels.parquet`. Structural levels are historical references derived from confirmed hourly, daily, and completed weekly swings; they are not guaranteed barriers or trading advice.
```

- [ ] **Step 3: Add the complete guide section**

Append `## 26. Support and resistance calculations` to `docs/DATA_USAGE_GUIDE.md` with:

```markdown
## 26. Support and resistance calculations

Generate the latest levels after the regular market session data has been refreshed:

```powershell
stock-focus support-resistance
```

Select a historical common date or a different number of structural levels:

```powershell
stock-focus support-resistance --analysis-date 2026-09-01 --levels 3
```

`data/latest/support_resistance.csv` contains one row per configured symbol and opens directly in Excel. `data/derived/support_resistance_levels.parquet` contains one row per emitted level for Python analysis.

```python
import pandas as pd

compact = pd.read_csv(
    "data/latest/support_resistance.csv",
    parse_dates=["price_timestamp_utc"],
)
levels = pd.read_parquet(
    "data/derived/support_resistance_levels.parquet"
)

amd = compact.loc[compact["symbol"] == "AMD"]
amd_levels = levels.loc[levels["symbol"] == "AMD"]
print(amd.T)
print(amd_levels)
```

The multi-timeframe method confirms strict swing highs and lows, weights weekly observations more than daily and hourly observations, applies recency decay, and clusters nearby prices using the larger of 0.5% of current price or 0.25 times daily ATR(14). Support 1 and resistance 1 are the nearest structural levels on each side of the analysis-date close. Touch count is the number of confirmed swing candidates in the cluster; strength score is the sum of timeframe and recency weights and is most useful within the same symbol.

Classic pivots use reference high `H`, low `L`, and close `C`:

```text
P  = (H + L + C) / 3
R1 = 2P - L       S1 = 2P - H
R2 = P + (H - L)  S2 = P - (H - L)
R3 = H + 2(P - L) S3 = L - 2(H - P)
```

Daily pivots use the common analysis-date bar and apply to the next session. Weekly pivots use the latest completed weekly bar. Null structural fields mean the retained history did not contain that many confirmed clusters; the program does not invent missing levels. `calculation_status=partial` and `warning` identify missing optional hourly or completed-weekly inputs.

Support and resistance are descriptive historical reference areas. Price can cross them, gap through them, or stop short of them; they are not forecasts, guarantees, or trading recommendations.
```

- [ ] **Step 4: Verify docs, links, formulas, and Markdown fences**

Run:

```powershell
Select-String -Path README.md,docs/DATA_USAGE_GUIDE.md -Pattern "support-resistance","support_resistance.csv","support_resistance_levels.parquet"
python -c "from pathlib import Path; files=[Path('README.md'),Path('docs/DATA_USAGE_GUIDE.md')]; [(_ for _ in ()).throw(AssertionError(p)) for p in files if p.read_text(encoding='utf-8').count(chr(96)*3)%2]; print('markdown fences balanced')"
git diff --check
```

Expected: both documents contain all three terms, Markdown fences are balanced, and the diff check exits zero.

- [ ] **Step 5: Commit documentation**

```powershell
git add README.md docs/DATA_USAGE_GUIDE.md
git commit -m "docs: explain support and resistance outputs"
```

---

### Task 8: Production Run, Data Verification, and Generated Outputs

**Files:**
- Generate: `data/latest/support_resistance.csv`
- Generate: `data/derived/support_resistance_levels.parquet`
- Verify: all source, test, and documentation changes

**Interfaces:**
- Consumes: data refreshed through 2026-09-01 and the completed CLI.
- Produces: verified 32-symbol research outputs committed locally.

- [ ] **Step 1: Run the program against production data**

Run from the repository root with the project environment active:

```powershell
stock-focus support-resistance --analysis-date 2026-09-01 --levels 3
```

Expected output contains:

```text
analysis_date=2026-09-01 symbols=32
```

- [ ] **Step 2: Verify schemas, formulas, ordering, completeness, and reloadability**

Run:

```powershell
python -c "from pathlib import Path; import math; import pandas as pd; c=pd.read_csv('data/latest/support_resistance.csv'); l=pd.read_parquet('data/derived/support_resistance_levels.parquet'); assert len(c)==32 and c.symbol.nunique()==32; assert set(c.analysis_date)=={'2026-09-01'}; assert c.calculation_status.eq('complete').all(); assert set(l.method)=={'classic','multi_timeframe'}; assert set(l.symbol)==set(c.symbol); assert c[['daily_pivot','daily_s1','daily_s2','daily_s3','daily_r1','daily_r2','daily_r3','weekly_pivot','weekly_s1','weekly_s2','weekly_s3','weekly_r1','weekly_r2','weekly_r3']].notna().all().all(); m=l[l.method.eq('multi_timeframe')]; assert (m.loc[m.side.eq('support'),'level_value'] < m.loc[m.side.eq('support'),'current_price']).all(); assert (m.loc[m.side.eq('resistance'),'level_value'] > m.loc[m.side.eq('resistance'),'current_price']).all(); assert m.loc[m.side.eq('support'),'distance_pct'].lt(0).all(); assert m.loc[m.side.eq('resistance'),'distance_pct'].gt(0).all(); d=l[(l.method.eq('classic')) & (l.reference_timeframe.eq('1d'))]; groups={s:g.set_index('level_name').level_value for s,g in d.groupby('symbol')}; [(_ for _ in ()).throw(AssertionError(s)) for s,v in groups.items() if not (math.isclose(v['R2']-v['P'],v['P']-v['S2'],rel_tol=1e-9,abs_tol=1e-9))]; assert pd.read_csv('data/latest/support_resistance.csv').shape==c.shape; assert pd.read_parquet('data/derived/support_resistance_levels.parquet').shape==l.shape; print(f'compact_rows={len(c)} long_rows={len(l)} structural_rows={len(m)} status=verified')"
```

Expected: prints `compact_rows=32` and `status=verified`.

- [ ] **Step 3: Verify data-equivalent reproducibility**

Run once to save hashes of sorted, normalized records, rerun the command, and compare:

```powershell
python -c "import hashlib,pandas as pd; c=pd.read_csv('data/latest/support_resistance.csv').sort_values('symbol').to_csv(index=False); l=pd.read_parquet('data/derived/support_resistance_levels.parquet').sort_values(['symbol','method','reference_timeframe','side','rank']).to_json(date_format='iso',orient='records'); open('.support_hash_before','w',encoding='utf-8').write(hashlib.sha256((c+l).encode()).hexdigest())"
stock-focus support-resistance --analysis-date 2026-09-01 --levels 3
python -c "import hashlib,pathlib,pandas as pd; c=pd.read_csv('data/latest/support_resistance.csv').sort_values('symbol').to_csv(index=False); l=pd.read_parquet('data/derived/support_resistance_levels.parquet').sort_values(['symbol','method','reference_timeframe','side','rank']).to_json(date_format='iso',orient='records'); after=hashlib.sha256((c+l).encode()).hexdigest(); before=pathlib.Path('.support_hash_before').read_text(); assert before==after,(before,after); print('data-equivalent rerun verified')"
```

Expected: `data-equivalent rerun verified`. Remove the temporary hash file with a targeted patch or a recoverable file removal after verifying its exact path is the repository-root `.support_hash_before`.

- [ ] **Step 4: Run full verification**

Run:

```powershell
python -m pytest -q
git diff --check
git status --short
```

Expected: every test passes, the diff check exits zero, and only the two generated output files remain uncommitted.

- [ ] **Step 5: Commit generated research outputs**

```powershell
git add data/latest/support_resistance.csv data/derived/support_resistance_levels.parquet
git commit -m "data: calculate support and resistance through 2026-09-01"
```

- [ ] **Step 6: Perform the final post-commit audit**

Run:

```powershell
python -m pytest -q
git diff --check HEAD~1 HEAD
git status --short --branch
git log -8 --oneline
```

Expected: all tests pass, the committed diff has no whitespace errors, the working tree is clean, and the recent log shows the formula, swing, clustering, assembly, builder, CLI, docs, and generated-data commits.

---

## Plan Self-Review Checklist

- Every requirement in `docs/superpowers/specs/2026-09-01-support-resistance-design.md` maps to one or more tasks above.
- Function names and signatures are consistent across tests, production steps, and downstream consumers.
- The non-history long-form Parquet is explicitly excluded from summary history discovery.
- Fatal build errors occur before output replacement; both successful outputs are written from complete in-memory frames.
- Weekly reference selection explicitly excludes incomplete rows.
- The analysis date is a common daily date, not the maximum date from only one symbol.
- Structural levels are ordered by proximity and are not fabricated when absent.
- Generated outputs are verified for all 32 symbols and committed separately from code and docs.
