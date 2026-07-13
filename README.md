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
