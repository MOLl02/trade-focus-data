# Stock Focus Data: Retrieval and Usage Guide

This guide explains how to locate, retrieve, inspect, query, export, and update the stock research data stored in this repository. It covers both the existing local checkout and a fresh checkout downloaded from GitHub.

The repository is a research dataset. It does not place trades, submit orders, or represent investment advice.

## 1. What the repository contains

The configured universe contains 32 symbols: 30 stocks plus the QQQ and SOXX ETFs. The authoritative list is [`config/universe.yaml`](../config/universe.yaml).

The normal retention policy is:

- Hourly history: the latest one calendar year
- Daily history: the latest two calendar years
- Weekly history: derived from the retained daily bars
- Market session: regular US equity session
- Primary source: Robinhood
- Gap-filling source: Alpaca

Newly listed symbols naturally have less history than the retention window. A missing date can also mean that the market was closed or the provider reported no real trading activity.

## 2. Local repository location

On the current Windows computer, the repository is located at:

```text
C:\Users\molyu\.codex\.chatgpt-projects\g-p-6a84f884f2cc8191a6925a21ab8f7c3e\stock-focus-data
```

Open it in PowerShell:

```powershell
cd "C:\Users\molyu\.codex\.chatgpt-projects\g-p-6a84f884f2cc8191a6925a21ab8f7c3e\stock-focus-data"
```

Open it in Git Bash:

```bash
cd ~/.codex/.chatgpt-projects/g-p-6a84f884f2cc8191a6925a21ab8f7c3e/stock-focus-data
```

Most examples in this guide assume the terminal is already in the repository root.

## 3. Retrieve the repository from GitHub

The configured GitHub repository is:

```text
https://github.com/MOLl02/trade-focus-data
```

### First download on another computer

Authenticate with GitHub, then clone the repository:

```bash
git clone https://github.com/MOLl02/trade-focus-data.git
cd trade-focus-data
```

With GitHub CLI, the equivalent command is:

```bash
gh repo clone MOLl02/trade-focus-data
cd trade-focus-data
```

If the repository is private, the GitHub account used by Git or `gh` must have access.

### Retrieve later updates

First check whether you have uncommitted local changes:

```bash
git status
```

If the working tree is clean, download only fast-forward updates:

```bash
git pull --ff-only origin main
```

`--ff-only` prevents Git from silently creating a merge commit when the local and remote histories differ.

### Confirm which revision you have

```bash
git log -5 --oneline
git status --short --branch
```

## 4. Install the data-reading tools

Python 3.11 or newer is recommended.

### Minimal installation for reading the data

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install pandas pyarrow
```

In Git Bash, activate the same Windows environment with:

```bash
source .venv/Scripts/activate
```

### Full project installation

Use this option if you also want to run the repository commands or tests:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## 5. Directory and file map

| Location | Purpose | Typical use |
|---|---|---|
| `config/universe.yaml` | Authoritative stock and ETF universe | Determine which symbols are expected |
| `data/latest/focus_summary.csv` | One latest row per symbol and timeframe | Excel, screening, quick review |
| `data/derived/{SYMBOL}-{TIMEFRAME}.parquet` | Complete indicator-enriched history | Charts, analysis, backtests, custom signals |
| `data/normalized/timeframe={TIMEFRAME}/symbol={SYMBOL}/year={YEAR}/bars.parquet` | Canonical validated OHLCV partitions | Source-aware research and custom calculations |
| `data/inbox/robinhood/` | Untouched Robinhood connector payloads | Auditing and reproducibility |
| `data/inbox/alpaca/` | Untouched Alpaca connector payloads | Auditing and reproducibility |
| `logs/run-*.json` | Collection/import manifests | Diagnose which run produced data |
| `src/stock_focus_data/` | Data pipeline source code | Understand or extend calculations |
| `tests/` | Automated data-pipeline tests and small fixtures | Verify behavior after code changes |

Timeframe codes are:

- `1h`: hourly
- `1d`: daily
- `1w`: weekly

For example:

```text
data/derived/AMD-1h.parquet
data/derived/AMD-1d.parquet
data/derived/AMD-1w.parquet
```

## 6. Choose the correct dataset

Use the smallest dataset that answers the question.

### Use the latest summary when

- You want the current RSI for every symbol.
- You want to screen for high relative volume.
- You want one row for every symbol/timeframe pair.
- You want to work in Excel without converting Parquet.

File:

```text
data/latest/focus_summary.csv
```

### Use the derived histories when

- You want to plot price and indicators over time.
- You want to backtest a signal.
- You want historical RSI, MACD, moving averages, volume, or returns.
- You want one convenient file for a symbol and timeframe.

Pattern:

```text
data/derived/{SYMBOL}-{1h|1d|1w}.parquet
```

### Use the normalized histories when

- You want OHLCV before indicators are added.
- You need provider provenance for every canonical bar.
- You are building your own indicators from validated bars.
- You want efficient year-partitioned reads.

Pattern:

```text
data/normalized/timeframe={1h|1d}/symbol={SYMBOL}/year={YEAR}/bars.parquet
```

Weekly bars are generated from daily data, so weekly files are stored under `data/derived/` rather than `data/normalized/`.

### Use the inbox payloads when

- You need to audit the exact provider response.
- You want to reproduce an import.
- You are diagnosing a discrepancy between providers.

Inbox files are not the recommended input for ordinary research. Use normalized or derived data unless you specifically need provider-level evidence.

## 7. Open the latest summary

### Excel

Open this file directly:

```text
data/latest/focus_summary.csv
```

In Excel, enable filters on the header row. Useful filters include:

- `timeframe = 1d`
- `rsi_14 < 30`
- `relative_volume_20 > 1.5`
- `macd_state = bullish`
- `trend_state = above_sma_20_50_200`

### Python

```python
import pandas as pd

