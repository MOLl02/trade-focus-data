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
    path.write_text(
        "symbols:\n  - symbol: AMD\n    asset_type: stock\n  - symbol: AMD\n    asset_type: stock\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate symbol: AMD"):
        load_universe(path)

