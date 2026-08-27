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
        UniverseEntry(
            symbol=str(row["symbol"]).strip().upper(),
            asset_type=str(row["asset_type"]).strip().lower(),
        )
        for row in rows
    )
    seen: set[str] = set()
    for entry in entries:
        if entry.symbol in seen:
            raise ValueError(f"duplicate symbol: {entry.symbol}")
        if entry.asset_type not in {"stock", "etf"}:
            raise ValueError(f"invalid asset type for {entry.symbol}: {entry.asset_type}")
        seen.add(entry.symbol)
    if tuple(entry.symbol for entry in entries) != tuple(
        sorted(entry.symbol for entry in entries)
    ):
        raise ValueError("universe symbols must be sorted")
    return entries