summary = pd.read_csv(
    "data/latest/focus_summary.csv",
    parse_dates=["timestamp_utc", "retrieved_at_utc"],
)

print(summary.head())
print(summary.shape)
print(summary["timeframe"].value_counts())
```

Show all three timeframes for AMD:

```python
amd = summary.loc[summary["symbol"] == "AMD"]

print(
    amd[
        [
            "symbol",
            "timeframe",
            "timestamp_utc",
            "close",
            "volume",
            "relative_volume_20",
            "rsi_14",
            "macd_state",
            "trend_state",
            "data_source",
        ]
    ]
)
```

Screen daily rows for low RSI and elevated volume:

```python
daily = summary.loc[summary["timeframe"] == "1d"].copy()

candidates = daily.loc[
    (daily["rsi_14"] < 35)
    & (daily["relative_volume_20"] > 1.25)
].sort_values(["rsi_14", "relative_volume_20"], ascending=[True, False])

print(
    candidates[
        [
            "symbol",
            "close",
            "rsi_14",
            "relative_volume_20",
            "macd_state",
            "trend_state",
        ]
    ]
)
```

The thresholds above are examples, not validated trading rules.

## 8. Read a complete calculated history

Read AMD daily history:

```python
import pandas as pd

amd_daily = pd.read_parquet("data/derived/AMD-1d.parquet")
amd_daily = amd_daily.sort_values("timestamp_utc")

print(amd_daily.tail(10))
```

Select common research columns:

```python
columns = [
    "timestamp_utc",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "rsi_14",
    "macd",
    "macd_signal",
    "sma_20",
    "sma_50",
    "sma_200",
    "stoch_k_14",
    "stoch_d_3",
    "relative_volume_20",
    "atr_14",
    "data_source",
]

print(amd_daily[columns].tail(20))
```

Use a different symbol or timeframe by changing the filename:

```python
pltr_hourly = pd.read_parquet("data/derived/PLTR-1h.parquet")
qqq_weekly = pd.read_parquet("data/derived/QQQ-1w.parquet")
```

## 9. Load derived data with a reusable function

```python
from pathlib import Path
import pandas as pd

REPOSITORY = Path(
    r"C:\Users\molyu\.codex\.chatgpt-projects"
    r"\g-p-6a84f884f2cc8191a6925a21ab8f7c3e"
    r"\stock-focus-data"
)


def load_derived(
    symbol: str,
    timeframe: str,
    repository: Path = REPOSITORY,
) -> pd.DataFrame:
    symbol = symbol.upper()
    if timeframe not in {"1h", "1d", "1w"}:
        raise ValueError("timeframe must be 1h, 1d, or 1w")
    path = repository / "data" / "derived" / f"{symbol}-{timeframe}.parquet"
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_parquet(path).sort_values("timestamp_utc")


