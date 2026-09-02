import numpy as np
import pytest

from stock_focus_data.support_resistance import classic_pivots


def test_classic_pivots_match_known_values() -> None:
    result = classic_pivots(high=110.0, low=90.0, close=100.0)

    assert result == {
        "pivot": 100.0,
        "s1": 90.0,
        "s2": 80.0,
        "s3": 70.0,
        "r1": 110.0,
        "r2": 120.0,
        "r3": 130.0,
    }


@pytest.mark.parametrize(
    ("high", "low", "close"),
    [
        (90.0, 110.0, 100.0),
        (110.0, 90.0, 120.0),
        (110.0, 90.0, 80.0),
        (np.nan, 90.0, 100.0),
        (110.0, np.inf, 100.0),
    ],
)
def test_classic_pivots_reject_invalid_reference_prices(
    high: float,
    low: float,
    close: float,
) -> None:
    with pytest.raises(ValueError, match="invalid pivot reference"):
        classic_pivots(high=high, low=low, close=close)
