# Support and Resistance Calculation Design

Date: 2026-09-01

Status: approved design, pending implementation

## 1. Purpose

Add a reproducible support and resistance calculation to the stock-focus-data repository. The calculation covers every symbol in `config/universe.yaml` and produces both:

1. Multi-timeframe structural levels derived from confirmed hourly, daily, and weekly swing prices.
2. Traditional classic daily and weekly pivot levels.

The result is research data only. It does not forecast price, recommend a trade, size a position, or place an order.

## 2. Scope

The feature will:

- Read the existing indicator-enriched Parquet histories under `data/derived/`.
- Calculate levels for all configured stocks plus QQQ and SOXX.
- Use a common completed daily analysis date across the universe.
- Write one compact CSV for human review and one long-form Parquet dataset for programmatic analysis.
- Add an explicit CLI command.
- Document the formulas, fields, and limitations.
- Add deterministic automated tests before production code is written.

The feature will not:

- Fetch market data itself; refresh remains a separate pipeline step.
- Use machine learning, order-book data, options data, or fundamental data.
- infer levels beyond the retained history.
- fabricate structural levels when the history has too few confirmed pivots.

## 3. Inputs and analysis date

### 3.1 Required inputs

For each symbol, the calculation reads:

- `data/derived/{SYMBOL}-1h.parquet`
- `data/derived/{SYMBOL}-1d.parquet`
- `data/derived/{SYMBOL}-1w.parquet`

The configured universe comes from `config/universe.yaml`.

### 3.2 Common analysis date

The default analysis date is the most recent `session_date` for which every configured symbol has a validated daily bar. Using a common date prevents a result from silently comparing symbols with different price endpoints.

An optional CLI `--analysis-date YYYY-MM-DD` override may select an earlier date. The command must reject an override unless every configured symbol has a daily bar for that date.

For each symbol:

- `current_price` is the close of the daily bar on the analysis date.
- `price_timestamp_utc` is that daily bar's timestamp.
- All source rows later than the analysis date are excluded.
- Weekly rows are included only when `is_complete` is true and their period ends no later than the analysis date.

The first production run is expected to use 2026-09-01, the latest common completed daily date in the refreshed repository.

## 4. Multi-timeframe structural method

### 4.1 Lookback windows

The structural calculation uses:

| Timeframe | Lookback | Pivot window | Base weight | Recency half-life |
|---|---:|---:|---:|---:|
| Hourly (`1h`) | 90 calendar days | 3 bars left and 3 bars right | 1.0 | 30 days |
| Daily (`1d`) | 365 calendar days | 3 bars left and 3 bars right | 2.0 | 90 days |
| Weekly (`1w`) | All retained completed rows | 2 bars left and 2 bars right | 3.0 | 180 days |

Lookbacks are measured backward from the analysis date. Rows outside the relevant window are ignored.

### 4.2 Confirmed swing candidates

A bar is a confirmed swing low when its `low` is strictly lower than every other low in its complete left/right pivot window. A bar is a confirmed swing high when its `high` is strictly higher than every other high in its complete left/right pivot window.

Bars without the full number of required observations on both sides are not candidates. This prevents edge values from being treated as confirmed pivots and prevents the calculation from looking beyond the selected analysis date.

Each candidate records:

- Symbol
- Timeframe
- Timestamp
- Price (`low` for a swing low; `high` for a swing high)
- Origin kind (`swing_low` or `swing_high`)
- Timeframe base weight
- Recency weight
- Combined candidate weight

Swing highs and lows enter the same clustering pool. A historical swing high below current price can become support after a breakout, and a historical swing low above current price can become resistance after a breakdown.

### 4.3 Candidate weighting

For a candidate with age `age_days`:

```text
recency_weight = 0.5 ** (age_days / half_life_days)
candidate_weight = timeframe_base_weight * recency_weight
```

Age is never negative. More recent candidates and candidates from higher timeframes therefore contribute more to a cluster's representative value and strength.

### 4.4 Volatility-aware clustering tolerance

The latest available daily ATR(14) on or before the analysis date is used when present:

```text
cluster_tolerance = max(current_price * 0.005, daily_atr_14 * 0.25)
```

