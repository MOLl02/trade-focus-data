# Stock Focus Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tested local Python repository that stores hourly, daily, and derived weekly OHLCV data for the approved 32-symbol universe, uses Robinhood imports first with Alpaca fallback, and produces technical-indicator histories and a latest summary.

**Architecture:** Connected Robinhood responses cross a file-based import boundary so no brokerage credentials enter the codebase. Source adapters normalize Robinhood and Alpaca bars into one pandas schema; validation, atomic partitioned Parquet storage, weekly aggregation, indicator calculation, and summary generation operate only on that schema. A Typer CLI exposes explicit, non-trading local workflows.

**Tech Stack:** Python 3.11+, pandas, PyArrow, PyYAML, HTTPX, Typer, pytest, Parquet, CSV, Git.

## Global Constraints

- Track exactly these 32 symbols: `AAOI, AAPL, AMD, AMZN, APP, AXTI, CBRS, COHR, CRWD, CRWV, FN, GH, GOOGL, LITE, LLY, META, MRVL, MSFT, MU, NBIS, NOW, NVDA, PLTR, QQQ, RDW, RKLB, SEDG, SNDK, SOXX, SPCX, TSLA, WOLF`.
- QQQ and SOXX are the only ETFs; leveraged, inverse, and single-stock leveraged ETFs remain excluded.
- Robinhood is preferred whenever a valid imported bar exists; Alpaca may fill unavailable or incomplete symbol/range data.
- Store hourly and daily source candles and derive weekly candles from validated daily history.
- Default backfills are 365 calendar days for hourly bars and five calendar years for daily bars.
- Calculate all approved indicators independently for `1h`, `1d`, and `1w` histories.
- Preserve raw imports, keep normalized and derived data separate, and record row-level provenance.
- Do not store Robinhood credentials, brokerage account numbers, portfolio positions, or any order capability.
- Phase one is local only: no GitHub publication and no recurring scheduler.

---

## File Map

- `pyproject.toml`: package metadata, dependencies, CLI entry point, and pytest settings.
- `.gitignore`: secrets, virtual environments, caches, logs, and generated data exclusions.
- `.env.example`: names of Alpaca configuration variables without values.
- `config/universe.yaml`: the single authoritative universe and asset classifications.
- `src/stock_focus_data/config.py`: configuration loading and validation.
- `src/stock_focus_data/models.py`: normalized candle schema and timeframe types.
- `src/stock_focus_data/sources/base.py`: common market-data source protocol.
- `src/stock_focus_data/sources/robinhood_import.py`: exact Robinhood connector-payload parser.
- `src/stock_focus_data/sources/alpaca.py`: official Alpaca historical-bars REST adapter.
- `src/stock_focus_data/validation.py`: OHLCV invariants, deduplication, and coverage reporting.
- `src/stock_focus_data/storage.py`: atomic partitioned Parquet and manifest persistence.
- `src/stock_focus_data/aggregation.py`: daily-to-weekly candle aggregation.
- `src/stock_focus_data/indicators.py`: timeframe-independent technical calculations.
- `src/stock_focus_data/collection.py`: Robinhood-first orchestration and Alpaca fallback.
- `src/stock_focus_data/summaries.py`: latest multi-timeframe CSV view.
- `src/stock_focus_data/cli.py`: local commands that compose the modules.
- `tests/fixtures/robinhood_day.json`: fixed connector-shaped daily fixture.
- `tests/`: unit and integration coverage with no live credentials.
- `README.md`: setup, data contract, commands, provenance, and limitations.

---

### Task 1: Package Skeleton, Universe, and Candle Contract

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `config/universe.yaml`
- Create: `src/stock_focus_data/__init__.py`
- Create: `src/stock_focus_data/config.py`
- Create: `src/stock_focus_data/models.py`
- Create: `tests/test_config.py`
- Create: `tests/test_models.py`

**Interfaces:**
- Produces: `Timeframe`, `CANDLE_COLUMNS`, `empty_candle_frame()`, `UniverseEntry`, and `load_universe(path: Path) -> tuple[UniverseEntry, ...]`.
- Consumes: no earlier implementation tasks.

- [ ] **Step 1: Write failing configuration and model tests**

```python
# tests/test_config.py
from pathlib import Path

import pytest

from stock_focus_data.config import load_universe


def test_loads_exact_approved_universe() -> None:
    entries = load_universe(Path("config/universe.yaml"))
    symbols = tuple(entry.symbol for entry in entries)
    assert len(symbols) == 32
    assert symbols == tuple(sorted(symbols))
    assert {entry.symbol for entry in entries if entry.asset_type == "etf"} == {"QQQ", "SOXX"}


def test_rejects_duplicate_symbol(tmp_path: Path) -> None:
    path = tmp_path / "universe.yaml"
    path.write_text("symbols:\n  - symbol: AMD\n    asset_type: stock\n  - symbol: AMD\n    asset_type: stock\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate symbol: AMD"):
        load_universe(path)
```

```python
# tests/test_models.py
from stock_focus_data.models import CANDLE_COLUMNS, Timeframe, empty_candle_frame


def test_empty_frame_uses_canonical_columns() -> None:
    frame = empty_candle_frame()
    assert list(frame.columns) == list(CANDLE_COLUMNS)
    assert frame.empty
    assert {item.value for item in Timeframe} == {"1h", "1d", "1w"}
```

- [ ] **Step 2: Run the tests and verify import failures**

Run: `python -m pytest tests/test_config.py tests/test_models.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'stock_focus_data'`.

- [ ] **Step 3: Create package metadata and safe local defaults**

```toml
# pyproject.toml
[build-system]
requires = ["hatchling>=1.25,<2"]
build-backend = "hatchling.build"

[project]
name = "stock-focus-data"
version = "0.1.0"
description = "Local Robinhood-first market data store and indicator pipeline"
requires-python = ">=3.11"
dependencies = [
  "httpx>=0.27,<1",
  "pandas>=2.2,<3",
  "pyarrow>=16,<24",
  "python-dotenv>=1,<2",
  "PyYAML>=6,<7",
  "typer>=0.12,<1",
]

[project.optional-dependencies]
dev = ["pytest>=8,<10"]

[project.scripts]
stock-focus = "stock_focus_data.cli:app"

[tool.hatch.build.targets.wheel]
packages = ["src/stock_focus_data"]

[tool.pytest.ini_options]
addopts = "-ra"
testpaths = ["tests"]
```

```gitignore
# .gitignore
.env
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
*.egg-info/
build/
dist/
.local-sample-data/
logs/*.json
data/inbox/
data/raw/
data/normalized/
data/derived/
data/latest/
```

```dotenv
# .env.example
APCA_API_KEY_ID=
APCA_API_SECRET_KEY=
APCA_DATA_BASE_URL=https://data.alpaca.markets
APCA_DATA_FEED=iex
```

- [ ] **Step 4: Add the authoritative universe**

```yaml
# config/universe.yaml
symbols:
  - {symbol: AAOI, asset_type: stock}
  - {symbol: AAPL, asset_type: stock}
  - {symbol: AMD, asset_type: stock}
  - {symbol: AMZN, asset_type: stock}
  - {symbol: APP, asset_type: stock}
  - {symbol: AXTI, asset_type: stock}
  - {symbol: CBRS, asset_type: stock}
  - {symbol: COHR, asset_type: stock}
  - {symbol: CRWD, asset_type: stock}
  - {symbol: CRWV, asset_type: stock}
  - {symbol: FN, asset_type: stock}
  - {symbol: GH, asset_type: stock}
  - {symbol: GOOGL, asset_type: stock}
  - {symbol: LITE, asset_type: stock}
  - {symbol: LLY, asset_type: stock}
  - {symbol: META, asset_type: stock}
  - {symbol: MRVL, asset_type: stock}
  - {symbol: MSFT, asset_type: stock}
  - {symbol: MU, asset_type: stock}
  - {symbol: NBIS, asset_type: stock}
  - {symbol: NOW, asset_type: stock}
  - {symbol: NVDA, asset_type: stock}
  - {symbol: PLTR, asset_type: stock}
  - {symbol: QQQ, asset_type: etf}
  - {symbol: RDW, asset_type: stock}
  - {symbol: RKLB, asset_type: stock}
  - {symbol: SEDG, asset_type: stock}
  - {symbol: SNDK, asset_type: stock}
  - {symbol: SOXX, asset_type: etf}
  - {symbol: SPCX, asset_type: stock}
  - {symbol: TSLA, asset_type: stock}
  - {symbol: WOLF, asset_type: stock}
```

- [ ] **Step 5: Implement the configuration and candle contracts**

```python
# src/stock_focus_data/__init__.py
"""Local stock focus data pipeline."""

__version__ = "0.1.0"
```