amd = load_derived("AMD", "1d")
print(amd.tail())
```

If the Python program is saved inside the repository, use `Path.cwd()` or a path relative to the program instead of hard-coding the full Windows location.

## 10. Load canonical normalized OHLCV data

Normalized data is partitioned by timeframe, symbol, and year. Read every retained daily AMD partition:

```python
from pathlib import Path
import pandas as pd

directory = Path("data/normalized/timeframe=1d/symbol=AMD")
files = sorted(directory.glob("year=*/bars.parquet"))

if not files:
    raise FileNotFoundError(directory)

amd_daily = pd.concat(
    [pd.read_parquet(path) for path in files],
    ignore_index=True,
).sort_values("timestamp_utc")

print(amd_daily.tail())
print(amd_daily["data_source"].value_counts())
```

Load one year partition only:

```python
amd_2026 = pd.read_parquet(
    "data/normalized/timeframe=1d/symbol=AMD/year=2026/bars.parquet"
)
```

Load every canonical daily symbol:

```python
from pathlib import Path
import pandas as pd

files = sorted(
    Path("data/normalized/timeframe=1d").glob(
        "symbol=*/year=*/bars.parquet"
    )
)

all_daily = pd.concat(
    [pd.read_parquet(path) for path in files],
    ignore_index=True,
).sort_values(["symbol", "timestamp_utc"])

print(all_daily.groupby("symbol").size())
```

## 11. Plot price and indicators

Install Matplotlib if it is not already installed:

```bash
python -m pip install matplotlib
```

Plot AMD closing price and moving averages:

```python
import matplotlib.pyplot as plt
import pandas as pd

data = pd.read_parquet("data/derived/AMD-1d.parquet")
data = data.sort_values("timestamp_utc").set_index("timestamp_utc")

ax = data[["close", "sma_20", "sma_50", "sma_200"]].plot(
    figsize=(12, 6),
    title="AMD daily close and moving averages",
)
ax.set_ylabel("Price")
ax.grid(alpha=0.25)
plt.tight_layout()
plt.show()
```

Plot RSI:

```python
ax = data["rsi_14"].plot(
    figsize=(12, 4),
    title="AMD daily RSI(14)",
)
ax.axhline(70, color="red", linestyle="--", alpha=0.6)
ax.axhline(30, color="green", linestyle="--", alpha=0.6)
ax.set_ylim(0, 100)
ax.grid(alpha=0.25)
plt.tight_layout()
plt.show()
```

## 12. Export Parquet for Excel or another program

Excel can open the summary CSV directly. For a complete derived history, convert Parquet to CSV:

```python
import pandas as pd

data = pd.read_parquet("data/derived/AMD-1d.parquet")
data.to_csv("AMD-1d.csv", index=False)
```

Export all three AMD timeframes to one Excel workbook:

```bash
python -m pip install openpyxl
```

```python
import pandas as pd

with pd.ExcelWriter("AMD-research.xlsx", engine="openpyxl") as writer:
    for timeframe in ("1h", "1d", "1w"):
        data = pd.read_parquet(f"data/derived/AMD-{timeframe}.parquet")
        data.to_excel(writer, sheet_name=timeframe, index=False)
