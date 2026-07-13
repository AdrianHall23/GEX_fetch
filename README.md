# GEX Fetch — SPX / SPY / QQQ Gamma Exposure Calculator

A Python tool that calculates **Gamma Exposure (GEX)** and **Delta Exposure (DEX)** for options chains using real-time market data from [yfinance](https://github.com/ranaroussi/yfinance).

## Overview

GEX Fetch pulls options chain data for major indices (SPX, SPY, QQQ) and computes:

- **Gamma Exposure (GEX)** per strike — measures how much underlying price volatility dealers face as options approach expiration
- **Delta Exposure (DEX)** per strike — tracks dealer positioning and hedging pressure
- **Key Levels** — call/put walls, gamma flip, delta flip, max pain
- **Regime Analysis** — long gamma vs. short gamma environments
- **Expected Move** — 1-day price move derived from ATM implied volatility

Results are exported to a JSON file (`levels_{TICKER}.json`) for dashboard consumption or further analysis.

## Installation

### Prerequisites

- Python 3.8+
- pip

### Setup

```bash
git clone https://github.com/AdrianHall23/GEX_fetch.git
cd GEX_fetch
pip install -r requirements.txt
```

### Dependencies

- **yfinance** — Fetches real-time options chain and price data
- **numpy** — Numerical computations
- **scipy** — Statistical functions (normal distribution for Black-Scholes)

## Usage

Run the script from command line with optional ticker and expiry arguments:

### Default (SPY, nearest Friday weekly)
```bash
python gex_fetch.py
```

### Custom Ticker
```bash
python gex_fetch.py SPY
python gex_fetch.py QQQ
python gex_fetch.py SPX
```

### Custom Ticker + Expiry Date
```bash
python gex_fetch.py SPY 2026-04-25
```

The script will output a summary to console and save detailed results to `levels_{TICKER}.json`.

## Output

### Console Output

```
════════════════════════════════════════════════════════════════
  GEX Fetch  |  SPY  |  2026-07-13 09:15 ET
════════════════════════════════════════════════════════════════

  Spot price : $445,250.00
  Expiration : 2026-07-17  (4 DTE)
  Chain      : 186 calls, 186 puts

──────────────────────────────────────────────────────────────
  CALL WALL   :  $450.00  (OI: 125,432)
  PUT WALL    :  $440.00  (OI: 98,765)
  GAMMA FLIP  : $445.50
  MAX PAIN    : $444.99
  REGIME      : LONG GAMMA
  NET GEX     : $2.543B
──────────────────────────────────────────────────────────────
  DEX CALL    :  $450.00  (net DEX: -45,600)
  DEX PUT     :  $440.00  (net DEX: 32,100)
  DELTA FLIP  : $442.75
  NET DEX     : 15,200 contracts
  EXP MOVE    : ±$3.25  (ES approx ±32pts)
────────────────────────────────────────────────────────────────
```

### JSON Output (`levels_{TICKER}.json`)

```json
{
  "ticker": "SPY",
  "expiry": "2026-07-17",
  "dte": 4,
  "spot": 445250.00,
  "as_of": "2026-07-13T09:15:00-04:00",
  "call_wall": 450.00,
  "put_wall": 440.00,
  "gamma_flip": 445.50,
  "max_pain": 444.99,
  "net_gex": 2543000000,
  "net_gex_label": "positive",
  "regime": "LONG GAMMA",
  "dex_call_wall": 450.00,
  "dex_put_wall": 440.00,
  "delta_flip": 442.75,
  "net_dex": 15200,
  "atm_iv": 0.18,
  "expected_move_1d": 3.25,
  "gex_by_expiry": [...],
  "strikes": [...]
}
```

## Key Concepts

### Gamma Exposure (GEX)
The aggregate gamma position across all options. In positive GEX environments, dealers are short gamma and must buy on dips and sell on rallies, providing market support. In negative GEX, dealers profit from larger moves.

**Formula:**
```
GEX = Σ (Gamma × Open Interest × Spot² × 0.01) per strike
```

### Delta Exposure (DEX)
Cumulative delta position of all options. Used to identify dealer hedging pressure and potential inflection points.

### Call/Put Walls
Strikes with the highest call and put open interest—areas where dealers face the most gamma pressure.

### Gamma Flip
The strike where cumulative GEX crosses zero, marking a transition between long and short gamma regimes.

### Max Pain
The strike at which total losses for option holders (across all expiries) are maximized—where the market tends to gravitate near expiration.

### Expected Move
Estimated 1-day price move derived from ATM implied volatility:
```
1-day move = Spot × ATM_IV × √(1/252)
```

## Black-Scholes Implementation

This tool uses the Black-Scholes model to compute:

- **Gamma:** Rate of change of delta; peaks near-the-money
- **Delta:** Expected change in option price per $1 move in underlying

Functions:
- `black_scholes_gamma(S, K, T, r, sigma)` — Gamma per strike
- `black_scholes_delta(S, K, T, r, sigma, option_type)` — Call/put delta

## Previous Levels

Each run backs up the previous `levels_{TICKER}.json` to `levels_{TICKER}_prev.json` for comparison and historical tracking.

## Scheduling (Optional)

Run before 9:30 AM ET each trading day for fresh daily levels:

### macOS / Linux (Cron)
```bash
30 9 * * 1-5 cd ~/path/to/GEX_fetch && /usr/bin/python3 gex_fetch.py
```

### Windows (Task Scheduler)
Create a batch file:
```batch
@echo off
cd C:\path\to\GEX_fetch
python gex_fetch.py
```
Then schedule via Task Scheduler to run at 9:30 AM.

## Notes

- Data is sourced from **yfinance** (Yahoo Finance); availability varies by ticker and market conditions
- Options data may lag 15–20 minutes during market hours
- GEX calculations assume constant IV; real markets are dynamic
- For production use, consider adding error handling and notifications for data fetch failures

## License

This project is open-source. See LICENSE file for details.

## Disclaimer

This tool is for educational and informational purposes only. It is not financial advice. Options trading involves substantial risk of loss. Always consult a financial advisor before making trading decisions.
