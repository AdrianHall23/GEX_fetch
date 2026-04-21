"""
GEX Fetch — SPX / SPY / QQQ Gamma Exposure Calculator
======================================================
Uses yfinance (free) to pull options chain, computes GEX per strike,
and outputs key levels + saves levels.json for the dashboard.

Run each morning before 9:30 AM ET:
    python gex_fetch.py
    python gex_fetch.py SPY
    python gex_fetch.py SPY 2026-04-25

Requirements:
    pip install yfinance numpy scipy
"""

import json
import math
import os
import shutil
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import yfinance as yf
from scipy.stats import norm

# ── Config ────────────────────────────────────────────────────────────────────
TICKER      = "SPY"
EXPIRY      = None       # None = auto nearest weekly Friday
# ──────────────────────────────────────────────────────────────────────────────


def next_friday(from_date=None):
    d = from_date or datetime.now(ZoneInfo("America/New_York")).date()
    days_ahead = (4 - d.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return d + timedelta(days=days_ahead)


def black_scholes_gamma(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return norm.pdf(d1) / (S * sigma * math.sqrt(T))


def black_scholes_delta(S, K, T, r, sigma, option_type='call'):
    """Black-Scholes delta. Call delta = N(d1), Put delta = N(d1) - 1"""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    if option_type == 'call':
        return norm.cdf(d1)
    else:
        return norm.cdf(d1) - 1


def compute_max_pain(calls_df, puts_df, strikes_list):
    """
    Max pain = strike where total dollar loss for ALL option holders is maximised.
    i.e. where option SELLERS profit most → price tends to gravitate here near expiry.
    """
    pain = {}
    for target in strikes_list:
        call_loss = 0.0
        put_loss  = 0.0
        for _, row in calls_df.iterrows():
            K  = float(row["strike"])
            oi = float(row["openInterest"]) if not np.isnan(row.get("openInterest", float("nan"))) else 0
            if K < target:
                call_loss += (target - K) * oi * 100
        for _, row in puts_df.iterrows():
            K  = float(row["strike"])
            oi = float(row["openInterest"]) if not np.isnan(row.get("openInterest", float("nan"))) else 0
            if K > target:
                put_loss += (K - target) * oi * 100
        pain[target] = call_loss + put_loss
    return min(pain, key=pain.get)


def get_atm_iv(calls_df, puts_df, spot):
    """Return average IV of the two nearest ATM options (one call, one put)."""
    ivs = []
    for df in [calls_df, puts_df]:
        nearest = df.iloc[(df["strike"] - spot).abs().argsort()[:1]]
        if not nearest.empty:
            iv = float(nearest["impliedVolatility"].iloc[0])
            if not math.isnan(iv) and iv > 0:
                ivs.append(iv)
    return sum(ivs) / len(ivs) if ivs else None


def compute_expected_move(spot, atm_iv, dte):
    """1-day expected move = spot × ATM_IV × sqrt(1/252)"""
    if not atm_iv or dte is None:
        return None
    daily_move = spot * atm_iv * math.sqrt(1 / 252)
    return round(daily_move, 2)


def compute_gex_for_expiry(tk, expiry, spot, r=0.05):
    """Compute per-strike GEX for a single expiry. Returns list of strike dicts."""
    today = datetime.now(ZoneInfo("America/New_York")).date()
    expiry_dt = datetime.strptime(expiry, "%Y-%m-%d").date()
    dte = (expiry_dt - today).days
    T = max(dte / 365.0, 1 / 365.0)

    try:
        chain = tk.option_chain(expiry)
    except Exception:
        return [], 0

    calls = chain.calls.copy()
    puts  = chain.puts.copy()
    results = {}

    for _, row in calls.iterrows():
        K  = float(row["strike"])
        oi = float(row["openInterest"]) if not np.isnan(row.get("openInterest", float("nan"))) else 0
        iv = float(row["impliedVolatility"]) if not np.isnan(row.get("impliedVolatility", float("nan"))) else 0
        if oi == 0 or iv == 0:
            continue
        gamma = black_scholes_gamma(spot, K, T, r, iv)
        gex   = gamma * oi * 100 * (spot ** 2) * 0.01
        if K not in results:
            results[K] = {"strike": K, "call_gex": 0, "put_gex": 0, "call_oi": 0, "put_oi": 0}
        results[K]["call_gex"] += gex
        results[K]["call_oi"]  += int(oi)

    for _, row in puts.iterrows():
        K  = float(row["strike"])
        oi = float(row["openInterest"]) if not np.isnan(row.get("openInterest", float("nan"))) else 0
        iv = float(row["impliedVolatility"]) if not np.isnan(row.get("impliedVolatility", float("nan"))) else 0
        if oi == 0 or iv == 0:
            continue
        gamma = black_scholes_gamma(spot, K, T, r, iv)
        gex   = -gamma * oi * 100 * (spot ** 2) * 0.01
        if K not in results:
            results[K] = {"strike": K, "call_gex": 0, "put_gex": 0, "call_oi": 0, "put_oi": 0}
        results[K]["put_gex"] += gex
        results[K]["put_oi"]  += int(oi)

    strikes = sorted(results.values(), key=lambda x: x["strike"])
    for s in strikes:
        s["net_gex"] = s["call_gex"] + s["put_gex"]

    net_total = sum(s["net_gex"] for s in strikes)
    return strikes, net_total


def compute_gex(ticker_sym, expiry_date=None):
    output_file = f"levels_{ticker_sym.replace('^','')}.json"
    prev_file   = f"levels_{ticker_sym.replace('^','')}_prev.json"

    print(f"\n{'='*60}")
    print(f"  GEX Fetch  |  {ticker_sym}  |  {datetime.now().strftime('%Y-%m-%d %H:%M ET')}")
    print(f"{'='*60}")

    tk = yf.Ticker(ticker_sym)

    # ── Spot price ────────────────────────────────────────────────────────────
    hist = tk.history(period="1d")
    if hist.empty:
        print("ERROR: Could not fetch price data.")
        sys.exit(1)
    spot = float(hist["Close"].iloc[-1])
    print(f"\n  Spot price : ${spot:,.2f}")

    # ── Pick primary expiration ───────────────────────────────────────────────
    all_expiries = tk.options
    if not all_expiries:
        print("ERROR: No options data available.")
        sys.exit(1)

    today = datetime.now(ZoneInfo("America/New_York")).date()
    target = expiry_date or str(next_friday())
    target_dt = datetime.strptime(target, "%Y-%m-%d").date()

    available = [e for e in all_expiries if abs((datetime.strptime(e, "%Y-%m-%d").date() - target_dt).days) <= 7]
    if not available:
        available = [all_expiries[0]]
    expiry = min(available, key=lambda e: abs((datetime.strptime(e, "%Y-%m-%d").date() - target_dt).days))
    expiry_dt = datetime.strptime(expiry, "%Y-%m-%d").date()
    dte = (expiry_dt - today).days
    print(f"  Expiration : {expiry}  ({dte} DTE)")

    # ── Primary chain ─────────────────────────────────────────────────────────
    chain = tk.option_chain(expiry)
    calls = chain.calls.copy()
    puts  = chain.puts.copy()
    T = max(dte / 365.0, 1 / 365.0)
    r = 0.05
    print(f"  Chain      : {len(calls)} calls, {len(puts)} puts")

    # ── GEX + DEX per strike (primary expiry) ────────────────────────────────
    results = {}
    for _, row in calls.iterrows():
        K  = float(row["strike"])
        oi = float(row["openInterest"]) if not np.isnan(row.get("openInterest", float("nan"))) else 0
        iv = float(row["impliedVolatility"]) if not np.isnan(row.get("impliedVolatility", float("nan"))) else 0
        if oi == 0 or iv == 0:
            continue
        gamma = black_scholes_gamma(spot, K, T, r, iv)
        delta = black_scholes_delta(spot, K, T, r, iv, 'call')
        gex   = gamma * oi * 100 * (spot ** 2) * 0.01
        # DEX: dealers short calls → negative call delta exposure
        dex   = -delta * oi * 100
        if K not in results:
            results[K] = {"strike": K, "call_gex": 0, "put_gex": 0, "call_oi": 0, "put_oi": 0, "call_dex": 0, "put_dex": 0}
        results[K]["call_gex"] += gex
        results[K]["call_oi"]  += int(oi)
        results[K]["call_dex"] += dex

    for _, row in puts.iterrows():
        K  = float(row["strike"])
        oi = float(row["openInterest"]) if not np.isnan(row.get("openInterest", float("nan"))) else 0
        iv = float(row["impliedVolatility"]) if not np.isnan(row.get("impliedVolatility", float("nan"))) else 0
        if oi == 0 or iv == 0:
            continue
        gamma = black_scholes_gamma(spot, K, T, r, iv)
        delta = black_scholes_delta(spot, K, T, r, iv, 'put')
        gex   = -gamma * oi * 100 * (spot ** 2) * 0.01
        # DEX: dealers long puts → positive put delta exposure (they buy puts to hedge)
        dex   = -delta * oi * 100
        if K not in results:
            results[K] = {"strike": K, "call_gex": 0, "put_gex": 0, "call_oi": 0, "put_oi": 0, "call_dex": 0, "put_dex": 0}
        results[K]["put_gex"] += gex
        results[K]["put_oi"]  += int(oi)
        results[K]["put_dex"] += dex

    if not results:
        print("ERROR: No valid strike data.")
        sys.exit(1)

    strikes = sorted(results.values(), key=lambda x: x["strike"])
    for s in strikes:
        s["net_gex"] = s["call_gex"] + s["put_gex"]
        s["net_dex"] = s["call_dex"] + s["put_dex"]

    # ── Key levels ────────────────────────────────────────────────────────────
    call_wall     = max(strikes, key=lambda x: x["call_gex"])
    put_wall      = min(strikes, key=lambda x: x["put_gex"])
    net_gex_total = sum(s["net_gex"] for s in strikes)
    net_dex_total = sum(s["net_dex"] for s in strikes)

    # Gamma flip
    sorted_desc = sorted(strikes, key=lambda x: x["strike"], reverse=True)
    cumulative  = 0
    gamma_flip  = None
    for s in sorted_desc:
        prev = cumulative
        cumulative += s["net_gex"]
        if (prev > 0 and cumulative <= 0) or (prev < 0 and cumulative >= 0):
            gamma_flip = s["strike"]
            break

    # Delta flip — strike where cumulative DEX crosses zero
    cumulative = 0
    delta_flip = None
    for s in sorted_desc:
        prev = cumulative
        cumulative += s["net_dex"]
        if (prev > 0 and cumulative <= 0) or (prev < 0 and cumulative >= 0):
            delta_flip = s["strike"]
            break

    # DEX walls — strike with most positive/negative net DEX
    dex_call_wall = max(strikes, key=lambda x: x["net_dex"])
    dex_put_wall  = min(strikes, key=lambda x: x["net_dex"])

    regime = "LONG GAMMA" if net_gex_total >= 0 else "SHORT GAMMA"

    # ── Max Pain ──────────────────────────────────────────────────────────────
    strike_list = [s["strike"] for s in strikes]
    max_pain = compute_max_pain(calls, puts, strike_list)
    print(f"  Max Pain   : ${max_pain:.2f}")

    # ── ATM IV + Expected Move ────────────────────────────────────────────────
    atm_iv       = get_atm_iv(calls, puts, spot)
    expected_move = compute_expected_move(spot, atm_iv, dte)
    if atm_iv:
        print(f"  ATM IV     : {atm_iv*100:.1f}%")
    if expected_move:
        print(f"  Exp Move   : ±${expected_move:.2f} (1-day)")

    # ── GEX by expiry (next 4 expirations) ───────────────────────────────────
    print(f"\n  Computing GEX by expiry...")
    gex_by_expiry = []
    future_expiries = [e for e in all_expiries if (datetime.strptime(e, "%Y-%m-%d").date() - today).days >= 0][:4]
    total_all_expiry_gex = 0

    for exp in future_expiries:
        exp_strikes, exp_net = compute_gex_for_expiry(tk, exp, spot)
        exp_dt  = datetime.strptime(exp, "%Y-%m-%d").date()
        exp_dte = (exp_dt - today).days
        gex_by_expiry.append({
            "expiry": exp,
            "dte": exp_dte,
            "net_gex": exp_net,
            "abs_gex": abs(exp_net)
        })
        total_all_expiry_gex += abs(exp_net)
        print(f"    {exp} ({exp_dte} DTE): ${exp_net/1e6:.1f}M net GEX")

    # Add concentration % for each expiry
    for e in gex_by_expiry:
        e["concentration_pct"] = round(e["abs_gex"] / total_all_expiry_gex * 100, 1) if total_all_expiry_gex > 0 else 0

    # ── Print summary ─────────────────────────────────────────────────────────
    print(f"\n{'─'*50}")
    print(f"  CALL WALL   : ${call_wall['strike']:>8.2f}  (OI: {call_wall['call_oi']:,})")
    print(f"  PUT WALL    : ${put_wall['strike']:>8.2f}  (OI: {put_wall['put_oi']:,})")
    print(f"  GAMMA FLIP  : {'$'+str(gamma_flip) if gamma_flip else 'Not found'}")
    print(f"  MAX PAIN    : ${max_pain:.2f}")
    print(f"  REGIME      : {regime}")
    print(f"  NET GEX     : ${net_gex_total/1e9:.3f}B")
    print(f"{'─'*50}")
    print(f"  DEX CALL    : ${dex_call_wall['strike']:>8.2f}  (net DEX: {dex_call_wall['net_dex']:,.0f})")
    print(f"  DEX PUT     : ${dex_put_wall['strike']:>8.2f}  (net DEX: {dex_put_wall['net_dex']:,.0f})")
    print(f"  DELTA FLIP  : {'$'+str(delta_flip) if delta_flip else 'Not found'}")
    print(f"  NET DEX     : {net_dex_total:,.0f} contracts")
    if expected_move:
        print(f"  EXP MOVE    : ±${expected_move:.2f}  (ES approx ±{expected_move*10:.0f}pts)")
    print(f"{'─'*50}")

    # ── Save previous levels before overwriting ───────────────────────────────
    if os.path.exists(output_file):
        shutil.copy(output_file, prev_file)
        print(f"\n  Previous levels saved → {prev_file}")

    # ── Save JSON ─────────────────────────────────────────────────────────────
    output = {
        "ticker":           ticker_sym,
        "expiry":           expiry,
        "dte":              dte,
        "spot":             spot,
        "as_of":            datetime.now(ZoneInfo("America/New_York")).isoformat(),
        "call_wall":        call_wall["strike"],
        "put_wall":         put_wall["strike"],
        "gamma_flip":       gamma_flip,
        "max_pain":         max_pain,
        "net_gex":          net_gex_total,
        "net_gex_label":    "positive" if net_gex_total >= 0 else "negative",
        "regime":           regime,
        "dex_call_wall":    dex_call_wall["strike"],
        "dex_put_wall":     dex_put_wall["strike"],
        "delta_flip":       delta_flip,
        "net_dex":          net_dex_total,
        "atm_iv":           atm_iv,
        "expected_move_1d": expected_move,
        "gex_by_expiry":    gex_by_expiry,
        "strikes":          strikes,
    }

    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)

    print(f"  Current levels saved → {output_file}")
    print(f"{'='*60}\n")
    return output


if __name__ == "__main__":
    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else TICKER
    expiry = sys.argv[2] if len(sys.argv) > 2 else EXPIRY
    compute_gex(ticker, expiry)