```

## 13. Normalized data columns

Each normalized bar contains these columns:

| Column | Meaning |
|---|---|
| `symbol` | Uppercase ticker |
| `timeframe` | `1h` or `1d` |
| `timestamp_utc` | Bar start timestamp in UTC |
| `session_date` | Associated trading-session date |
| `open` | First price in the bar |
| `high` | Highest price in the bar |
| `low` | Lowest price in the bar |
| `close` | Last price in the bar; not necessarily an official settlement price |
| `volume` | Shares reported for the bar |
| `vwap` | Provider-reported volume-weighted price when available |
| `trade_count` | Provider-reported trade count when available |
| `data_source` | `robinhood`, `alpaca`, or `derived` |
| `retrieved_at_utc` | Time the payload was imported |
| `validation_status` | Normally `valid` after validation |
| `fallback_reason` | Why Alpaca supplied the bar, when applicable |

`vwap`, `trade_count`, and `fallback_reason` may be empty because the source does not always provide them.

## 14. Derived indicator columns

Derived files include every normalized column plus:

| Column | Calculation or interpretation |
|---|---|
| `rsi_14` | 14-bar RSI using Wilder-style exponentially weighted gains and losses |
| `ema_12`, `ema_26`, `ema_50` | Exponential moving averages |
| `macd` | `ema_12 - ema_26` |
| `macd_signal` | 9-bar EMA of MACD |
| `macd_histogram` | `macd - macd_signal` |
| `sma_20`, `sma_50`, `sma_200` | Simple moving averages |
| `distance_sma_20`, `distance_sma_50`, `distance_sma_200` | `close / SMA - 1` |
| `atr_14` | 14-bar Wilder-style average true range |
| `stoch_k_14` | Close position inside the rolling 14-bar high/low range, scaled 0–100 |
| `stoch_d_3` | Three-bar average of stochastic %K |
| `volume_avg_5`, `volume_avg_20`, `volume_avg_50` | Rolling average volume |
| `relative_volume_20` | `volume / volume_avg_20` |
| `return_1`, `return_5`, `return_20` | Percentage change expressed as a decimal |
| `realized_volatility_20` | 20-bar log-return volatility, annualized by timeframe |
| `running_peak` | Highest close observed so far in the retained file |
| `drawdown` | `close / running_peak - 1` |
| `high_52w`, `low_52w` | Rolling 52-week high/low for daily and weekly data |
| `range_52w_position` | Position between the rolling 52-week low and high, from 0 to 1 |

Annualization factors for realized volatility are:

- Hourly: `252 × 6.5`
- Daily: `252`
- Weekly: `52`

Returns, moving-average distances, volatility, drawdown, and 52-week position are decimals. For example, `0.05` means 5%, while `-0.20` means -20%.

## 15. Latest-summary-only columns

The summary adds two categorical interpretations:

| Column | Values |
|---|---|
| `macd_state` | `bullish`, `bearish`, or `insufficient_history` |
| `trend_state` | `above_sma_20_50_200`, `below_sma_20_50_200`, or `mixed_or_insufficient_history` |

These labels describe indicator relationships. They are not trade recommendations.

## 16. Missing indicator values

Empty values near the start of a history are expected because rolling indicators require warm-up bars:

- RSI and ATR require 14 bars.
- SMA 20 requires 20 bars.
- SMA 50 requires 50 bars.
- SMA 200 requires 200 bars.
- Daily 52-week fields require 252 daily bars.
- Weekly 52-week fields require 52 weekly bars.
- Hourly 52-week fields are intentionally empty.

Recently listed symbols may therefore have valid prices but missing long-lookback indicators.

When screening, explicitly exclude missing values:

```python
daily = summary.loc[summary["timeframe"] == "1d"].copy()
daily = daily.dropna(subset=["rsi_14", "relative_volume_20"])
```

## 17. Source selection and provenance

The canonical store uses these source priorities for the same bar:

1. Robinhood
2. Derived data
3. Alpaca

For daily data, duplicate detection uses `symbol + timeframe + session_date`. This prevents Robinhood midnight timestamps and Alpaca market-open-offset timestamps from creating two bars for the same session.

For hourly data, duplicate detection uses `symbol + timeframe + timestamp_utc`.

Important details:

- Robinhood interpolated gap-fill bars are excluded.
- Internally inconsistent OHLC bars are excluded.
- Alpaca hourly imports are restricted to regular-session bar-start hours in New York time.
- Alpaca fills timestamps or ranges for which Robinhood has no usable bar.
- Raw inbox payloads remain unchanged even when a row is excluded from canonical data.

Count canonical bars by source:

```python
print(
    all_daily.groupby(["symbol", "data_source"])
    .size()
    .rename("bars")
)
```

## 18. Timezones and market dates

`timestamp_utc` is timezone-aware UTC in Parquet files. Convert it for display without modifying the stored value:

```python
data = pd.read_parquet("data/derived/QQQ-1h.parquet")
data["timestamp_new_york"] = data["timestamp_utc"].dt.tz_convert(
    "America/New_York"
)

print(data[["timestamp_utc", "timestamp_new_york", "close"]].tail())
```

Daily timestamps are normalized to midnight UTC in the canonical store. Use `session_date` when grouping or joining daily bars by trading date.

## 19. Weekly data behavior

Weekly bars are derived from validated daily bars using Friday-ending weeks:

- Open: first daily open in the week
- High: maximum daily high
- Low: minimum daily low
- Close: last daily close
- Volume: sum of daily volume
- Source: `derived`

The latest incomplete week is retained in the derived history with an internal completion flag, but the compact summary selects complete rows when that flag is available.

## 20. Inspect raw provider payloads

Read a Robinhood JSON batch:

```python
import json
from pathlib import Path

