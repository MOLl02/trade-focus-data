# Interactive Support and Resistance Chart Design

Date: 2026-09-01

Status: approved design, pending implementation

## 1. Purpose

Add reproducible interactive charts for every symbol in `config/universe.yaml`. Each chart combines retained daily price history with the multi-timeframe structural levels and classic daily/weekly pivots already defined by the support-and-resistance calculation.

The charts are research visualizations. They do not forecast price, recommend a trade, size a position, or place an order.

## 2. Scope

The feature will:

- Generate one interactive HTML page for each of the 32 configured symbols.
- Generate a searchable HTML index linking to every symbol page.
- Show a two-year overview and a six-month candlestick zoom on each page.
- Show every retained multi-timeframe structural level.
- Draw classic levels that fall inside the zoom price range and list all classic values in a side table.
- Work offline after cloning the repository by using one shared local Plotly JavaScript bundle.
- Record the calculation date, source ranges, symbols, and generated files in a manifest.
- Add a Typer CLI command, automated tests, and usage documentation.
- Publish the completed work from `feature/support-resistance-charts` as a pull request into `main`.

The feature will not:

- Fetch or refresh market data.
- Replace the existing compact CSV or long-form Parquet level outputs.
- Generate trading signals, predictions, alerts, or orders.
- Fabricate history or levels for a symbol with insufficient data.
- Depend on an internet connection when a generated chart is opened locally.

## 3. Command and inputs

The command is:

```powershell
stock-focus chart-support-resistance
```

The explicit production form is:

```powershell
stock-focus chart-support-resistance --analysis-date 2026-09-01
```

Options:

- `--root`, defaulting to `data`, locates derived histories.
- `--config`, defaulting to `config/universe.yaml`, selects the configured universe.
- `--analysis-date`, when present, must be a daily session shared by every configured symbol.
- `--output-root`, defaulting to `charts/support_resistance`, selects the chart publication root.
- `--levels`, defaulting to 3, remains consistent with the support-and-resistance calculation.

The command reads `data/derived/{SYMBOL}-1d.parquet` for chart history. It calls the existing `build_support_resistance` calculation directly for the same analysis date instead of trusting potentially stale published level files.

If `--analysis-date` is omitted, the existing latest-common-date rule selects the most recent daily session shared by the entire universe. All history later than the selected date is excluded.

## 4. Output layout

For analysis date `2026-09-01`, the default output is:

```text
charts/
  assets/
    plotly.min.js
  support_resistance/
    2026-09-01/
      index.html
      manifest.json
      AAOI.html
      AAPL.html
      ...
      WOLF.html
```

There is exactly one symbol page for each configured entry. File names use the validated uppercase ticker. All page links are relative so a cloned repository can be moved without breaking navigation.

The shared Plotly bundle is written once under `charts/assets/`. Symbol pages must reference that local file and must not require a CDN.

## 5. Symbol page design

### 5.1 Header and navigation

The page header contains:

- Symbol
- Analysis date
- Current close
- Calculation status and any warning
- A link back to `index.html`
- Previous/next symbol links in configured-universe order

### 5.2 Top panel: retained-history overview

The overview shows all retained daily observations on or before the analysis date, up to two calendar years. Newly listed symbols use all available history without padding.

Traces:

- Daily close as the primary line
- SMA(50), when available
- SMA(200), when available
- A marker on the analysis-date close

The overview supplies historical context; support and resistance lines are reserved for the zoom panel so current levels are not visually presented as if they existed throughout the full history.

### 5.3 Bottom panel: six-month candlestick zoom

The zoom begins six calendar months before the analysis date and includes every available daily bar through that date. If a symbol has less than six months of history, all available rows are shown.

The candlestick hover contains:

- Session date
- Open, high, low, and close
- Volume
- RSI(14), when available
- Data provider

The zoom y-range is derived from the minimum low and maximum high in the selected rows with a small visual margin. The range is computed before classic-level filtering.

### 5.4 Level overlays

All available multi-timeframe structural S1-S3 and R1-R3 levels are drawn on the zoom panel, including a level outside the candle range. Plotly may expand the y-axis so the complete structural set remains visible.

Classic daily and weekly P, S1-S3, and R1-R3 levels are drawn only when their values fall inside the original six-month candle price range including its margin. Every classic value remains visible in the level table even when its line is omitted from the plot.

Visual encoding:

| Meaning | Color | Line pattern |
|---|---|---|
| Support | Green | Determined by method |
| Resistance | Red | Determined by method |
| Pivot | Blue | Determined by method |
| Multi-timeframe | Side color | Solid |
| Classic daily | Side color | Dashed |
| Classic weekly | Side color | Dotted |

Rank affects line width and opacity: rank 1 is visually strongest, followed by ranks 2 and 3. Each line has a hover label containing the method, timeframe, level name, value, and distance from current price.

