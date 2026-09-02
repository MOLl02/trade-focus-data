from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

import stock_focus_data.cli as cli_module
from stock_focus_data.cli import app


def test_validate_config_command() -> None:
    result = CliRunner().invoke(
        app, ["validate-config", "--config", "config/universe.yaml"]
    )
    assert result.exit_code == 0
    assert "32 symbols; 30 stocks; 2 ETFs" in result.stdout


def test_refresh_uses_complete_robinhood_import_without_credentials(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = tmp_path / "universe.yaml"
    config.write_text(
        "symbols:\n  - symbol: AMD\n    asset_type: stock\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)
    result = CliRunner().invoke(
        app,
        [
            "refresh",
            "--robinhood-input",
            "tests/fixtures/robinhood_day.json",
            "--timeframe",
            "1d",
            "--start",
            "2026-08-24T00:00:00Z",
            "--end",
            "2026-08-27T00:00:00Z",
            "--root",
            str(tmp_path / "data"),
            "--config",
            str(config),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "refreshed=1 failed=0" in result.stdout


def test_import_alpaca_command_merges_connected_payload(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    result = CliRunner().invoke(
        app,
        [
            "import-alpaca",
            "--input",
            "tests/fixtures/alpaca_day.json",
            "--timeframe",
            "1d",
            "--root",
            str(root),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "imported 1 rows" in result.stdout
    partition = root / "normalized" / "timeframe=1d" / "symbol=CBRS"
    assert list(partition.rglob("*.parquet"))


def test_sample_command_builds_local_daily_and_weekly_data(
    tmp_path: Path,
) -> None:
    result = CliRunner().invoke(
        app, ["sample", "--root", str(tmp_path / "sample-data")]
    )
    assert result.exit_code == 0, result.stdout
    assert "sample complete: daily=3 weekly=1" in result.stdout
    assert (tmp_path / "sample-data" / "derived" / "AMD-1d.parquet").exists()
    assert (tmp_path / "sample-data" / "derived" / "AMD-1w.parquet").exists()


def derived_frame(
    symbol: str,
    timeframe: str,
    complete: bool = True,
) -> pd.DataFrame:
    dates = (
        pd.date_range("2026-08-01", periods=20, freq="B", tz="UTC")
        if timeframe == "1d"
        else pd.date_range("2026-08-01", periods=20, freq="h", tz="UTC")
        if timeframe == "1h"
        else pd.date_range(
            "2026-04-17", periods=20, freq="W-FRI", tz="UTC"
        )
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
            derived / f"AMD-{timeframe}.parquet",
            index=False,
        )


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


def test_support_resistance_failure_preserves_existing_outputs(
    tmp_path: Path,
) -> None:
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


def test_summarize_ignores_support_resistance_parquet(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "data"
    config = tmp_path / "universe.yaml"
    write_cli_fixture(root, config)
    pd.DataFrame(
        [{"symbol": "AMD", "method": "classic", "level_value": 100.0}]
    ).to_parquet(
        root / "derived" / "support_resistance_levels.parquet",
        index=False,
    )
    actual_read_parquet = pd.read_parquet
    read_names: list[str] = []

    def tracked_read_parquet(path, *args, **kwargs):
        read_names.append(Path(path).name)
        return actual_read_parquet(path, *args, **kwargs)

    monkeypatch.setattr(cli_module.pd, "read_parquet", tracked_read_parquet)

    result = CliRunner().invoke(
        app,
        ["summarize", "--root", str(root), "--config", str(config)],
    )

    assert result.exit_code == 0, result.stdout
    assert "wrote 3 rows" in result.stdout
    assert "support_resistance_levels.parquet" not in read_names
