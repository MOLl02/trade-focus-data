from datetime import UTC, datetime
from pathlib import Path

from stock_focus_data.aggregation import aggregate_weekly
from stock_focus_data.indicators import add_indicators
from stock_focus_data.models import Timeframe
from stock_focus_data.sources.robinhood_import import RobinhoodImportSource
from stock_focus_data.storage import CandleStore
from stock_focus_data.summaries import build_latest_summary


def test_fixture_pipeline_is_idempotent(tmp_path: Path) -> None:
    imported = RobinhoodImportSource.load(
        Path("tests/fixtures/robinhood_day.json"),
        Timeframe.DAY,
        datetime(2026, 8, 26, 22, tzinfo=UTC),
    )
    store = CandleStore(tmp_path)
    store.merge(imported)
    store.merge(imported)
    daily = store.read("AMD", Timeframe.DAY)
    assert len(daily) == 3
    weekly = aggregate_weekly(
        daily, datetime(2026, 9, 1, 22, tzinfo=UTC)
    )
    summary = build_latest_summary(
        [add_indicators(daily), add_indicators(weekly)]
    )
    assert set(summary["timeframe"]) == {"1d", "1w"}
    assert set(summary["data_source"]) == {"robinhood", "derived"}