```python
# src/stock_focus_data/config.py
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True, slots=True)
class UniverseEntry:
    symbol: str
    asset_type: str


def load_universe(path: Path) -> tuple[UniverseEntry, ...]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows = payload.get("symbols", []) if isinstance(payload, dict) else []
    entries = tuple(
        UniverseEntry(symbol=str(row["symbol"]).strip().upper(), asset_type=str(row["asset_type"]).strip().lower())
        for row in rows
    )
    seen: set[str] = set()
    for entry in entries:
        if entry.symbol in seen:
            raise ValueError(f"duplicate symbol: {entry.symbol}")
        if entry.asset_type not in {"stock", "etf"}:
            raise ValueError(f"invalid asset type for {entry.symbol}: {entry.asset_type}")
        seen.add(entry.symbol)
    if tuple(entry.symbol for entry in entries) != tuple(sorted(entry.symbol for entry in entries)):
        raise ValueError("universe symbols must be sorted")
    return entries
```

```python
# src/stock_focus_data/models.py
from enum import StrEnum

import pandas as pd


class Timeframe(StrEnum):
    HOUR = "1h"
    DAY = "1d"
    WEEK = "1w"


CANDLE_COLUMNS = (
    "symbol",
    "timeframe",
    "timestamp_utc",
    "session_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "vwap",
    "trade_count",
    "data_source",
    "retrieved_at_utc",
    "validation_status",
    "fallback_reason",
)


def empty_candle_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=CANDLE_COLUMNS)
```

- [ ] **Step 6: Install locally and run the focused tests**

Run: `python -m pip install -e ".[dev]"`

Expected: installation completes with `Successfully installed stock-focus-data` or reports it is already installed.

Run: `python -m pytest tests/test_config.py tests/test_models.py -q`

Expected: `3 passed`.

- [ ] **Step 7: Commit the package contract**

```bash
git add pyproject.toml .gitignore .env.example config src tests/test_config.py tests/test_models.py
git commit -m "feat: define stock universe and candle contract"
```

---

### Task 2: Robinhood Import and OHLCV Validation

**Files:**
- Create: `src/stock_focus_data/sources/__init__.py`
- Create: `src/stock_focus_data/sources/base.py`
- Create: `src/stock_focus_data/sources/robinhood_import.py`
- Create: `src/stock_focus_data/validation.py`
- Create: `tests/fixtures/robinhood_day.json`
- Create: `tests/test_robinhood_import.py`
- Create: `tests/test_validation.py`

**Interfaces:**
- Consumes: `Timeframe`, `CANDLE_COLUMNS`, and `empty_candle_frame()` from Task 1.
- Produces: `MarketDataSource.get_bars(...)`, `RobinhoodImportSource.load(path, timeframe, retrieved_at)`, `validate_candles(frame)`, and `DataValidationError`.

- [ ] **Step 1: Add a connector-shaped Robinhood fixture**

```json
{
  "data": {
    "results": [
      {
        "symbol": "AMD",
        "interval": "day",
        "bounds": "regular",
        "bars": [
          {"begins_at": "2026-08-24T00:00:00Z", "open_price": "180.00", "high_price": "185.00", "low_price": "179.00", "close_price": "184.00", "volume": 42000000, "session": "reg"},
          {"begins_at": "2026-08-25T00:00:00Z", "open_price": "184.00", "high_price": "188.00", "low_price": "183.00", "close_price": "187.00", "volume": 45000000, "session": "reg"},
          {"begins_at": "2026-08-26T00:00:00Z", "open_price": "187.00", "high_price": "189.00", "low_price": "184.00", "close_price": "186.00", "volume": 41000000, "session": "reg", "interpolated": false}
        ]
      }
    ]
  },
  "guide": "Fixed test fixture"
}
```

- [ ] **Step 2: Write failing parser and validator tests**

```python
# tests/test_robinhood_import.py
from datetime import UTC, datetime
from pathlib import Path

from stock_focus_data.models import Timeframe
from stock_focus_data.sources.robinhood_import import RobinhoodImportSource


def test_parses_connector_payload_and_provenance() -> None:
    frame = RobinhoodImportSource.load(
        Path("tests/fixtures/robinhood_day.json"),
        Timeframe.DAY,
        datetime(2026, 8, 26, 22, 0, tzinfo=UTC),
    )
    assert len(frame) == 3
    assert frame.iloc[-1]["close"] == 186.0
    assert frame.iloc[-1]["volume"] == 41_000_000
    assert set(frame["data_source"]) == {"robinhood"}
    assert str(frame["timestamp_utc"].dtype) == "datetime64[ns, UTC]"
```

```python
# tests/test_validation.py
import pandas as pd
import pytest

from stock_focus_data.validation import DataValidationError, validate_candles


def valid_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"symbol": "AMD", "timeframe": "1d", "timestamp_utc": "2026-08-25T00:00:00Z", "session_date": "2026-08-25", "open": 10.0, "high": 12.0, "low": 9.0, "close": 11.0, "volume": 100, "vwap": None, "trade_count": None, "data_source": "robinhood", "retrieved_at_utc": "2026-08-26T00:00:00Z", "validation_status": "pending", "fallback_reason": None},
        {"symbol": "AMD", "timeframe": "1d", "timestamp_utc": "2026-08-25T00:00:00Z", "session_date": "2026-08-25", "open": 10.0, "high": 12.0, "low": 9.0, "close": 11.0, "volume": 100, "vwap": None, "trade_count": None, "data_source": "robinhood", "retrieved_at_utc": "2026-08-26T00:00:00Z", "validation_status": "pending", "fallback_reason": None},
    ])


def test_validation_deduplicates_and_marks_valid() -> None:
    result = validate_candles(valid_frame())
    assert len(result) == 1
    assert result.iloc[0]["validation_status"] == "valid"


def test_validation_rejects_impossible_ohlc() -> None:
    frame = valid_frame().iloc[:1].copy()
    frame.loc[:, "high"] = 8.0
    with pytest.raises(DataValidationError, match="invalid OHLC relationship"):
        validate_candles(frame)


def test_validation_rejects_negative_volume() -> None:
    frame = valid_frame().iloc[:1].copy()
    frame.loc[:, "volume"] = -1
    with pytest.raises(DataValidationError, match="negative volume"):
        validate_candles(frame)
```

- [ ] **Step 3: Run tests and verify missing modules**

Run: `python -m pytest tests/test_robinhood_import.py tests/test_validation.py -q`

Expected: collection fails because `sources.robinhood_import` and `validation` do not exist.

- [ ] **Step 4: Implement the source protocol and Robinhood parser**

```python
# src/stock_focus_data/sources/__init__.py
"""Market-data source adapters."""
```

```python
# src/stock_focus_data/sources/base.py
from datetime import datetime
from typing import Protocol

import pandas as pd

from stock_focus_data.models import Timeframe


class MarketDataSource(Protocol):
    def get_bars(self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime) -> pd.DataFrame:
        """Return normalized bars in the canonical candle schema."""
```

```python
# src/stock_focus_data/sources/robinhood_import.py
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from stock_focus_data.models import CANDLE_COLUMNS, Timeframe, empty_candle_frame


class RobinhoodImportSource:
    @staticmethod
    def load(path: Path, timeframe: Timeframe, retrieved_at: datetime) -> pd.DataFrame:
        payload = json.loads(path.read_text(encoding="utf-8"))
        results = payload.get("data", {}).get("results", [])
        rows: list[dict[str, object]] = []
        for result in results:
            symbol = str(result["symbol"]).upper()
            for bar in result.get("bars") or []:
                if bar is None or bar.get("interpolated", False):
                    continue
                timestamp = pd.Timestamp(bar["begins_at"]).tz_convert("UTC")
                rows.append({
                    "symbol": symbol,
                    "timeframe": timeframe.value,
                    "timestamp_utc": timestamp,
                    "session_date": timestamp.date().isoformat(),
                    "open": float(bar["open_price"]),
                    "high": float(bar["high_price"]),
                    "low": float(bar["low_price"]),
                    "close": float(bar["close_price"]),
                    "volume": int(bar["volume"]),
                    "vwap": None,
                    "trade_count": None,
                    "data_source": "robinhood",
                    "retrieved_at_utc": pd.Timestamp(retrieved_at).tz_convert("UTC"),
                    "validation_status": "pending",
                    "fallback_reason": None,
                })
        if not rows:
            return empty_candle_frame()
        return pd.DataFrame(rows, columns=CANDLE_COLUMNS)
```

- [ ] **Step 5: Implement strict validation**

