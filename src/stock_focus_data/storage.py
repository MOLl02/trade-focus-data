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

    def _directory(
        self, symbol: str, timeframe: Timeframe, year: int
    ) -> Path:
        return (
            self.root
            / "normalized"
            / f"timeframe={timeframe.value}"
            / f"symbol={symbol}"
            / f"year={year}"
        )

    def _partition(
        self, symbol: str, timeframe: Timeframe, year: int
    ) -> Path:
        return self._directory(symbol, timeframe, year) / "bars.parquet"

    def merge(self, frame: pd.DataFrame) -> None:
        incoming = validate_candles(frame)
        if incoming.empty:
            return
        incoming["year"] = incoming["timestamp_utc"].dt.year
        for (symbol, timeframe_value, year), group in incoming.groupby(
            ["symbol", "timeframe", "year"], sort=True
        ):
            timeframe = Timeframe(str(timeframe_value))
            target = self._partition(str(symbol), timeframe, int(year))
            existing = (
                pd.read_parquet(target) if target.exists() else empty_candle_frame()
            )
            combined = pd.concat(
                [existing, group.drop(columns="year")], ignore_index=True
            )
            combined["_source_priority"] = (
                combined["data_source"].map(SOURCE_PRIORITY).fillna(0)
            )
            combined = combined.sort_values(
                ["timestamp_utc", "_source_priority", "retrieved_at_utc"]
            )
            combined = combined.drop_duplicates(
                ["symbol", "timeframe", "timestamp_utc"], keep="last"
            ).drop(columns="_source_priority")
            validated = validate_candles(combined)
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                dir=target.parent, suffix=".parquet", delete=False
            ) as handle:
                temporary = Path(handle.name)
            try:
                validated.to_parquet(temporary, index=False)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)

    def read(self, symbol: str, timeframe: Timeframe) -> pd.DataFrame:
        paths = sorted(
            (
                self.root
                / "normalized"
                / f"timeframe={timeframe.value}"
                / f"symbol={symbol}"
            ).glob("year=*/bars.parquet")
        )
        if not paths:
            return empty_candle_frame()
        return validate_candles(
            pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)
        )


def write_manifest(root: Path, manifest: dict[str, object]) -> Path:
    directory = root / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = directory / f"run-{stamp}.json"
    sequence = 1
    while target.exists():
        target = directory / f"run-{stamp}-{sequence:02d}.json"
        sequence += 1
    target.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return target