### 5.5 Level table

The page includes a table next to or directly below the plot, depending on viewport width. It lists every emitted structural and classic row with:

- Method
- Reference timeframe
- Level name and side
- Value
- Distance from current price
- Structural touch count and strength, when applicable
- Contributing timeframes, when applicable
- Reference period or last-touch time
- Whether the level is drawn on the zoom panel

The table provides complete values without forcing all classic lines into a crowded plot.

## 6. Index design

`index.html` contains a searchable, responsive table in configured-universe order. Each row contains:

- Symbol and asset type
- Current price
- Nearest structural support and resistance
- Daily and weekly pivots
- Calculation status
- Link to the symbol chart

The search works entirely in the browser with small inline JavaScript. The index links to the manifest and states the analysis date and generation scope.

## 7. Architecture and module boundaries

Add `src/stock_focus_data/charts.py` with focused units:

- History selection for the overview and zoom windows
- Candle-range calculation and classic-level visibility classification
- Plotly figure construction
- Level-table and page rendering
- Index and manifest construction
- Staged publication of an entire analysis-date result

The CLI remains responsible only for option parsing, loading the universe, calling the chart builder, publishing results, and printing a concise summary.

Rendering inputs are pandas DataFrames and simple value objects. Figure construction returns a Plotly `Figure`, allowing tests to inspect traces, axes, annotations, and shapes without running a browser.

## 8. Publication and failure behavior

The command performs all reads, calculations, validations, and rendering in a temporary staging directory under the output root. It publishes files only after every configured symbol, the index, the manifest, and the shared JavaScript asset have rendered successfully.

If any step fails:

- The command exits nonzero with the symbol and reason.
- Existing published files for that analysis date remain unchanged.
- Temporary files are removed.

When publication succeeds, each staged file replaces the matching target atomically. The versioned analysis-date directory prevents one run from overwriting a different date. The command does not delete unrelated chart directories or files.

## 9. Determinism and safety

- Symbols, traces, shapes, table rows, and index rows use stable ordering.
- Plot div identifiers derive from validated symbols instead of random UUIDs.
- Pages contain no generation timestamp; the manifest records the analysis date rather than wall-clock time.
- Numeric display uses stable formatting while the embedded figure preserves source precision.
- Symbols and displayed strings are HTML-escaped.
- No credentials, provider payloads, or environment variables enter generated pages.
- Repeated runs against identical inputs must produce identical symbol HTML, index HTML, and manifest content. The shared Plotly asset is version-dependent but identical within one installed version.

## 10. Dependency choice

Add `plotly>=6,<7` as a runtime dependency. Plotly provides native candlesticks, linked date axes, hover details, subplot composition, and standalone HTML output. A static Matplotlib-only approach was rejected because the approved output requires interactive HTML pages.

## 11. Testing and verification

Implementation follows red-green-refactor. Tests will cover:

1. Overview and six-month history selection, including short-history symbols.
2. Candle-range calculation and classic-level inclusion at, inside, and outside boundaries.
3. Figure structure: two panels, close/SMA traces, candlesticks, deterministic identifiers, and level shapes.
4. Structural levels always drawn and classic levels filtered only from the plot, not the table.
5. Hover data fields and level metadata.
6. Index ordering, search controls, relative links, and HTML escaping.
7. Manifest schema, symbol coverage, and stable serialization.
8. CLI generation into a temporary root.
9. Failure before publication preserving pre-existing chart files.
10. Offline pages referencing `charts/assets/plotly.min.js` with no CDN dependency.
11. Repeat generation producing byte-identical project-authored HTML and JSON.

Production verification will assert:

- Exactly 32 configured symbol pages, one index, and one manifest exist for 2026-09-01.
- Every page contains the correct symbol, analysis date, two-panel figure, and level table.
- The levels embedded in each page match a fresh support-and-resistance calculation.
- The index covers every configured symbol exactly once.
- Shared JavaScript exists and all relative asset links resolve.
- The complete automated test suite passes.
- AMD, SPCX, and WOLF are opened for visual inspection, covering full, short, and volatile histories.

## 12. Documentation

Update `README.md` and `docs/DATA_USAGE_GUIDE.md` with:

- The chart command and options
- Output paths
- Local opening instructions
- Git clone/opening instructions
- Explanation of both panels, level visibility, hover data, and table fields
- Regeneration workflow after refreshing market data
- Research-only limitations

## 13. Acceptance criteria

The feature is accepted when:

- The documented command creates the approved 32-page interactive chart set for 2026-09-01.
- Every chart uses the correct retained daily history and freshly calculated levels.
- The pages work without network access after cloning.
- All automated and production validations pass.
- Generated artifacts and implementation are committed on `feature/support-resistance-charts`.
- The branch is pushed and a pull request into `main` is created.
