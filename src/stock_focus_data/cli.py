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
from stock_focus_data.sources.alpaca_import import AlpacaImportSource
from stock_focus_data.sources.robinhood_import import RobinhoodImportSource
from stock_focus_data.storage import CandleStore, write_manifest
from stock_focus_data.summaries import build_latest_summary
from stock_focus_data.validation import validate_candles


app = typer.Typer(no_args_is_help=True)


class MissingFallback:
    def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        raise RuntimeError(
            "Alpaca credentials are required to fill missing Robinhood "
            f"data for {symbol} {timeframe.value}"
        )


@app.command("validate-config")
def validate_config(
    config: Path = typer.Option(Path("config/universe.yaml")),
) -> None:
    entries = load_universe(config)
    stocks = sum(entry.asset_type == "stock" for entry in entries)
    etfs = sum(entry.asset_type == "etf" for entry in entries)
    typer.echo(f"{len(entries)} symbols; {stocks} stocks; {etfs} ETFs")


@app.command("sample")
def sample(root: Path = typer.Option(Path("data"))) -> None:
    fixture = Path("tests/fixtures/robinhood_day.json")
    frame = RobinhoodImportSource.load(
        fixture, Timeframe.DAY, datetime.now(UTC)
    )
    store = CandleStore(root)
    store.merge(frame)
    daily = store.read("AMD", Timeframe.DAY)
    weekly = aggregate_weekly(daily, datetime.now(UTC))
    derived = root / "derived"
    derived.mkdir(parents=True, exist_ok=True)
    add_indicators(daily).to_parquet(
        derived / "AMD-1d.parquet", index=False
    )
    add_indicators(weekly).to_parquet(
        derived / "AMD-1w.parquet", index=False
    )
    typer.echo(f"sample complete: daily={len(daily)} weekly={len(weekly)}")


@app.command("import-robinhood")
def import_robinhood(
    input_path: Path = typer.Option(..., "--input"),
    timeframe: Timeframe = typer.Option(...),
    root: Path = typer.Option(Path("data")),
) -> None:
    frame = RobinhoodImportSource.load(
        input_path, timeframe, datetime.now(UTC)
    )
    validated = validate_candles(frame)
    CandleStore(root).merge(validated)
    manifest = {
        "command": "import-robinhood",
        "input": str(input_path),
        "timeframe": timeframe.value,
        "rows": len(validated),
        "symbols": sorted(validated["symbol"].unique().tolist()),
    }
    path = write_manifest(root.parent, manifest)
    typer.echo(f"imported {len(validated)} rows; manifest={path}")


@app.command("import-alpaca")
def import_alpaca(
    input_path: Path = typer.Option(..., "--input"),
    timeframe: Timeframe = typer.Option(...),
    root: Path = typer.Option(Path("data")),
) -> None:
    frame = AlpacaImportSource.load(
        input_path, timeframe, datetime.now(UTC)
    )
    validated = validate_candles(frame)
    CandleStore(root).merge(validated)
    manifest = {
        "command": "import-alpaca",
        "input": str(input_path),
        "timeframe": timeframe.value,
        "rows": len(validated),
        "symbols": sorted(validated["symbol"].unique().tolist()),
    }
    path = write_manifest(root.parent, manifest)
    typer.echo(f"imported {len(validated)} rows; manifest={path}")


@app.command("refresh")
def refresh(
    robinhood_input: list[Path] = typer.Option([], "--robinhood-input"),
    timeframe: Timeframe = typer.Option(...),
    start: str = typer.Option(...),
    end: str = typer.Option(...),
    root: Path = typer.Option(Path("data")),
    config: Path = typer.Option(Path("config/universe.yaml")),
) -> None:
    if timeframe is Timeframe.WEEK:
        raise typer.BadParameter("refresh supports 1h and 1d; rebuild derives 1w")
    start_time = pd.Timestamp(start)
    end_time = pd.Timestamp(end)
    if start_time.tzinfo is None:
        start_time = start_time.tz_localize("UTC")
    else:
        start_time = start_time.tz_convert("UTC")
    if end_time.tzinfo is None:
        end_time = end_time.tz_localize("UTC")
    else:
        end_time = end_time.tz_convert("UTC")
    retrieved = datetime.now(UTC)
    imported_frames = [
        RobinhoodImportSource.load(path, timeframe, retrieved)
        for path in robinhood_input
    ]
    imported = (
        pd.concat(imported_frames, ignore_index=True)
        if imported_frames
        else empty_candle_frame()
    )
    load_dotenv()
    key_id = os.getenv("APCA_API_KEY_ID", "")
    secret_key = os.getenv("APCA_API_SECRET_KEY", "")
    fallback = (
        AlpacaSource(
            key_id,
            secret_key,
            base_url=os.getenv(
                "APCA_DATA_BASE_URL", "https://data.alpaca.markets"
            ),
            feed=os.getenv("APCA_DATA_FEED", "iex"),
            raw_directory=root / "raw" / "alpaca",
        )
        if key_id and secret_key
        else MissingFallback()
    )
    store = CandleStore(root)
    statuses: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    for entry in load_universe(config):
        try:
            frame, status = collect_symbol(
                entry.symbol,
                timeframe,
                start_time.to_pydatetime(),
                end_time.to_pydatetime(),
                imported,
                fallback,
            )
            store.merge(frame)
            statuses.append(status)
        except Exception as exc:
            failures.append(
                {
                    "symbol": entry.symbol,
                    "timeframe": timeframe.value,
                    "error": str(exc),
                }
            )
    write_manifest(
        root.parent,
        {
            "command": "refresh",
            "timeframe": timeframe.value,
            "start": start_time,
            "end": end_time,
            "statuses": statuses,
            "failures": failures,
        },
    )
    typer.echo(f"refreshed={len(statuses)} failed={len(failures)}")
    if failures:
        raise typer.Exit(code=1)


@app.command("rebuild")
def rebuild(
    root: Path = typer.Option(Path("data")),
    config: Path = typer.Option(Path("config/universe.yaml")),
) -> None:
    store = CandleStore(root)
    entries = load_universe(config)
    derived_dir = root / "derived"
    derived_dir.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        daily = store.read(entry.symbol, Timeframe.DAY)
        if daily.empty:
            continue
        weekly = aggregate_weekly(daily, datetime.now(UTC))
        add_indicators(daily).to_parquet(
            derived_dir / f"{entry.symbol}-1d.parquet", index=False
        )
        add_indicators(weekly).to_parquet(
            derived_dir / f"{entry.symbol}-1w.parquet", index=False
        )
        hourly = store.read(entry.symbol, Timeframe.HOUR)
        if not hourly.empty:
            add_indicators(hourly).to_parquet(
                derived_dir / f"{entry.symbol}-1h.parquet", index=False
            )
    typer.echo("rebuilt derived datasets")


@app.command("summarize")
def summarize(
    root: Path = typer.Option(Path("data")),
    config: Path = typer.Option(Path("config/universe.yaml")),
) -> None:
    paths = sorted((root / "derived").glob("*.parquet"))
    expected_symbols = [entry.symbol for entry in load_universe(config)]
    summary = build_latest_summary(
        (pd.read_parquet(path) for path in paths),
        expected_symbols=expected_symbols,
    )
    target = root / "latest" / "focus_summary.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(target, index=False)
    typer.echo(f"wrote {len(summary)} rows to {target}")
