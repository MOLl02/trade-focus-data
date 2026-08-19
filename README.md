# trade-focus-data

Personal market-focus dataset and trading-research configuration.

## Current snapshot

This package captures the connected Robinhood focus lists on **2026-08-19** and the multi-timeframe trading research framework discussed in the prior Trade conversation.

Files:

- `data/robinhood_watchlists_2026-08-19.json` — structured watchlist snapshot.
- `data/focus_symbols_2026-08-19.csv` — flat symbol/watchlist mapping.
- `config/trading_system.json` — machine-readable strategy/scanner rules.

The focus snapshot contains **48 list entries / 48 unique symbols** across five non-empty custom watchlists.

## Research goals

The scanner is intended to examine both the focused universe and the broader liquid US market for:

- consecutive declines, capitulation, low-base and repair rebounds;
- oversold/overbought reversal setups;
- sideways accumulation and volatility compression;
- volume-confirmed breakouts and breakout retests;
- failed breakouts, divergence, weak-volume rallies, blow-off/distribution shorts;
- high-volume + high-change names that are outside the focus list;
- multi-timeframe support/resistance from daily and weekly history.

The defaults in `trading_system.json` are **research heuristics, not validated edge estimates**. They should be backtested and iterated.

## Privacy

This public-repo package intentionally excludes brokerage account numbers, balances, current positions, orders, tax lots, and other private account data.