```python
# src/stock_focus_data/validation.py
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
    result["timestamp_utc"] = pd.to_datetime(result["timestamp_utc"], utc=True, errors="raise")
    result["retrieved_at_utc"] = pd.to_datetime(result["retrieved_at_utc"], utc=True, errors="raise")
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
    result = result.sort_values(["symbol", "timeframe", "timestamp_utc", "retrieved_at_utc"])
    result = result.drop_duplicates(["symbol", "timeframe", "timestamp_utc"], keep="last")
    result["validation_status"] = "valid"
    return result.reset_index(drop=True)
```

- [ ] **Step 6: Run parser and validation tests**

Run: `python -m pytest tests/test_robinhood_import.py tests/test_validation.py -q`

Expected: `4 passed`.

- [ ] **Step 7: Commit the trusted import boundary**

```bash
git add src/stock_focus_data/sources src/stock_focus_data/validation.py tests/fixtures tests/test_robinhood_import.py tests/test_validation.py
git commit -m "feat: parse and validate Robinhood candle imports"
```

---

### Task 3: Atomic Storage and Weekly Aggregation

**Files:**
- Create: `src/stock_focus_data/storage.py`
- Create: `src/stock_focus_data/aggregation.py`
- Create: `tests/test_storage.py`
- Create: `tests/test_aggregation.py`

**Interfaces:**
- Consumes: canonical frames and `validate_candles(frame)` from Tasks 1–2.
- Produces: `CandleStore.merge(frame)`, `CandleStore.read(symbol, timeframe)`, `write_manifest(root, manifest)`, and `aggregate_weekly(daily, now_utc)`.

- [ ] **Step 1: Write failing idempotency and aggregation tests**

```python
# tests/test_storage.py
from pathlib import Path

import pandas as pd

from stock_focus_data.models import Timeframe
from stock_focus_data.storage import CandleStore


def candle(source: str, close: float, retrieved: str) -> pd.DataFrame:
    return pd.DataFrame([{ "symbol": "AMD", "timeframe": "1d", "timestamp_utc": "2026-08-25T00:00:00Z", "session_date": "2026-08-25", "open": 10.0, "high": 12.0, "low": 9.0, "close": close, "volume": 100, "vwap": None, "trade_count": None, "data_source": source, "retrieved_at_utc": retrieved, "validation_status": "pending", "fallback_reason": None }])


def test_merge_is_idempotent_and_prefers_robinhood(tmp_path: Path) -> None:
    store = CandleStore(tmp_path)
    store.merge(candle("alpaca", 10.5, "2026-08-26T20:00:00Z"))
    store.merge(candle("robinhood", 11.0, "2026-08-26T19:00:00Z"))
    store.merge(candle("robinhood", 11.0, "2026-08-26T19:00:00Z"))
    result = store.read("AMD", Timeframe.DAY)
    assert len(result) == 1
    assert result.iloc[0]["data_source"] == "robinhood"
    assert result.iloc[0]["close"] == 11.0
```

```python
# tests/test_aggregation.py
from datetime import UTC, datetime

import pandas as pd

from stock_focus_data.aggregation import aggregate_weekly


def test_aggregates_daily_bars_and_marks_current_week_incomplete() -> None:
    dates = pd.to_datetime(["2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21", "2026-08-24"], utc=True)
    daily = pd.DataFrame({
        "symbol": "AMD", "timeframe": "1d", "timestamp_utc": dates,
        "session_date": [date.date().isoformat() for date in dates],
        "open": [10, 11, 12, 13, 14, 20], "high": [12, 13, 14, 15, 16, 22],
        "low": [9, 10, 11, 12, 13, 19], "close": [11, 12, 13, 14, 15, 21],
        "volume": [100, 110, 120, 130, 140, 200], "vwap": None, "trade_count": None,
        "data_source": "robinhood", "retrieved_at_utc": pd.Timestamp("2026-08-26T22:00:00Z"),
        "validation_status": "valid", "fallback_reason": None,
    })
    weekly = aggregate_weekly(daily, datetime(2026, 8, 26, 22, tzinfo=UTC))
    first = weekly.iloc[0]
    assert (first["open"], first["high"], first["low"], first["close"], first["volume"]) == (10, 16, 9, 15, 600)
    assert bool(first["is_complete"]) is True
    assert bool(weekly.iloc[-1]["is_complete"]) is False
```

- [ ] **Step 2: Run tests and verify missing modules**

Run: `python -m pytest tests/test_storage.py tests/test_aggregation.py -q`

Expected: collection fails because `storage` and `aggregation` do not exist.

- [ ] **Step 3: Implement atomic, partitioned Parquet storage**

```python
# src/stock_focus_data/storage.py
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from stock_focus_data.models import Timeframe, empty_candle_frame
from stock_focus_data.validation import validate_candles


SOURCE_PRIORITY = {"alpaca": 1, "derived": 2, "robinhood": 3}


class CandleStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _directory(self, symbol: str, timeframe: Timeframe, year: int) -> Path:
        return self.root / "normalized" / f"timeframe={timeframe.value}" / f"symbol={symbol}" / f"year={year}"

    def _partition(self, symbol: str, timeframe: Timeframe, year: int) -> Path:
        return self._directory(symbol, timeframe, year) / "bars.parquet"

    def merge(self, frame: pd.DataFrame) -> None:
        incoming = validate_candles(frame)
        if incoming.empty:
            return
        incoming["year"] = incoming["timestamp_utc"].dt.year
        for (symbol, timeframe_value, year), group in incoming.groupby(["symbol", "timeframe", "year"], sort=True):
            timeframe = Timeframe(str(timeframe_value))
            target = self._partition(str(symbol), timeframe, int(year))
            existing = pd.read_parquet(target) if target.exists() else empty_candle_frame()
            combined = pd.concat([existing, group.drop(columns="year")], ignore_index=True)
            combined["_source_priority"] = combined["data_source"].map(SOURCE_PRIORITY).fillna(0)
            combined = combined.sort_values(["timestamp_utc", "_source_priority", "retrieved_at_utc"])
            combined = combined.drop_duplicates(["symbol", "timeframe", "timestamp_utc"], keep="last")
            combined = combined.drop(columns="_source_priority")
            validated = validate_candles(combined)
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".parquet", delete=False) as handle:
                temp = Path(handle.name)
            try:
                validated.to_parquet(temp, index=False)
                os.replace(temp, target)
            finally:
                temp.unlink(missing_ok=True)

    def read(self, symbol: str, timeframe: Timeframe) -> pd.DataFrame:
        paths = sorted((self.root / "normalized" / f"timeframe={timeframe.value}" / f"symbol={symbol}").glob("year=*/bars.parquet"))
        if not paths:
            return empty_candle_frame()
        return validate_candles(pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True))


def write_manifest(root: Path, manifest: dict[str, object]) -> Path:
    directory = root / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = directory / f"run-{stamp}.json"
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return target
```

- [ ] **Step 4: Implement weekly candle derivation**

```python
# src/stock_focus_data/aggregation.py
from datetime import datetime

import pandas as pd

from stock_focus_data.models import CANDLE_COLUMNS
from stock_focus_data.validation import validate_candles


def aggregate_weekly(daily: pd.DataFrame, now_utc: datetime) -> pd.DataFrame:
    validated = validate_candles(daily)
    if validated.empty:
        return validated.assign(is_complete=pd.Series(dtype=bool))
    frames: list[pd.DataFrame] = []
    for symbol, group in validated.groupby("symbol", sort=True):
        indexed = group.set_index("timestamp_utc").sort_index()
        weekly = indexed.resample("W-FRI", label="right", closed="right").agg({
            "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
            "retrieved_at_utc": "max",
        }).dropna(subset=["open", "close"])
        weekly["symbol"] = symbol
        weekly["timeframe"] = "1w"
        weekly["session_date"] = weekly.index.date.astype(str)
        weekly["vwap"] = None
        weekly["trade_count"] = None
        weekly["data_source"] = "derived"
        weekly["validation_status"] = "pending"
        weekly["fallback_reason"] = None
        now_naive = pd.Timestamp(now_utc).tz_convert("UTC").tz_localize(None)
        current_period_label = now_naive.to_period("W-FRI").end_time.normalize().tz_localize("UTC")
        weekly["is_complete"] = weekly.index < current_period_label
        frames.append(weekly.reset_index())
    result = pd.concat(frames, ignore_index=True)
    core = validate_candles(result[list(CANDLE_COLUMNS)])
    complete = result.set_index(["symbol", "timeframe", "timestamp_utc"])["is_complete"]
    key = core.set_index(["symbol", "timeframe", "timestamp_utc"]).index
    core["is_complete"] = complete.reindex(key).to_numpy()
    return core
```

- [ ] **Step 5: Run storage and aggregation tests**