path = Path(
    "data/inbox/robinhood/range/"
    "day-2024-08-27_2026-08-27-batch-01.json"
)

payload = json.loads(path.read_text(encoding="utf-8"))

for result in payload["data"]["results"]:
    print(result["symbol"], len(result.get("bars") or []))
```

Read an Alpaca JSON batch:

```python
import json
from pathlib import Path

path = Path(
    "data/inbox/alpaca/range/"
    "day-2024-08-27_2026-08-27-batch-01.json"
)

payload = json.loads(path.read_text(encoding="utf-8"))

for symbol, bars in payload["bars"].items():
    print(symbol, len(bars))
```

Do not assume a raw provider bar passed canonical validation. Use normalized data for ordinary analysis.

## 21. Inspect collection manifests

Run manifests are in `logs/`:

```python
import json
from pathlib import Path

for path in sorted(Path("logs").glob("run-*.json")):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    print(path.name, manifest.get("command"))
```

Manifests record details such as command type, timeframe, input files, row counts, source statuses, failures, and retrieval windows.

## 22. Refresh and rebuild the data

The standalone project cannot sign in to Robinhood. Robinhood history must first be retrieved through the connected Codex/Robinhood boundary and saved as an unchanged JSON payload under `data/inbox/robinhood/`.

Import a Robinhood payload:

```powershell
stock-focus import-robinhood `
  --input data/inbox/robinhood/example-day.json `
  --timeframe 1d
```

Import a connected Alpaca payload:

```powershell
stock-focus import-alpaca `
  --input data/inbox/alpaca/example-day.json `
  --timeframe 1d
```

After imports, regenerate indicators and the compact summary:

```powershell
stock-focus rebuild
stock-focus summarize
```

Validate the configured universe:

```powershell
stock-focus validate-config
```

Run all tests:

```powershell
python -m pytest -q
```

## 23. Commit and publish refreshed data

Review changes before committing:

```bash
git status
git diff --stat
```

Commit the new data and generated files:

```bash
git add -A
git commit -m "data: refresh market history"
```

Upload the commit:

```bash
git push origin main
```

Keep the GitHub repository private if raw provider payloads or logs should not be public. Never commit `.env`, API keys, authentication tokens, brokerage account identifiers, positions, orders, or balances.

## 24. Common problems

### `ModuleNotFoundError: No module named 'pyarrow'`

Install the Parquet engine:

```bash
python -m pip install pyarrow
```

### `FileNotFoundError`

Confirm that the terminal is in the repository root:

```bash
git rev-parse --show-toplevel
```

Also confirm the symbol and timeframe spelling. Symbols are uppercase and timeframes are `1h`, `1d`, or `1w`.

### GitHub does not preview a Parquet file

Clone or download the repository, then use `pandas.read_parquet`. GitHub's browser interface is not the main interface for analyzing binary Parquet data.

### Long-lookback indicators are empty

The symbol may not have enough retained or post-listing bars. See the warm-up requirements in the missing-values section.

### Two providers report different prices or volume

Inspect `data_source`, `retrieved_at_utc`, and the corresponding raw inbox payloads. Robinhood is preferred for duplicate canonical timestamps, while Alpaca fills unavailable ranges. Provider feeds can differ in adjustment conventions, venue coverage, and bar construction.

### `git pull --ff-only` is rejected

Run:

```bash
git status
git log --oneline --graph --decorate --all -10
```

Resolve or commit local changes before pulling. Do not force-push unless you intentionally want to replace remote history.

## 25. Recommended workflow

For everyday use:

1. Run `git pull --ff-only origin main` to retrieve the newest committed data.
2. Open `data/latest/focus_summary.csv` for a quick market overview.
3. Use `data/derived/{SYMBOL}-{TIMEFRAME}.parquet` for historical analysis.
4. Use normalized partitions when provenance or custom indicators matter.
5. Check `data_source` and missing values before interpreting a result.
6. Treat every screen or indicator as research evidence, not an automatic trading decision.

For the project overview and collection commands, also see the repository [`README.md`](../README.md).
