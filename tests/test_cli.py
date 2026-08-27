from pathlib import Path

from typer.testing import CliRunner

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
