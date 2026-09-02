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
            if timeframe is Timeframe.DAY:
                sort_columns = [
                    "session_date",
                    "_source_priority",
                    "retrieved_at_utc",
                    "timestamp_utc",
                ]
                duplicate_columns = ["symbol", "timeframe", "session_date"]
            else:
                sort_columns = [
                    "timestamp_utc",
                    "_source_priority",
                    "retrieved_at_utc",
                ]
                duplicate_columns = ["symbol", "timeframe", "timestamp_utc"]
            combined = combined.sort_values(sort_columns)
            combined = combined.drop_duplicates(
                duplicate_columns, keep="last"
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

    def trim(
        self,
        timeframe: Timeframe,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> int:
        start_utc = pd.Timestamp(start)
        end_utc = pd.Timestamp(end)
        if start_utc.tzinfo is None:
            start_utc = start_utc.tz_localize("UTC")
        else:
            start_utc = start_utc.tz_convert("UTC")
        if end_utc.tzinfo is None:
            end_utc = end_utc.tz_localize("UTC")
        else:
            end_utc = end_utc.tz_convert("UTC")
        removed = 0
        paths = sorted(
            (
                self.root
                / "normalized"
                / f"timeframe={timeframe.value}"
            ).glob("symbol=*/year=*/bars.parquet")
        )
        for target in paths:
            frame = validate_candles(pd.read_parquet(target))
            keep = frame["timestamp_utc"].between(start_utc, end_utc)
            if timeframe is Timeframe.HOUR:
                market_hours = frame["timestamp_utc"].dt.tz_convert(
                    "America/New_York"
                ).dt.hour
                keep &= market_hours.between(9, 15)
            removed += int((~keep).sum())
            remaining = frame.loc[keep].copy()
            if remaining.empty:
                target.unlink()
                continue
            with tempfile.NamedTemporaryFile(
                dir=target.parent, suffix=".parquet", delete=False
            ) as handle:
                temporary = Path(handle.name)
            try:
                validate_candles(remaining).to_parquet(temporary, index=False)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        return removed


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
