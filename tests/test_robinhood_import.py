from datetime import UTC, datetime
from pathlib import Path

from stock_focus_data.models import Timeframe
from stock_focus_data.sources.robinhood_import import RobinhoodImportSource


def test_parses_connector_payload_and_provenance() -> None:
    frame = RobinhoodImportSource.load(
        Path("tests/fixtures/robinhood_day.json"),
        Timeframe.DAY,
        datetime(2026, 8, 26, 22, 0, tzinfo=UTC),
    )
    assert len(frame) == 3
    assert frame.iloc[-1]["close"] == 186.0
    assert frame.iloc[-1]["volume"] == 41_000_000
    assert set(frame["data_source"]) == {"robinhood"}
    assert str(frame["timestamp_utc"].dtype) == "datetime64[ns, UTC]"

