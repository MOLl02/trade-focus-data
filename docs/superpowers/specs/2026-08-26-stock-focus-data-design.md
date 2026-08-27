# Stock Focus Data: Local Repository Design

## Purpose

Build a local, private-by-default repository that stores and analyzes market data for a fixed focus universe. The first phase runs locally and does not publish to GitHub or create a recurring schedule. Robinhood is the preferred data source; Alpaca fills unavailable or incomplete ranges.

This repository is for research and monitoring. It will not place, preview, modify, or cancel trades.

## Focus Universe

The repository tracks 32 approved symbols:

`AAOI, AAPL, AMD, AMZN, APP, AXTI, CBRS, COHR, CRWD, CRWV, FN, GH, GOOGL, LITE, LLY, META, MRVL, MSFT, MU, NBIS, NOW, NVDA, PLTR, QQQ, RDW, RKLB, SEDG, SNDK, SOXX, SPCX, TSLA, WOLF`

QQQ and SOXX are the only ETFs in scope. Leveraged, inverse, and single-stock leveraged ETFs are excluded.

The universe is maintained in `config/universe.yaml`. Data collection must use this file rather than a second hard-coded symbol list.

## Scope

### Included in the local phase

- Hourly and daily OHLCV candles obtained directly from the available sources.
- Weekly OHLCV candles derived from validated daily data.
- Raw, normalized, derived, and latest-summary datasets.
- Robinhood-first source selection with Alpaca fallback.
- Data validation, provenance, logging, tests, and a local command-line workflow.
- A sample end-to-end collection before collecting the full universe.

### Deferred until the local phase is approved

- Publishing the repository to GitHub.
- Recurring hourly and end-of-day scheduling.
- Dashboards, alerts, trade execution, portfolio accounting, and options data.

## Architecture

The repository uses small modules with clear boundaries:

1. **Universe loader** reads and validates the approved symbols and their asset types.
2. **Source adapters** convert Robinhood and Alpaca responses into one normalized candle schema.
3. **Collector** consumes a Robinhood import for a symbol and timeframe first, detects missing or unusable ranges, and requests only those ranges from Alpaca.
4. **Validator** rejects malformed rows, reports gaps, and prevents incomplete data from replacing valid history.
5. **Storage layer** merges validated bars idempotently and writes partitioned Parquet history plus viewable CSV summaries.
6. **Weekly aggregator** derives weekly candles from validated daily bars using the market-session calendar.
7. **Indicator engine** calculates the approved indicators separately for hourly, daily, and weekly histories.
8. **Summary builder** produces a compact latest row for every symbol and timeframe.
9. **CLI** provides explicit commands for sample collection, full refresh, validation, indicator rebuilding, and summary generation.

Connected Robinhood access is available through Codex rather than as a normal credential that a standalone script can safely embed. In the local phase, Robinhood responses enter through a normalized import boundary managed from this task. The standalone collector can call Alpaca using locally supplied environment variables. The repository will not depend on an unofficial Robinhood login library or store Robinhood credentials.

## Repository Layout

```text
stock-focus-data/
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── config/
│   └── universe.yaml
├── docs/
│   └── superpowers/specs/
├── src/stock_focus_data/
│   ├── cli.py
│   ├── config.py
│   ├── models.py
│   ├── collection.py
│   ├── validation.py
│   ├── storage.py
│   ├── aggregation.py
│   ├── indicators.py
│   ├── summaries.py
│   └── sources/
│       ├── base.py
│       ├── robinhood_import.py
│       └── alpaca.py
├── data/
│   ├── inbox/robinhood/
│   ├── raw/
│   ├── normalized/
│   ├── derived/
│   └── latest/
├── logs/
└── tests/
```

Credentials and local runtime artifacts are ignored. `.env.example` documents variable names without containing secrets.

## Candle Data Model

Every normalized bar contains:

- `symbol`
- `timeframe` (`1h`, `1d`, or `1w`)
- `timestamp_utc`
- `session_date`
- `open`, `high`, `low`, `close`
- `volume`
- `vwap` and `trade_count` when the source provides them
- `data_source` (`robinhood`, `alpaca`, or `derived`)
- `retrieved_at_utc`
- `validation_status`
- `fallback_reason` when Alpaca was used

