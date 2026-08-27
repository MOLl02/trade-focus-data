import numpy as np
import pandas as pd


ANNUALIZATION = {"1h": 252 * 6.5, "1d": 252, "1w": 52}


def _rsi(close: pd.Series, length: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    average_gain = gain.ewm(
        alpha=1 / length, min_periods=length, adjust=False
    ).mean()
    average_loss = loss.ewm(
        alpha=1 / length, min_periods=length, adjust=False
    ).mean()
    relative_strength = average_gain / average_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + relative_strength))
    return result.mask((average_loss == 0) & (average_gain > 0), 100.0)


def _one_group(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.sort_values("timestamp_utc").copy()
    close = result["close"].astype(float)
    high = result["high"].astype(float)
    low = result["low"].astype(float)
    volume = result["volume"].astype(float)

    result["rsi_14"] = _rsi(close, 14)
    ema_12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema_26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    result["ema_12"] = ema_12
    result["ema_26"] = ema_26
    result["ema_50"] = close.ewm(
        span=50, adjust=False, min_periods=50
    ).mean()
    result["macd"] = ema_12 - ema_26
    result["macd_signal"] = result["macd"].ewm(
        span=9, adjust=False, min_periods=9
    ).mean()
    result["macd_histogram"] = result["macd"] - result["macd_signal"]

    for length in (20, 50, 200):
        result[f"sma_{length}"] = close.rolling(
            length, min_periods=length
        ).mean()
        result[f"distance_sma_{length}"] = (
            close / result[f"sma_{length}"] - 1
        )

    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    result["atr_14"] = true_range.ewm(
        alpha=1 / 14, adjust=False, min_periods=14
    ).mean()

    rolling_low = low.rolling(14, min_periods=14).min()
    rolling_high = high.rolling(14, min_periods=14).max()
    result["stoch_k_14"] = 100 * (close - rolling_low) / (
        rolling_high - rolling_low
    ).replace(0, np.nan)
    result["stoch_d_3"] = result["stoch_k_14"].rolling(
        3, min_periods=3
    ).mean()

    for length in (5, 20, 50):
        result[f"volume_avg_{length}"] = volume.rolling(
            length, min_periods=length
        ).mean()
    result["relative_volume_20"] = volume / result["volume_avg_20"]

    for length in (1, 5, 20):
        result[f"return_{length}"] = close.pct_change(
            length, fill_method=None
        )

    log_return = np.log(close / close.shift(1))
    factor = ANNUALIZATION[str(result["timeframe"].iloc[0])]
    result["realized_volatility_20"] = (
        log_return.rolling(20, min_periods=20).std(ddof=1) * np.sqrt(factor)
    )
    result["running_peak"] = close.cummax()
    result["drawdown"] = close / result["running_peak"] - 1

    timeframe = str(result["timeframe"].iloc[0])
    range_length = 252 if timeframe == "1d" else 52 if timeframe == "1w" else None
    if range_length is None:
        result["high_52w"] = np.nan
        result["low_52w"] = np.nan
        result["range_52w_position"] = np.nan
    else:
        result["high_52w"] = high.rolling(
            range_length, min_periods=range_length
        ).max()
        result["low_52w"] = low.rolling(
            range_length, min_periods=range_length
        ).min()
        width = result["high_52w"] - result["low_52w"]
        result["range_52w_position"] = (
            close - result["low_52w"]
        ) / width.replace(0, np.nan)
    return result


def add_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    return pd.concat(
        [
            _one_group(group)
            for _, group in frame.groupby(
                ["symbol", "timeframe"], sort=True
            )
        ],
        ignore_index=True,
    )
