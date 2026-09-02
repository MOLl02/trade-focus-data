from __future__ import annotations

import math


def classic_pivots(high: float, low: float, close: float) -> dict[str, float]:
    """Return classic floor-trader pivot levels for one completed bar."""
    values = (float(high), float(low), float(close))
    high_value, low_value, close_value = values
    if (
        not all(math.isfinite(value) for value in values)
        or high_value < low_value
        or not low_value <= close_value <= high_value
    ):
        raise ValueError("invalid pivot reference high, low, or close")

    pivot = (high_value + low_value + close_value) / 3.0
    spread = high_value - low_value
    return {
        "pivot": pivot,
        "s1": 2.0 * pivot - high_value,
        "s2": pivot - spread,
        "s3": low_value - 2.0 * (high_value - pivot),
        "r1": 2.0 * pivot - low_value,
        "r2": pivot + spread,
        "r3": high_value + 2.0 * (pivot - low_value),
    }