If ATR(14) is unavailable, the tolerance is `current_price * 0.005`.

This avoids using a single absolute dollar threshold for both low-priced and high-priced securities.

### 4.5 Deterministic clustering

Candidates are sorted by price, timestamp, timeframe, and origin kind. The algorithm scans upward by price:

1. The first candidate starts the first cluster.
2. A later candidate joins the current cluster when its price is within `cluster_tolerance` of the cluster's current weighted mean.
3. The weighted mean is recalculated after each addition.
4. Otherwise, the candidate starts a new cluster.

For each cluster:

```text
level_value = sum(candidate_price * candidate_weight) / sum(candidate_weight)
strength_score = sum(candidate_weight)
touch_count = number of confirmed swing candidates in the cluster
```

The cluster also records its distinct contributing timeframes, most recent candidate timestamp, and swing-high/swing-low counts. `strength_score` is useful for ranking levels within one symbol; it is not presented as a universally comparable probability.

### 4.6 Support and resistance classification

- Clusters strictly below `current_price` are supports.
- Clusters strictly above `current_price` are resistances.
- A cluster exactly equal to current price is omitted because it is neither clearly support nor resistance.

Supports are ordered from highest to lowest so support 1 is nearest to current price. Resistances are ordered from lowest to highest so resistance 1 is nearest to current price.

The default output contains the nearest three supports and nearest three resistances. If fewer than three defensible clusters exist on one side, the remaining fields are null; the program must not invent values.

For every structural level:

```text
distance_pct = level_value / current_price - 1
```

Support distances are negative and resistance distances are positive.

## 5. Traditional classic pivot method

### 5.1 Reference bars

Daily pivots use the completed daily high, low, and close on the analysis date. They are reference levels for the next trading session.

Weekly pivots use the most recent completed weekly high, low, and close whose period ends on or before the analysis date. They are reference levels for the active/upcoming trading week.

Incomplete weekly rows must never be used.

### 5.2 Formulas

Given reference high `H`, low `L`, and close `C`:

```text
P  = (H + L + C) / 3
R1 = 2 * P - L
S1 = 2 * P - H
R2 = P + (H - L)
S2 = P - (H - L)
R3 = H + 2 * (P - L)
S3 = L - 2 * (H - P)
```

The same formulas are applied independently to the daily and weekly reference bars.

## 6. Outputs

### 6.1 Compact CSV

Path:

```text
data/latest/support_resistance.csv
```

The file contains exactly one row per configured symbol, ordered as the universe configuration. Core columns are:

- `symbol`
- `analysis_date`
- `current_price`
- `price_timestamp_utc`
- `calculation_status`
- `warning`

For each `mt_support_1` through `mt_support_3` and `mt_resistance_1` through `mt_resistance_3`, the CSV contains:

- Level value
- Distance percentage
- Touch count
- Strength score
- Pipe-delimited contributing timeframes
- Most recent touch timestamp

Traditional daily columns are:

- `daily_reference_date`
- `daily_pivot`
- `daily_s1`, `daily_s2`, `daily_s3`
- `daily_r1`, `daily_r2`, `daily_r3`

Traditional weekly columns are:

- `weekly_reference_period_end`
- `weekly_pivot`
- `weekly_s1`, `weekly_s2`, `weekly_s3`
- `weekly_r1`, `weekly_r2`, `weekly_r3`

### 6.2 Long-form Parquet

Path:

```text
data/derived/support_resistance_levels.parquet
```

Each row is one level. Columns are:

- `symbol`
- `analysis_date`
- `current_price`
- `method` (`multi_timeframe` or `classic`)
- `reference_timeframe` (`multi`, `1d`, or `1w`)
- `level_name`
- `side` (`support`, `pivot`, or `resistance`)
- `rank`
- `level_value`
- `distance_pct`
- `touch_count`
- `strength_score`
- `contributing_timeframes`
- `last_touch_utc`
- `reference_period_end`

Fields that do not apply to classic pivots are null. Structural levels that do not exist are absent from the long-form dataset and null in the compact CSV.

## 7. Program structure

