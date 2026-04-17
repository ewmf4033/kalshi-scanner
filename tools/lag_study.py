#!/usr/bin/env python3
"""
lag_study.py — One-off analysis of Kalshi settlement lag.

Pulls close_time, settlement_ts, settlement_timer_seconds for every ticker
in raw/resolved/*.json and raw/resolved.bak.*/*.json. Computes excess lag
(actual lag minus mandated timer) by category. Writes summary + per-ticker
detail to raw/lag_study/.
"""

import json, time, sys, statistics
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resolve import load_private_key, kalshi_get

BASE = Path(__file__).resolve().parent.parent
RAW_RESOLVED = BASE / "raw" / "resolved"
RAW_BAK_GLOB = "resolved.bak.*"
OUT_DIR = BASE / "raw" / "lag_study"
OUT_DIR.mkdir(exist_ok=True)

def collect_tickers():
    tickers = set()
    for f in RAW_RESOLVED.glob("*.json"):
        data = json.loads(f.read_text())
        for r in data.get("resolutions", []):
            tickers.add(r["ticker"])
    for bak_dir in (BASE / "raw").glob(RAW_BAK_GLOB):
        for f in bak_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                for r in data.get("resolutions", []):
                    tickers.add(r["ticker"])
            except Exception as e:
                print(f"skip {f}: {e}")
    return sorted(tickers)

def infer_category(ticker):
    # Kalshi ticker prefixes - add to this map as needed
    prefix = ticker.split("-")[0]
    mapping = {
        "KXGOLDD": "commodities",
        "KXOILD": "commodities",
        "KXCPI": "macro",
        "KXFEDDECISION": "macro",
        "KXNFP": "macro",
        "KXPPI": "macro",
        "KXUNRATE": "macro",
        "KXNBAGAME": "sports",
        "KXMLBGAME": "sports",
        "KXNFLGAME": "sports",
        "KXNHLGAME": "sports",
        "KXHIGH": "weather",
        "KXLOW": "weather",
    }
    return mapping.get(prefix, f"other:{prefix}")

def parse_ts(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def main():
    pk = load_private_key()
    tickers = collect_tickers()
    print(f"Collected {len(tickers)} unique tickers")

    rows = []
    for i, t in enumerate(tickers):
        try:
            m = kalshi_get(f"/markets/{t}", pk=pk)
            market = m.get("market", m)
            close_time = parse_ts(market.get("close_time"))
            settlement_ts = parse_ts(market.get("settlement_ts"))
            timer_sec = market.get("settlement_timer_seconds")
            status = market.get("status")
            if close_time and settlement_ts:
                total_lag_sec = (settlement_ts - close_time).total_seconds()
                excess_lag_sec = total_lag_sec - (timer_sec or 0)
            else:
                total_lag_sec = None
                excess_lag_sec = None
            rows.append({
                "ticker": t,
                "category": infer_category(t),
                "close_time": market.get("close_time"),
                "settlement_ts": market.get("settlement_ts"),
                "timer_sec": timer_sec,
                "total_lag_sec": total_lag_sec,
                "excess_lag_sec": excess_lag_sec,
                "status": status,
            })
            print(f"[{i+1}/{len(tickers)}] {t} excess={excess_lag_sec}s status={status}")
        except Exception as e:
            print(f"[{i+1}/{len(tickers)}] {t} ERROR {e}")
            rows.append({"ticker": t, "error": str(e)})
        time.sleep(0.2)

    # write detail
    (OUT_DIR / "ticker_lag.json").write_text(json.dumps(rows, indent=2))

    # summary by category
    by_cat = defaultdict(list)
    for r in rows:
        if r.get("excess_lag_sec") is not None:
            by_cat[r["category"]].append(r["excess_lag_sec"])

    summary = {}
    print("\n=== SUMMARY (excess lag in seconds, beyond mandated timer) ===")
    print(f"{'category':<20} {'n':>4} {'median':>10} {'p90':>10} {'p99':>10} {'max':>10}")
    for cat in sorted(by_cat):
        vals = sorted(by_cat[cat])
        n = len(vals)
        median = statistics.median(vals)
        p90 = vals[int(n * 0.9)] if n > 1 else vals[0]
        p99 = vals[int(n * 0.99)] if n > 1 else vals[0]
        mx = max(vals)
        summary[cat] = {"n": n, "median_sec": median, "p90_sec": p90, "p99_sec": p99, "max_sec": mx}
        print(f"{cat:<20} {n:>4} {median:>10.1f} {p90:>10.1f} {p99:>10.1f} {mx:>10.1f}")

    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {OUT_DIR}/ticker_lag.json and summary.json")

if __name__ == "__main__":
    main()