Run: `python -m pytest tests/test_storage.py tests/test_aggregation.py -q`

Expected: `2 passed`.

- [ ] **Step 6: Run all tests and commit**

Run: `python -m pytest -q`

Expected: `9 passed`.

```bash
git add src/stock_focus_data/storage.py src/stock_focus_data/aggregation.py tests/test_storage.py tests/test_aggregation.py
git commit -m "feat: store candles and derive weekly bars"
```

---

### Task 4: Technical Indicator Engine

**Files:**
- Create: `src/stock_focus_data/indicators.py`
- Create: `tests/test_indicators.py`

**Interfaces:**
- Consumes: validated single-symbol, single-timeframe candle frames.
- Produces: `add_indicators(frame) -> pd.DataFrame` with stable indicator column names used by summaries.

- [ ] **Step 1: Write failing deterministic indicator tests**

```python
# tests/test_indicators.py
import math

import pandas as pd

from stock_focus_data.indicators import add_indicators


def trend_frame(timeframe: str = "1d", count: int = 260) -> pd.DataFrame:
    close = pd.Series(range(1, count + 1), dtype=float)
    dates = pd.date_range("2025-01-01", periods=count, freq="B", tz="UTC")
    return pd.DataFrame({
        "symbol": "AMD", "timeframe": timeframe, "timestamp_utc": dates,
        "session_date": dates.date.astype(str), "open": close - 0.5,
        "high": close, "low": close - 1.0, "close": close,
        "volume": pd.Series(range(1000, 1000 + count), dtype=float),
        "vwap": None, "trade_count": None, "data_source": "robinhood",
        "retrieved_at_utc": pd.Timestamp("2026-08-26T22:00:00Z"),
        "validation_status": "valid", "fallback_reason": None,
    })


def test_indicators_have_expected_values_on_monotonic_series() -> None:
    result = add_indicators(trend_frame())
    last = result.iloc[-1]
    assert last["sma_20"] == 250.5
    assert last["sma_200"] == 160.5
    assert last["rsi_14"] == 100.0
    assert last["drawdown"] == 0.0
    assert math.isclose(last["return_1"], 260 / 259 - 1)
    assert math.isclose(last["range_52w_position"], 1.0)
    assert {"macd", "macd_signal", "macd_histogram", "atr_14", "stoch_k_14", "stoch_d_3", "relative_volume_20", "realized_volatility_20"}.issubset(result.columns)


def test_insufficient_history_remains_null() -> None:
    result = add_indicators(trend_frame(count=10))
    assert pd.isna(result.iloc[-1]["sma_20"])
    assert pd.isna(result.iloc[-1]["rsi_14"])
    assert pd.isna(result.iloc[-1]["range_52w_position"])
```

- [ ] **Step 2: Run test and verify missing module**

Run: `python -m pytest tests/test_indicators.py -q`

Expected: collection fails because `indicators` does not exist.

- [ ] **Step 3: Implement all approved indicators**

```python
# src/stock_focus_data/indicators.py
import numpy as np
import pandas as pd


ANNUALIZATION = {"1h": 252 * 6.5, "1d": 252, "1w": 52}


def _rsi(close: pd.Series, length: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    average_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    average_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    relative_strength = average_gain / average_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + relative_strength))
    return result.mask((average_loss == 0) & (average_gain > 0), 100.0)


def _one_group(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.sort_values("timestamp_utc").copy()
    close = result["close"].astype(float)
    high = result["high"].astype(float)
    low = result["low"].astype(float)
    volume = result["volume"].astype(float)
    result["rsi_14"] = _rsi(close, 14)
    ema_12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema_26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    result["ema_12"] = ema_12
    result["ema_26"] = ema_26
    result["ema_50"] = close.ewm(span=50, adjust=False, min_periods=50).mean()
    result["macd"] = ema_12 - ema_26
    result["macd_signal"] = result["macd"].ewm(span=9, adjust=False, min_periods=9).mean()
    result["macd_histogram"] = result["macd"] - result["macd_signal"]
    for length in (20, 50, 200):
        result[f"sma_{length}"] = close.rolling(length, min_periods=length).mean()
        result[f"distance_sma_{length}"] = close / result[f"sma_{length}"] - 1
    previous_close = close.shift(1)
    true_range = pd.concat([high - low, (high - previous_close).abs(), (low - previous_close).abs()], axis=1).max(axis=1)
    result["atr_14"] = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rolling_low = low.rolling(14, min_periods=14).min()
    rolling_high = high.rolling(14, min_periods=14).max()
    result["stoch_k_14"] = 100 * (close - rolling_low) / (rolling_high - rolling_low).replace(0, np.nan)
    result["stoch_d_3"] = result["stoch_k_14"].rolling(3, min_periods=3).mean()
    for length in (5, 20, 50):
        result[f"volume_avg_{length}"] = volume.rolling(length, min_periods=length).mean()
    result["relative_volume_20"] = volume / result["volume_avg_20"]
    for length in (1, 5, 20):
        result[f"return_{length}"] = close.pct_change(length, fill_method=None)
    log_return = np.log(close / close.shift(1))
    factor = ANNUALIZATION[str(result["timeframe"].iloc[0])]
    result["realized_volatility_20"] = log_return.rolling(20, min_periods=20).std(ddof=1) * np.sqrt(factor)
    result["running_peak"] = close.cummax()
    result["drawdown"] = close / result["running_peak"] - 1
    timeframe = str(result["timeframe"].iloc[0])
    range_length = 252 if timeframe == "1d" else 52 if timeframe == "1w" else None
    if range_length is None:
        result["high_52w"] = np.nan
        result["low_52w"] = np.nan
        result["range_52w_position"] = np.nan
    else:
        result["high_52w"] = high.rolling(range_length, min_periods=range_length).max()
        result["low_52w"] = low.rolling(range_length, min_periods=range_length).min()
        width = result["high_52w"] - result["low_52w"]
        result["range_52w_position"] = (close - result["low_52w"]) / width.replace(0, np.nan)
    return result


def add_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    return pd.concat(
        [_one_group(group) for _, group in frame.groupby(["symbol", "timeframe"], sort=True)],
        ignore_index=True,
    )
```

- [ ] **Step 4: Run focused and full tests**

Run: `python -m pytest tests/test_indicators.py -q`

Expected: `2 passed`.

Run: `python -m pytest -q`

Expected: `11 passed`.

- [ ] **Step 5: Commit the indicator engine**

```bash
git add src/stock_focus_data/indicators.py tests/test_indicators.py
git commit -m "feat: calculate multi-timeframe indicators"
```

---

### Task 5: Alpaca Adapter and Robinhood-First Collection

**Files:**
- Create: `src/stock_focus_data/sources/alpaca.py`
- Create: `src/stock_focus_data/collection.py`
- Create: `tests/test_alpaca.py`
- Create: `tests/test_collection.py`

**Interfaces:**
- Consumes: `MarketDataSource`, `RobinhoodImportSource.load`, `validate_candles`, and `CandleStore.merge`.
- Produces: `AlpacaSource.get_bars(symbol, timeframe, start, end)` and `collect_symbol(symbol, timeframe, start, end, robinhood_frame, fallback)`.

- [ ] **Step 1: Write failing Alpaca normalization and fallback tests**

```python
# tests/test_alpaca.py
from datetime import UTC, datetime
from pathlib import Path

import httpx

from stock_focus_data.models import Timeframe
from stock_focus_data.sources.alpaca import AlpacaSource


def test_alpaca_normalizes_bars_and_retries_transient_failure(tmp_path: Path) -> None:
    calls = 0
    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.headers["APCA-API-KEY-ID"] == "key"
        assert request.url.params["timeframe"] == "1Day"
        if calls == 1:
            return httpx.Response(503, json={"message": "temporary"})
        return httpx.Response(200, json={"bars": {"AMD": [{"t": "2026-08-25T04:00:00Z", "o": 10, "h": 12, "l": 9, "c": 11, "v": 100, "n": 50, "vw": 10.8}]}, "next_page_token": None})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    source = AlpacaSource("key", "secret", client=client, raw_directory=tmp_path, sleeper=lambda _: None)
    frame = source.get_bars("AMD", Timeframe.DAY, datetime(2026, 8, 25, tzinfo=UTC), datetime(2026, 8, 26, tzinfo=UTC))
    assert calls == 2
    assert len(list(tmp_path.glob("AMD-1d-*.json"))) == 2
    assert len(frame) == 1
    assert frame.iloc[0]["vwap"] == 10.8
    assert frame.iloc[0]["trade_count"] == 50
    assert frame.iloc[0]["fallback_reason"] == "robinhood_missing_or_incomplete"
```

