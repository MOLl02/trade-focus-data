from stock_focus_data.models import CANDLE_COLUMNS, Timeframe, empty_candle_frame


def test_empty_frame_uses_canonical_columns() -> None:
    frame = empty_candle_frame()
    assert list(frame.columns) == list(CANDLE_COLUMNS)
    assert frame.empty
    assert {item.value for item in Timeframe} == {"1h", "1d", "1w"}