Raw source payloads remain unchanged. Normalized and derived datasets may be rebuilt from raw inputs. Historical storage is partitioned by timeframe, symbol, and calendar year to limit file growth.

## Data Flow

1. Load the universe and requested timeframe.
2. Read the newest stored timestamp for each symbol.
3. Use the Codex-connected Robinhood adapter to place the required hourly or daily payload in the local import inbox.
4. Validate the imported response and identify unresolved symbols or missing ranges.
5. Request only unresolved or missing data from Alpaca.
6. Normalize both sources and retain row-level provenance.
7. Merge by `(symbol, timeframe, timestamp_utc)` without duplicating bars.
8. Prefer a valid Robinhood bar when both sources cover the same timestamp; retain the fallback decision in the run manifest.
9. Derive weekly bars from daily data after daily validation succeeds.
10. Calculate timeframe-specific indicators and rebuild the latest summaries.
11. Write a run manifest containing counts, gaps, source use, validation results, and errors.

Weekly aggregation uses the first session open, maximum high, minimum low, last session close, and summed volume for each exchange week. Partial current weeks are marked incomplete rather than presented as finalized weekly bars.

## Indicators

Indicators are calculated independently for hourly, daily, and weekly histories when sufficient lookback exists:

- RSI(14)
- MACD(12, 26, 9), including MACD line, signal line, and histogram
- SMA(20), SMA(50), and SMA(200)
- EMA(12), EMA(26), and EMA(50)
- ATR(14)
- Stochastic %K(14) and %D(3)
- Relative volume against a 20-bar average
- Rolling volume averages over 5, 20, and 50 bars
- Returns over 1, 5, and 20 bars
- Realized volatility over 20 bars, annualized with a timeframe-appropriate factor
- Running peak and drawdown
- Percentage distance from the 20-, 50-, and 200-bar moving averages
- 52-week high, low, and range position for daily and weekly summaries

Unavailable indicators remain null until enough history exists; they are never filled with zero.

## Latest Summary

`data/latest/focus_summary.csv` contains one row per symbol and timeframe with:

- Latest complete candle timestamp and close
- Current and average volume
- RSI, MACD state, stochastic K/D, and ATR
- SMA/EMA values and price distance from each trend average
- Short- and medium-horizon returns
- Realized volatility and drawdown
- 52-week range position where applicable
- Source, validation status, and retrieval time

The summary is a convenience view. Historical Parquet files remain the canonical normalized datasets.

## Reliability and Error Handling

- Retry temporary source failures with bounded exponential backoff.
- Fall back to Alpaca at the symbol/range level rather than abandoning an entire run.
- Reject rows with invalid timestamps, negative volume, non-finite prices, `high < max(open, close, low)`, or `low > min(open, close, high)`.
- Deduplicate on the normalized primary key and make reruns idempotent.
- Detect expected-session gaps without inventing candles for periods with no trading.
- Write new data through a temporary file and replace the target only after validation succeeds.
- Never replace valid history with an empty, truncated, or invalid response.
- Keep successful symbols when another symbol fails; return a non-success run status with precise error details.
- Record all fallback decisions and unresolved gaps in a timestamped run manifest.

## Testing and Acceptance Criteria

Unit tests cover universe validation, source normalization, merge precedence, duplicate handling, OHLCV validation, weekly aggregation, each indicator, insufficient-lookback behavior, and summary generation.

Integration tests use fixed local fixtures and do not require live credentials. A live smoke test runs first on `AMD`, `PLTR`, `QQQ`, and `SOXX`, covering individual stocks and both approved ETFs.

The local phase is accepted when:

1. A clean setup can install the package and run the documented CLI.
2. The sample symbols produce validated hourly, daily, and derived weekly candles.
3. Indicators match independently calculated fixture expectations within documented numerical tolerances.
4. Rerunning collection produces no duplicate bars.
5. A simulated Robinhood failure uses Alpaca and records the fallback reason.
6. Invalid or incomplete input cannot overwrite valid stored history.
7. The full 32-symbol universe can generate a latest summary with explicit status for every symbol.
8. No credential, account number, order capability, or portfolio holding is committed.

## Future Scheduling and Publication

After local verification, a separate approved phase may create a private GitHub repository and schedule hourly market-session updates plus one post-close daily finalization. That phase must preserve the same data contracts and must not expose credentials or brokerage-account information.