```python
# tests/test_collection.py
from datetime import UTC, datetime

import pandas as pd

from stock_focus_data.collection import collect_symbol
from stock_focus_data.models import Timeframe, empty_candle_frame


class FakeAlpaca:
    def __init__(self) -> None:
        self.calls = 0

    def get_bars(self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime) -> pd.DataFrame:
        self.calls += 1
        return pd.DataFrame([{ "symbol": symbol, "timeframe": timeframe.value, "timestamp_utc": start, "session_date": start.date().isoformat(), "open": 10.0, "high": 12.0, "low": 9.0, "close": 11.0, "volume": 100, "vwap": None, "trade_count": None, "data_source": "alpaca", "retrieved_at_utc": end, "validation_status": "pending", "fallback_reason": "robinhood_missing_or_incomplete" }])


def test_valid_robinhood_rows_avoid_fallback() -> None:
    fallback = FakeAlpaca()
    start = datetime(2026, 8, 25, tzinfo=UTC)
    robinhood = fallback.get_bars("AMD", Timeframe.DAY, start, datetime(2026, 8, 26, tzinfo=UTC)).assign(data_source="robinhood", fallback_reason=None)
    fallback.calls = 0
    result, status = collect_symbol("AMD", Timeframe.DAY, start, datetime(2026, 8, 26, tzinfo=UTC), robinhood, fallback)
    assert fallback.calls == 0
    assert status["source"] == "robinhood"
    assert set(result["data_source"]) == {"robinhood"}


def test_empty_robinhood_rows_use_alpaca() -> None:
    fallback = FakeAlpaca()
    start = datetime(2026, 8, 25, tzinfo=UTC)
    result, status = collect_symbol("AMD", Timeframe.DAY, start, datetime(2026, 8, 26, tzinfo=UTC), empty_candle_frame(), fallback)
    assert fallback.calls == 1
    assert status["source"] == "alpaca"
    assert set(result["data_source"]) == {"alpaca"}
```

- [ ] **Step 2: Run tests and verify missing modules**

Run: `python -m pytest tests/test_alpaca.py tests/test_collection.py -q`

Expected: collection fails because `sources.alpaca` and `collection` do not exist.

- [ ] **Step 3: Implement the paginated Alpaca adapter**

```python
# src/stock_focus_data/sources/alpaca.py
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pandas as pd

from stock_focus_data.models import CANDLE_COLUMNS, Timeframe, empty_candle_frame


ALPACA_TIMEFRAMES = {Timeframe.HOUR: "1Hour", Timeframe.DAY: "1Day"}


class AlpacaSource:
    def __init__(self, key_id: str, secret_key: str, base_url: str = "https://data.alpaca.markets", feed: str = "iex", client: httpx.Client | None = None, raw_directory: Path | None = None, sleeper: Callable[[float], None] = time.sleep) -> None:
        if not key_id or not secret_key:
            raise ValueError("Alpaca credentials are required for fallback")
        self.base_url = base_url.rstrip("/")
        self.feed = feed
        self.client = client or httpx.Client(timeout=30.0)
        self.headers = {"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret_key}
        self.raw_directory = raw_directory
        self.sleeper = sleeper

    def get_bars(self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime) -> pd.DataFrame:
        if timeframe not in ALPACA_TIMEFRAMES:
            raise ValueError("Alpaca fetch supports only 1h and 1d; derive 1w from 1d")
        rows: list[dict[str, object]] = []
        token: str | None = None
        retrieved = datetime.now(UTC)
        page = 0
        while True:
            params = {"symbols": symbol, "timeframe": ALPACA_TIMEFRAMES[timeframe], "start": start.isoformat(), "end": end.isoformat(), "limit": "10000", "adjustment": "split", "feed": self.feed, "sort": "asc"}
            if token:
                params["page_token"] = token
            for attempt in range(3):
                response = self.client.get(f"{self.base_url}/v2/stocks/bars", params=params, headers=self.headers)
                if self.raw_directory is not None:
                    self.raw_directory.mkdir(parents=True, exist_ok=True)
                    stamp = retrieved.strftime("%Y%m%dT%H%M%SZ")
                    raw_path = self.raw_directory / f"{symbol}-{timeframe.value}-{stamp}-page{page:03d}-attempt{attempt + 1}.json"
                    raw_path.write_text(response.text, encoding="utf-8")
                if response.status_code < 500:
                    break
                if attempt < 2:
                    self.sleeper(float(2**attempt))
            response.raise_for_status()
            payload = response.json()
            for bar in payload.get("bars", {}).get(symbol, []):
                timestamp = pd.Timestamp(bar["t"]).tz_convert("UTC")
                rows.append({"symbol": symbol, "timeframe": timeframe.value, "timestamp_utc": timestamp, "session_date": timestamp.date().isoformat(), "open": float(bar["o"]), "high": float(bar["h"]), "low": float(bar["l"]), "close": float(bar["c"]), "volume": int(bar["v"]), "vwap": float(bar["vw"]) if bar.get("vw") is not None else None, "trade_count": int(bar["n"]) if bar.get("n") is not None else None, "data_source": "alpaca", "retrieved_at_utc": pd.Timestamp(retrieved), "validation_status": "pending", "fallback_reason": "robinhood_missing_or_incomplete"})
            token = payload.get("next_page_token")
            if not token:
                break
            page += 1
        return pd.DataFrame(rows, columns=CANDLE_COLUMNS) if rows else empty_candle_frame()
```

- [ ] **Step 4: Implement source precedence and fallback isolation**

```python
# src/stock_focus_data/collection.py
from datetime import datetime

import pandas as pd

from stock_focus_data.models import Timeframe
from stock_focus_data.sources.base import MarketDataSource
from stock_focus_data.validation import DataValidationError, validate_candles


def collect_symbol(symbol: str, timeframe: Timeframe, start: datetime, end: datetime, robinhood_frame: pd.DataFrame, fallback: MarketDataSource) -> tuple[pd.DataFrame, dict[str, object]]:
    preferred = robinhood_frame.loc[(robinhood_frame["symbol"] == symbol) & (robinhood_frame["timeframe"] == timeframe.value)].copy() if not robinhood_frame.empty else robinhood_frame.copy()
    try:
        preferred = validate_candles(preferred)
    except DataValidationError:
        preferred = preferred.iloc[0:0].copy()
    if not preferred.empty:
        return preferred, {"symbol": symbol, "timeframe": timeframe.value, "source": "robinhood", "rows": len(preferred), "fallback_reason": None}
    fallback_frame = validate_candles(fallback.get_bars(symbol, timeframe, start, end))
    if fallback_frame.empty:
        raise DataValidationError(f"no valid bars for {symbol} {timeframe.value}")
    return fallback_frame, {"symbol": symbol, "timeframe": timeframe.value, "source": "alpaca", "rows": len(fallback_frame), "fallback_reason": "robinhood_missing_or_incomplete"}
```

- [ ] **Step 5: Run adapter, fallback, and full tests**

Run: `python -m pytest tests/test_alpaca.py tests/test_collection.py -q`

Expected: `3 passed`.

Run: `python -m pytest -q`

Expected: `14 passed`.

- [ ] **Step 6: Commit the fallback path**

```bash
git add src/stock_focus_data/sources/alpaca.py src/stock_focus_data/collection.py tests/test_alpaca.py tests/test_collection.py
git commit -m "feat: add Alpaca fallback collection"
```

---

### Task 6: Latest Summary and Local CLI

**Files:**
- Create: `src/stock_focus_data/summaries.py`
- Create: `src/stock_focus_data/cli.py`
- Create: `tests/test_summaries.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: universe loading, imports, storage, aggregation, indicators, and manifests.
- Produces: `build_latest_summary(frames)`, `stock-focus validate-config`, `stock-focus import-robinhood`, `stock-focus rebuild`, and `stock-focus summarize`.

- [ ] **Step 1: Write failing summary and CLI tests**

```python
# tests/test_summaries.py
import pandas as pd

from stock_focus_data.summaries import build_latest_summary


