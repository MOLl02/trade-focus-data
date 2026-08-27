# Stock Focus Data

Local Robinhood-first OHLCV storage and technical analysis for 32 approved focus symbols. QQQ and SOXX are the only ETFs. This project stores research data and cannot place trades.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Fill `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` in `.env` only when Alpaca fallback is needed. Never put Robinhood credentials or account numbers in this repository.

## Local checks

```powershell
stock-focus validate-config
stock-focus sample
python -m pytest -q
```

## Robinhood import

Robinhood is connected through Codex. Save the connector's unchanged structured payload under `data/inbox/robinhood/`, then import it explicitly:

```powershell
stock-focus import-robinhood --input data/inbox/robinhood/day-2026-08-26.json --timeframe 1d
stock-focus import-robinhood --input data/inbox/robinhood/hour-2026-08-26.json --timeframe 1h
stock-focus rebuild
stock-focus summarize
```

To apply Robinhood-first selection and Alpaca fallback across the configured universe, use `refresh` with one or more connector payloads:

```powershell
stock-focus refresh --robinhood-input data/inbox/robinhood/day-2026-08-26.json --timeframe 1d --start 2021-08-26T00:00:00Z --end 2026-08-27T00:00:00Z
```

Raw imports, generated data, logs, and `.env` are ignored by Git. The canonical normalized history is partitioned Parquet under `data/normalized/`; calculated histories are under `data/derived/`; `data/latest/focus_summary.csv` is the compact current view.

## Data defaults

- Hourly backfill: 365 calendar days
- Daily backfill: five calendar years
- Weekly bars: derived from validated daily bars
- Regular market session, split-adjusted prices
- Robinhood wins duplicate timestamps; Alpaca fills unavailable symbol/range data

## Indicators

RSI(14), MACD(12,26,9), SMA(20/50/200), EMA(12/26/50), ATR(14), stochastic %K/%D, relative and rolling volume, 1/5/20-bar returns, 20-bar realized volatility, running drawdown, moving-average distance, and 52-week range position.

## Limitations

The standalone code cannot authenticate to Robinhood. Robinhood payloads enter through the connected Codex import boundary. Live Alpaca fallback requires user-supplied API credentials. Phase one has no scheduler and does not publish to GitHub.