A new focused module, `src/stock_focus_data/support_resistance.py`, will contain pure calculation functions and a repository-level builder. Planned boundaries are:

- `classic_pivots(high, low, close)` calculates P/S1-S3/R1-R3.
- `find_swing_candidates(frame, timeframe, analysis_date)` finds confirmed pivots for one timeframe.
- `cluster_candidates(candidates, current_price, atr_14)` calculates deterministic structural clusters.
- `select_nearest_levels(clusters, current_price, count)` classifies and ranks support/resistance.
- `calculate_symbol_levels(hourly, daily, weekly, analysis_date)` returns the compact symbol record and long-form rows.
- `build_support_resistance(root, entries, analysis_date, levels)` loads every configured symbol and returns both output frames.

The CLI remains responsible for argument parsing and writing files, not calculation logic.

## 8. CLI behavior

Add:

```text
stock-focus support-resistance
```

Options:

- `--root data`
- `--config config/universe.yaml`
- `--analysis-date YYYY-MM-DD` (optional; default is latest common daily date)
- `--levels 3` (default 3; valid range 1 through 10)

On success, the command writes both outputs and prints the analysis date, symbol count, structural level count, and output paths.

The command exits nonzero without replacing existing output files when:

- No common daily analysis date exists.
- A configured symbol lacks a daily bar on the requested analysis date.
- Required OHLC fields are invalid.
- The compact output does not contain exactly one row per configured symbol.

Missing hourly or weekly history produces `calculation_status=partial` and a warning for that symbol while preserving available daily classic pivots. The current repository is expected to produce complete status for all 32 symbols.

## 9. Documentation

Update `README.md` and `docs/DATA_USAGE_GUIDE.md` with:

- The new command.
- Both output locations.
- Exact formulas and structural algorithm summary.
- Python and Excel loading examples.
- Explanations of distance, touch count, score, timeframes, reference dates, and partial/null values.
- A reminder that levels are descriptive historical references, not guaranteed future barriers or trading advice.

## 10. Testing strategy

Implementation follows test-driven development. Tests are written and observed failing before production code is added.

Unit tests cover:

1. Exact classic pivot results for a known H/L/C example.
2. Rejection of invalid H/L/C input.
3. Strict swing-high and swing-low detection.
4. Exclusion of edge bars without a complete confirmation window.
5. Exclusion of rows after the analysis date.
6. Exclusion of incomplete weekly bars.
7. Volatility-aware tolerance with ATR and without ATR.
8. Deterministic cluster weighted means, touch counts, timeframes, and strength.
9. Role reversal by classifying all clusters relative to current price.
10. Nearest-first support and resistance ordering.
11. Null/absent structural levels when fewer than the requested count exist.
12. Daily and weekly reference-bar selection.

Integration and CLI tests cover:

1. Latest common analysis-date selection.
2. Explicit analysis-date validation.
3. Exactly one compact row for every configured symbol.
4. Long-form output schema and methods.
5. Nonzero exit and no partial replacement on fatal input errors.
6. Partial status when hourly or weekly data is missing.
7. Successful writing of both output files.

## 11. Production verification

After implementation, run the command against the refreshed repository and verify:

- Analysis date is 2026-09-01.
- Compact CSV has 32 unique symbols and 32 rows.
- Every symbol has finite daily and weekly P/S1-S3/R1-R3 values.
- Every emitted structural support is below current price.
- Every emitted structural resistance is above current price.
- Support ranks descend by value and resistance ranks ascend by value.
- Distance signs match level sides.
- Weekly references use completed weeks only.
- Both files can be reloaded by pandas without schema loss.
- A second run produces data-equivalent outputs.
- The full automated test suite passes.
- `git diff --check` reports no whitespace errors.

## 12. Acceptance criteria

The feature is complete when:

1. Both approved calculation methods are implemented exactly as specified.
2. The CLI generates both outputs for all 32 configured symbols.
3. Tests demonstrate the intended behavior through red-green TDD.
4. Production verification passes on the data through 2026-09-01.
5. Documentation makes the outputs usable locally and from a Git clone.
6. Code, tests, documentation, and generated outputs are committed locally without publishing or placing trades.