def test_summary_selects_latest_complete_row() -> None:
    frame = pd.DataFrame([
        {"symbol": "AMD", "timeframe": "1d", "timestamp_utc": "2026-08-25T00:00:00Z", "close": 10.0, "volume": 100, "volume_avg_20": 90.0, "rsi_14": 55.0, "macd": 1.0, "macd_signal": 0.8, "macd_histogram": 0.2, "stoch_k_14": 60.0, "stoch_d_3": 58.0, "atr_14": 2.0, "sma_20": 9.5, "sma_50": 9.0, "sma_200": 8.0, "ema_12": 9.8, "ema_26": 9.2, "ema_50": 9.0, "distance_sma_20": 0.0526, "distance_sma_50": 0.1111, "distance_sma_200": 0.25, "return_1": 0.01, "return_5": 0.05, "return_20": 0.1, "relative_volume_20": 1.11, "realized_volatility_20": 0.3, "drawdown": -0.02, "high_52w": 12.0, "low_52w": 6.0, "range_52w_position": 0.667, "data_source": "robinhood", "validation_status": "valid", "retrieved_at_utc": "2026-08-26T22:00:00Z", "is_complete": True},
        {"symbol": "AMD", "timeframe": "1d", "timestamp_utc": "2026-08-26T00:00:00Z", "close": 11.0, "volume": 50, "data_source": "robinhood", "validation_status": "valid", "retrieved_at_utc": "2026-08-26T22:00:00Z", "is_complete": False},
    ])
    summary = build_latest_summary([frame])
    assert len(summary) == 1
    assert summary.iloc[0]["close"] == 10.0
    assert summary.iloc[0]["trend_state"] == "above_sma_20_50_200"
    assert summary.iloc[0]["macd_state"] == "bullish"


def test_summary_marks_missing_symbol_timeframes() -> None:
    frame = pd.DataFrame([{"symbol": "AMD", "timeframe": "1d", "timestamp_utc": "2026-08-25T00:00:00Z", "close": 10.0, "data_source": "robinhood", "validation_status": "valid", "retrieved_at_utc": "2026-08-26T22:00:00Z"}])
    summary = build_latest_summary([frame], expected_symbols=["AMD", "PLTR"])
    assert len(summary) == 6
    missing = summary.loc[summary["validation_status"] == "missing"]
    assert len(missing) == 5
    assert set(missing["symbol"]) == {"AMD", "PLTR"}
```

```python
# tests/test_cli.py
from typer.testing import CliRunner

from stock_focus_data.cli import app


def test_validate_config_command() -> None:
    result = CliRunner().invoke(app, ["validate-config", "--config", "config/universe.yaml"])
    assert result.exit_code == 0
    assert "32 symbols; 30 stocks; 2 ETFs" in result.stdout


def test_refresh_uses_complete_robinhood_import_without_credentials(tmp_path, monkeypatch) -> None:
    config = tmp_path / "universe.yaml"
    config.write_text("symbols:\n  - symbol: AMD\n    asset_type: stock\n", encoding="utf-8")
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)
    result = CliRunner().invoke(app, ["refresh", "--robinhood-input", "tests/fixtures/robinhood_day.json", "--timeframe", "1d", "--start", "2026-08-24T00:00:00Z", "--end", "2026-08-27T00:00:00Z", "--root", str(tmp_path / "data"), "--config", str(config)])
    assert result.exit_code == 0, result.stdout
    assert "refreshed=1 failed=0" in result.stdout
```

- [ ] **Step 2: Run tests and verify missing modules**

Run: `python -m pytest tests/test_summaries.py tests/test_cli.py -q`

Expected: collection fails because `summaries` and `cli` do not exist.

- [ ] **Step 3: Implement stable latest-summary selection**

```python
# src/stock_focus_data/summaries.py
from collections.abc import Iterable

import pandas as pd


SUMMARY_COLUMNS = ["symbol", "timeframe", "timestamp_utc", "close", "volume", "volume_avg_20", "relative_volume_20", "rsi_14", "macd", "macd_signal", "macd_histogram", "macd_state", "stoch_k_14", "stoch_d_3", "atr_14", "sma_20", "sma_50", "sma_200", "ema_12", "ema_26", "ema_50", "distance_sma_20", "distance_sma_50", "distance_sma_200", "trend_state", "return_1", "return_5", "return_20", "realized_volatility_20", "drawdown", "high_52w", "low_52w", "range_52w_position", "data_source", "validation_status", "retrieved_at_utc"]


def _trend(row: pd.Series) -> str:
    values = [row.get("sma_20"), row.get("sma_50"), row.get("sma_200")]
    if all(pd.notna(value) and row["close"] > value for value in values):
        return "above_sma_20_50_200"
    if all(pd.notna(value) and row["close"] < value for value in values):
        return "below_sma_20_50_200"
    return "mixed_or_insufficient_history"


def build_latest_summary(frames: Iterable[pd.DataFrame], expected_symbols: Iterable[str] = ()) -> pd.DataFrame:
    nonempty = [frame.copy() for frame in frames if not frame.empty]
    if not nonempty:
        missing = pd.DataFrame([{"symbol": symbol, "timeframe": timeframe, "validation_status": "missing"} for symbol in expected_symbols for timeframe in ("1h", "1d", "1w")])
        for column in SUMMARY_COLUMNS:
            if column not in missing.columns:
                missing[column] = pd.NA
        return missing[SUMMARY_COLUMNS].sort_values(["symbol", "timeframe"]).reset_index(drop=True) if not missing.empty else pd.DataFrame(columns=SUMMARY_COLUMNS)
    combined = pd.concat(nonempty, ignore_index=True)
    if "is_complete" in combined.columns:
        combined = combined.loc[combined["is_complete"].fillna(True)]
    latest = combined.sort_values("timestamp_utc").groupby(["symbol", "timeframe"], as_index=False).tail(1).copy()
    latest["trend_state"] = latest.apply(_trend, axis=1)
    latest["macd_state"] = latest.apply(lambda row: "bullish" if pd.notna(row.get("macd")) and pd.notna(row.get("macd_signal")) and row["macd"] > row["macd_signal"] else "bearish" if pd.notna(row.get("macd")) and pd.notna(row.get("macd_signal")) else "insufficient_history", axis=1)
    for column in SUMMARY_COLUMNS:
        if column not in latest.columns:
            latest[column] = pd.NA
    result = latest[SUMMARY_COLUMNS]
    expected = {(symbol, timeframe) for symbol in expected_symbols for timeframe in ("1h", "1d", "1w")}
    present = set(zip(result["symbol"], result["timeframe"], strict=False))
    missing_rows = [{"symbol": symbol, "timeframe": timeframe, "validation_status": "missing"} for symbol, timeframe in sorted(expected - present)]
    if missing_rows:
        missing = pd.DataFrame(missing_rows)
        for column in SUMMARY_COLUMNS:
            if column not in missing.columns:
                missing[column] = pd.NA
        result = pd.concat([result, missing[SUMMARY_COLUMNS]], ignore_index=True)
    return result.sort_values(["symbol", "timeframe"]).reset_index(drop=True)
```

- [ ] **Step 4: Implement explicit local CLI commands**

```python
# src/stock_focus_data/cli.py
import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import typer
from dotenv import load_dotenv

from stock_focus_data.aggregation import aggregate_weekly
from stock_focus_data.collection import collect_symbol
from stock_focus_data.config import load_universe
from stock_focus_data.indicators import add_indicators
from stock_focus_data.models import Timeframe, empty_candle_frame
from stock_focus_data.sources.alpaca import AlpacaSource
from stock_focus_data.sources.robinhood_import import RobinhoodImportSource
from stock_focus_data.storage import CandleStore, write_manifest
from stock_focus_data.summaries import build_latest_summary
from stock_focus_data.validation import validate_candles


app = typer.Typer(no_args_is_help=True)


class MissingFallback:
    def get_bars(self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime) -> pd.DataFrame:
        raise RuntimeError(f"Alpaca credentials are required to fill missing Robinhood data for {symbol} {timeframe.value}")


@app.command("validate-config")
def validate_config(config: Path = typer.Option(Path("config/universe.yaml"))) -> None:
    entries = load_universe(config)
    stocks = sum(entry.asset_type == "stock" for entry in entries)
    etfs = sum(entry.asset_type == "etf" for entry in entries)
    typer.echo(f"{len(entries)} symbols; {stocks} stocks; {etfs} ETFs")


@app.command("import-robinhood")
def import_robinhood(input_path: Path = typer.Option(..., "--input"), timeframe: Timeframe = typer.Option(...), root: Path = typer.Option(Path("data"))) -> None:
    frame = RobinhoodImportSource.load(input_path, timeframe, datetime.now(UTC))
    validated = validate_candles(frame)
    CandleStore(root).merge(validated)
    manifest = {"command": "import-robinhood", "input": str(input_path), "timeframe": timeframe.value, "rows": len(validated), "symbols": sorted(validated["symbol"].unique().tolist())}
    path = write_manifest(Path("."), manifest)
    typer.echo(f"imported {len(validated)} rows; manifest={path}")


