from collections.abc import Iterable

import pandas as pd


SUMMARY_COLUMNS = [
    "symbol",
    "timeframe",
    "timestamp_utc",
    "close",
    "volume",
    "volume_avg_20",
    "relative_volume_20",
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_histogram",
    "macd_state",
    "stoch_k_14",
    "stoch_d_3",
    "atr_14",
    "sma_20",
    "sma_50",
    "sma_200",
    "ema_12",
    "ema_26",
    "ema_50",
    "distance_sma_20",
    "distance_sma_50",
    "distance_sma_200",
    "trend_state",
    "return_1",
    "return_5",
    "return_20",
    "realized_volatility_20",
    "drawdown",
    "high_52w",
    "low_52w",
    "range_52w_position",
    "data_source",
    "validation_status",
    "retrieved_at_utc",
]


def _trend(row: pd.Series) -> str:
    values = [row.get("sma_20"), row.get("sma_50"), row.get("sma_200")]
    if all(
        pd.notna(value) and row["close"] > value
        for value in values
    ):
        return "above_sma_20_50_200"
    if all(
        pd.notna(value) and row["close"] < value
        for value in values
    ):
        return "below_sma_20_50_200"
    return "mixed_or_insufficient_history"


def _missing_rows(expected_symbols: Iterable[str]) -> pd.DataFrame:
    missing = pd.DataFrame(
        [
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "validation_status": "missing",
            }
            for symbol in expected_symbols
            for timeframe in ("1h", "1d", "1w")
        ]
    )
    for column in SUMMARY_COLUMNS:
        if column not in missing.columns:
            missing[column] = pd.NA
    return (
        missing[SUMMARY_COLUMNS]
        if not missing.empty
        else pd.DataFrame(columns=SUMMARY_COLUMNS)
    )


def build_latest_summary(
    frames: Iterable[pd.DataFrame],
    expected_symbols: Iterable[str] = (),
) -> pd.DataFrame:
    expected_symbols = tuple(expected_symbols)
    nonempty = [frame.copy() for frame in frames if not frame.empty]
    if not nonempty:
        return _missing_rows(expected_symbols).sort_values(
            ["symbol", "timeframe"]
        ).reset_index(drop=True)
    combined = pd.concat(nonempty, ignore_index=True)
    if "is_complete" in combined.columns:
        combined = combined.loc[combined["is_complete"].fillna(True)]
    latest = (
        combined.sort_values("timestamp_utc")
        .groupby(["symbol", "timeframe"], as_index=False)
        .tail(1)
        .copy()
    )
    latest["trend_state"] = latest.apply(_trend, axis=1)
    latest["macd_state"] = latest.apply(
        lambda row: (
            "bullish"
            if pd.notna(row.get("macd"))
            and pd.notna(row.get("macd_signal"))
            and row["macd"] > row["macd_signal"]
            else "bearish"
            if pd.notna(row.get("macd"))
            and pd.notna(row.get("macd_signal"))
            else "insufficient_history"
        ),
        axis=1,
    )
    for column in SUMMARY_COLUMNS:
        if column not in latest.columns:
            latest[column] = pd.NA
    result = latest[SUMMARY_COLUMNS]
    expected = {
        (symbol, timeframe)
        for symbol in expected_symbols
        for timeframe in ("1h", "1d", "1w")
    }
    present = set(zip(result["symbol"], result["timeframe"], strict=False))
    missing_pairs = sorted(expected - present)
    if missing_pairs:
        missing = pd.DataFrame(
            [
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "validation_status": "missing",
                }
                for symbol, timeframe in missing_pairs
            ]
        )
        for column in SUMMARY_COLUMNS:
            if column not in missing.columns:
                missing[column] = pd.NA
        result = pd.concat(
            [result, missing[SUMMARY_COLUMNS]], ignore_index=True
        )
    return result.sort_values(["symbol", "timeframe"]).reset_index(drop=True)