@app.command("refresh")
def refresh(robinhood_input: list[Path] = typer.Option([], "--robinhood-input"), timeframe: Timeframe = typer.Option(...), start: datetime = typer.Option(...), end: datetime = typer.Option(...), root: Path = typer.Option(Path("data")), config: Path = typer.Option(Path("config/universe.yaml"))) -> None:
    if timeframe is Timeframe.WEEK:
        raise typer.BadParameter("refresh supports 1h and 1d; rebuild derives 1w")
    retrieved = datetime.now(UTC)
    imported_frames = [RobinhoodImportSource.load(path, timeframe, retrieved) for path in robinhood_input]
    imported = pd.concat(imported_frames, ignore_index=True) if imported_frames else empty_candle_frame()
    load_dotenv()
    key_id = os.getenv("APCA_API_KEY_ID", "")
    secret_key = os.getenv("APCA_API_SECRET_KEY", "")
    fallback = AlpacaSource(key_id, secret_key, base_url=os.getenv("APCA_DATA_BASE_URL", "https://data.alpaca.markets"), feed=os.getenv("APCA_DATA_FEED", "iex"), raw_directory=root / "raw" / "alpaca") if key_id and secret_key else MissingFallback()
    store = CandleStore(root)
    statuses: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    for entry in load_universe(config):
        try:
            frame, status = collect_symbol(entry.symbol, timeframe, start, end, imported, fallback)
            store.merge(frame)
            statuses.append(status)
        except Exception as exc:
            failures.append({"symbol": entry.symbol, "timeframe": timeframe.value, "error": str(exc)})
    write_manifest(root.parent, {"command": "refresh", "timeframe": timeframe.value, "start": start, "end": end, "statuses": statuses, "failures": failures})
    typer.echo(f"refreshed={len(statuses)} failed={len(failures)}")
    if failures:
        raise typer.Exit(code=1)


@app.command("rebuild")
def rebuild(root: Path = typer.Option(Path("data")), config: Path = typer.Option(Path("config/universe.yaml"))) -> None:
    store = CandleStore(root)
    entries = load_universe(config)
    derived_dir = root / "derived"
    derived_dir.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        daily = store.read(entry.symbol, Timeframe.DAY)
        if daily.empty:
            continue
        weekly = aggregate_weekly(daily, datetime.now(UTC))
        add_indicators(daily).to_parquet(derived_dir / f"{entry.symbol}-1d.parquet", index=False)
        add_indicators(weekly).to_parquet(derived_dir / f"{entry.symbol}-1w.parquet", index=False)
        hourly = store.read(entry.symbol, Timeframe.HOUR)
        if not hourly.empty:
            add_indicators(hourly).to_parquet(derived_dir / f"{entry.symbol}-1h.parquet", index=False)
    typer.echo("rebuilt derived datasets")


@app.command("summarize")
def summarize(root: Path = typer.Option(Path("data")), config: Path = typer.Option(Path("config/universe.yaml"))) -> None:
    paths = sorted((root / "derived").glob("*.parquet"))
    expected_symbols = [entry.symbol for entry in load_universe(config)]
    summary = build_latest_summary((pd.read_parquet(path) for path in paths), expected_symbols=expected_symbols)
    target = root / "latest" / "focus_summary.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(target, index=False)
    typer.echo(f"wrote {len(summary)} rows to {target}")
```

- [ ] **Step 5: Run focused and full tests**

Run: `python -m pytest tests/test_summaries.py tests/test_cli.py -q`

Expected: `4 passed`.

Run: `python -m pytest -q`

Expected: `18 passed`.

- [ ] **Step 6: Exercise the first CLI command and commit**

Run: `stock-focus validate-config`

Expected: `32 symbols; 30 stocks; 2 ETFs`.

```bash
git add src/stock_focus_data/summaries.py src/stock_focus_data/cli.py tests/test_summaries.py tests/test_cli.py
git commit -m "feat: add summaries and local commands"
```

---

### Task 7: Fixture-Level End-to-End Workflow and Documentation

**Files:**
- Create: `tests/test_pipeline.py`
- Create: `README.md`
- Modify: `src/stock_focus_data/cli.py`

**Interfaces:**
- Consumes: all earlier task interfaces.
- Produces: a documented, fixture-tested local workflow and a `stock-focus sample` command.

- [ ] **Step 1: Write a failing end-to-end fixture test**

```python
# tests/test_pipeline.py
from datetime import UTC, datetime
from pathlib import Path

from stock_focus_data.aggregation import aggregate_weekly
from stock_focus_data.indicators import add_indicators
from stock_focus_data.models import Timeframe
from stock_focus_data.sources.robinhood_import import RobinhoodImportSource
from stock_focus_data.storage import CandleStore
from stock_focus_data.summaries import build_latest_summary


def test_fixture_pipeline_is_idempotent(tmp_path: Path) -> None:
    imported = RobinhoodImportSource.load(Path("tests/fixtures/robinhood_day.json"), Timeframe.DAY, datetime(2026, 8, 26, 22, tzinfo=UTC))
    store = CandleStore(tmp_path)
    store.merge(imported)
    store.merge(imported)
    daily = store.read("AMD", Timeframe.DAY)
    assert len(daily) == 3
    weekly = aggregate_weekly(daily, datetime(2026, 9, 1, 22, tzinfo=UTC))
    summary = build_latest_summary([add_indicators(daily), add_indicators(weekly)])
    assert set(summary["timeframe"]) == {"1d", "1w"}
    assert set(summary["data_source"]) == {"robinhood", "derived"}
```

- [ ] **Step 2: Run the integration test and verify the expected pre-documentation state**

Run: `python -m pytest tests/test_pipeline.py -q`

Expected: `1 passed`.

- [ ] **Step 3: Add a sample command that never needs credentials**

Add this command below `validate_config` in `src/stock_focus_data/cli.py`:

```python
@app.command("sample")
def sample(root: Path = typer.Option(Path("data"))) -> None:
    fixture = Path("tests/fixtures/robinhood_day.json")
    frame = RobinhoodImportSource.load(fixture, Timeframe.DAY, datetime.now(UTC))
    store = CandleStore(root)
    store.merge(frame)
    daily = store.read("AMD", Timeframe.DAY)
    weekly = aggregate_weekly(daily, datetime.now(UTC))
    derived = root / "derived"
    derived.mkdir(parents=True, exist_ok=True)
    add_indicators(daily).to_parquet(derived / "AMD-1d.parquet", index=False)
    add_indicators(weekly).to_parquet(derived / "AMD-1w.parquet", index=False)
    typer.echo(f"sample complete: daily={len(daily)} weekly={len(weekly)}")
```

- [ ] **Step 4: Document setup, commands, and security boundaries**

````markdown
# Stock Focus Data

Local Robinhood-first OHLCV storage and technical analysis for 32 approved focus symbols. QQQ and SOXX are the only ETFs. This project stores research data and cannot place trades.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Fill `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` in `.env` only when Alpaca fallback is needed. Never put Robinhood credentials or account numbers in this repository.

## Local checks

```powershell
stock-focus validate-config
stock-focus sample
python -m pytest -q
```

## Robinhood import

Robinhood is connected through Codex. Save the connector's unchanged structured payload under `data/inbox/robinhood/`, then import it explicitly:

```powershell
stock-focus import-robinhood --input data/inbox/robinhood/day-2026-08-26.json --timeframe 1d
stock-focus import-robinhood --input data/inbox/robinhood/hour-2026-08-26.json --timeframe 1h
stock-focus rebuild
stock-focus summarize
```

To apply Robinhood-first selection and Alpaca fallback across the configured universe, use `refresh` with one or more connector payloads:

```powershell
stock-focus refresh --robinhood-input data/inbox/robinhood/day-2026-08-26.json --timeframe 1d --start 2021-08-26T00:00:00Z --end 2026-08-27T00:00:00Z
```

Raw imports, generated data, logs, and `.env` are ignored by Git. The canonical normalized history is partitioned Parquet under `data/normalized/`; calculated histories are under `data/derived/`; `data/latest/focus_summary.csv` is the compact current view.

## Data defaults

- Hourly backfill: 365 calendar days
- Daily backfill: five calendar years
- Weekly bars: derived from validated daily bars
- Regular market session, split-adjusted prices
- Robinhood wins duplicate timestamps; Alpaca fills unavailable symbol/range data

## Indicators

RSI(14), MACD(12,26,9), SMA(20/50/200), EMA(12/26/50), ATR(14), stochastic %K/%D, relative and rolling volume, 1/5/20-bar returns, 20-bar realized volatility, running drawdown, moving-average distance, and 52-week range position.

## Limitations

The standalone code cannot authenticate to Robinhood. Robinhood payloads enter through the connected Codex import boundary. Live Alpaca fallback requires user-supplied API credentials. Phase one has no scheduler and does not publish to GitHub.
````

- [ ] **Step 5: Run sample, all tests, and security scans**

Run: `stock-focus sample --root .local-sample-data`

Expected: output starts with `sample complete: daily=3 weekly=` and exits successfully.

Run: `python -m pytest -q`

Expected: `19 passed`.

Run: `rg -n -i "password|secret|account_number|place.*order|cancel.*order" --glob "!docs/superpowers/**" --glob "!*.example" .`

Expected: only deliberate documentation or Alpaca environment-variable references; no credential values, Robinhood account numbers, or trading functions.

Run: `git status --short`

Expected: only Task 7 files are modified; `.local-sample-data`, generated data, logs, caches, and `.env` are not tracked.

- [ ] **Step 6: Commit the complete local workflow**

```bash
git add README.md src/stock_focus_data/cli.py tests/test_pipeline.py
git commit -m "docs: complete local stock data workflow"
```

---

### Task 8: Live Four-Symbol Smoke Test

**Files:**
- Create locally but do not commit: `data/inbox/robinhood/day-2026-08-26.json`
- Create locally but do not commit: `data/inbox/robinhood/hour-2026-08-26.json`
- Create locally but do not commit: `data/normalized/**`
- Create locally but do not commit: `data/derived/**`
- Create locally but do not commit: `data/latest/focus_summary.csv`
- Create locally but do not commit: the timestamped manifest generated under `logs/`

**Interfaces:**
- Consumes: connected Robinhood historicals for `AMD`, `PLTR`, `QQQ`, and `SOXX`, plus every implemented CLI command.
- Produces: validated local sample data and an evidence-backed readiness report; no tracked source changes.

- [ ] **Step 1: Fetch the live smoke-test history through the connected Robinhood tool**

Request regular-session, split-adjusted bars for `AMD`, `PLTR`, `QQQ`, and `SOXX` in batches of four:

```text
Daily: interval=day, start_time=2021-08-26T00:00:00Z, end_time=2026-08-27T00:00:00Z, bounds=regular, adjustment_type=split
Hourly: interval=hour, start_time=2025-08-26T00:00:00Z, end_time=2026-08-27T00:00:00Z, bounds=regular, adjustment_type=split
```

Save each returned structured payload unchanged to the corresponding ignored inbox file. Confirm that no portfolio, account, or order fields are present.

- [ ] **Step 2: Import, rebuild, and summarize the live sample**

```powershell
stock-focus import-robinhood --input data/inbox/robinhood/day-2026-08-26.json --timeframe 1d
stock-focus import-robinhood --input data/inbox/robinhood/hour-2026-08-26.json --timeframe 1h
stock-focus rebuild
stock-focus summarize
```

Expected: both imports report positive row counts; rebuild succeeds; the full-universe summary contains 96 rows, of which 12 non-missing rows cover the four smoke-test symbols across `1h`, `1d`, and `1w`.

- [ ] **Step 3: Verify provenance, completeness, and indicators**

Run: `python -c "import pandas as pd; p='data/latest/focus_summary.csv'; d=pd.read_csv(p); live=d[d.validation_status!='missing']; assert len(d)==96; assert len(live)==12; assert set(live.symbol)=={'AMD','PLTR','QQQ','SOXX'}; assert set(live.timeframe)=={'1h','1d','1w'}; assert live.validation_status.eq('valid').all(); print(live[['symbol','timeframe','close','rsi_14','data_source']].to_string(index=False))"`

Expected: a 12-row table, all rows valid, Robinhood provenance on `1h` and `1d`, and derived provenance on `1w`.

- [ ] **Step 4: Verify idempotency and repository cleanliness**

Repeat the two import commands, then run the summary command again.

Run: `python -c "import pandas as pd; d=pd.read_csv('data/latest/focus_summary.csv'); assert len(d)==96; assert len(d[d.validation_status!='missing'])==12; print('idempotent summary: 96 universe rows, 12 populated')"`

Expected: `idempotent summary: 96 universe rows, 12 populated`.

Run: `python -m pytest -q`

Expected: `19 passed`.

Run: `git status --short --ignored`

Expected: generated inbox, normalized, derived, latest, log, cache, and environment artifacts are ignored; tracked files are clean.

- [ ] **Step 5: Record the readiness result without committing generated market data**

If every check passes, report the tested symbols, candle counts by timeframe, fallback usage, indicator coverage, and clean Git status to the user. Do not commit generated market data in phase one; publication and scheduling remain a separately approved phase.

---

### Task 9: Full 32-Symbol Local Collection

**Files:**
- Create locally but do not commit: eight connector payloads under `data/inbox/robinhood/`
- Update locally but do not commit: generated normalized, derived, latest, and manifest data

**Interfaces:**
- Consumes: the verified smoke-test workflow and the exact universe from `config/universe.yaml`.
- Produces: a 96-row status-complete local summary covering every symbol across `1h`, `1d`, and `1w`.

- [ ] **Step 1: Fetch daily and hourly data in connector-safe batches**

Use these exact symbol batches, each within the Robinhood tool's 10-symbol limit:

```text
Batch 01: AAOI AAPL AMD AMZN APP AXTI CBRS COHR CRWD CRWV
Batch 02: FN GH GOOGL LITE LLY META MRVL MSFT MU NBIS
Batch 03: NOW NVDA PLTR QQQ RDW RKLB SEDG SNDK SOXX SPCX
Batch 04: TSLA WOLF
```

For every batch, request the exact ranges and settings below:

```text
Daily: interval=day, start_time=2021-08-26T00:00:00Z, end_time=2026-08-27T00:00:00Z, bounds=regular, adjustment_type=split
Hourly: interval=hour, start_time=2025-08-26T00:00:00Z, end_time=2026-08-27T00:00:00Z, bounds=regular, adjustment_type=split
```

Save the unchanged structured responses as `day-2026-08-26-batch-01.json` through `day-2026-08-26-batch-04.json` and the corresponding four `hour-2026-08-26-batch-*.json` files.

- [ ] **Step 2: Import all eight payloads idempotently**

```powershell
stock-focus refresh --robinhood-input data/inbox/robinhood/day-2026-08-26-batch-01.json --robinhood-input data/inbox/robinhood/day-2026-08-26-batch-02.json --robinhood-input data/inbox/robinhood/day-2026-08-26-batch-03.json --robinhood-input data/inbox/robinhood/day-2026-08-26-batch-04.json --timeframe 1d --start 2021-08-26T00:00:00Z --end 2026-08-27T00:00:00Z
stock-focus refresh --robinhood-input data/inbox/robinhood/hour-2026-08-26-batch-01.json --robinhood-input data/inbox/robinhood/hour-2026-08-26-batch-02.json --robinhood-input data/inbox/robinhood/hour-2026-08-26-batch-03.json --robinhood-input data/inbox/robinhood/hour-2026-08-26-batch-04.json --timeframe 1h --start 2025-08-26T00:00:00Z --end 2026-08-27T00:00:00Z
stock-focus rebuild
stock-focus summarize
```

Expected: every import completes independently, rebuild completes, and summary generation reports 96 rows.

- [ ] **Step 3: Verify universe coverage and explicit missing status**

Run: `python -c "import pandas as pd, yaml; d=pd.read_csv('data/latest/focus_summary.csv'); u={x['symbol'] for x in yaml.safe_load(open('config/universe.yaml', encoding='utf-8'))['symbols']}; assert len(d)==96; assert set(d.symbol)==u; assert set(d.timeframe)=={'1h','1d','1w'}; assert d.groupby('symbol').size().eq(3).all(); assert d.validation_status.isin(['valid','missing']).all(); print(d.groupby(['timeframe','validation_status']).size().to_string())"`

Expected: exactly three rows per approved symbol and a printed count of valid versus missing rows by timeframe. A missing status is acceptable only when the run manifest names the unavailable symbol or range; do not silently drop it.

- [ ] **Step 4: Inspect indicator and provenance coverage**

Run: `python -c "import pandas as pd; d=pd.read_csv('data/latest/focus_summary.csv'); v=d[d.validation_status=='valid']; assert v.data_source.isin(['robinhood','alpaca','derived']).all(); print(v.groupby(['timeframe','data_source']).size().to_string()); print(v[['rsi_14','macd','sma_200','atr_14','stoch_k_14','relative_volume_20']].notna().sum().to_string())"`

Expected: hourly and daily rows identify Robinhood or Alpaca, weekly rows identify derived data, and indicator non-null counts reflect each symbol's available lookback rather than fabricated zeroes.

- [ ] **Step 5: Re-run quality checks and hand off local results**

Run: `python -m pytest -q`

Expected: `19 passed`.

Run: `git status --short --ignored`

Expected: tracked files are clean and all generated market data remains ignored.

Report full-universe coverage, any unresolved symbols, source fallback counts, final candle counts, and the absolute path to `data/latest/focus_summary.csv`. Do not publish or schedule the repository without separate user approval.
