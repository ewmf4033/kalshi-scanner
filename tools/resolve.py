#!/usr/bin/env python3
"""
resolve.py — Settlement scoring for Kalshi Scanner

Pulls settled markets from Kalshi API, matches against scanner predictions,
computes Brier score, log loss, and theoretical P&L. Updates raw/resolved/.

Usage:
    python3 tools/resolve.py              # resolve all pending
    python3 tools/resolve.py --dry-run    # print without saving
"""

import json, os, sys, time, math, base64, logging
from pathlib import Path
from datetime import datetime, timezone

log = logging.getLogger("resolve")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

# --- Paths ---
BASE = Path(__file__).resolve().parent.parent
RAW_SCANS = BASE / "raw" / "scans"
RAW_CONSENSUS = BASE / "raw" / "consensus"
RAW_RESOLVED = BASE / "raw" / "resolved"
RAW_SNAPSHOTS = BASE / "raw" / "snapshots"
RAW_RESOLVED.mkdir(exist_ok=True)

FULL_COVERAGE_TRACK_B_MODELS = {
    "gpt56_track_b",
    "fable5_track_b",
    "grok_track_b",
}

FULL_COVERAGE_EXCLUDED_DATES = {
    "2026-04-10",  # Historical technical dry run with hindsight risk.
}

# --- Kalshi API auth (same as scanner.py) ---
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from dotenv import load_dotenv
import httpx

load_dotenv(BASE / ".env")

API_KEY_ID = os.getenv("KALSHI_API_KEY_ID")
PRIVATE_KEY_PATH = os.getenv("KALSHI_PRIVATE_KEY_PATH", "/root/kalshi_private.key")
KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"


def load_private_key():
    log.info(f"Loading Kalshi key from {PRIVATE_KEY_PATH}")
    with open(PRIVATE_KEY_PATH, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def kalshi_get(path, params=None, pk=None):
    ts = str(int(time.time() * 1000))
    msg = (ts + "GET" + path).encode()
    sig = pk.sign(msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())
    headers = {
        "KALSHI-ACCESS-KEY": API_KEY_ID,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
        "KALSHI-ACCESS-TIMESTAMP": ts,
    }
    r = httpx.get(f"{KALSHI_BASE}{path}", params=params, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()


def get_market_by_ticker(ticker, pk):
    """Fetch a single market by ticker to check settlement status."""
    try:
        data = kalshi_get(f"/markets/{ticker}", pk=pk)
        return data.get("market", data)
    except Exception as e:
        log.warning(f"Could not fetch {ticker}: {e}")
        return None


# --- Scoring math ---
def brier_score(predicted_prob_yes, outcome_yes):
    """Brier score: (predicted - actual)^2. Lower is better."""
    return round((predicted_prob_yes - outcome_yes) ** 2, 6)


def log_loss_score(predicted_prob_yes, outcome_yes, eps=1e-6):
    """Log loss for a single prediction. Lower is better."""
    p = max(eps, min(1 - eps, predicted_prob_yes))
    if outcome_yes == 1:
        return round(-math.log(p), 6)
    else:
        return round(-math.log(1 - p), 6)


def theoretical_pnl(direction, price_at_scan, outcome_yes):
    """
    What you would have made/lost buying at price_at_scan.
    Returns P&L per $1 contract.
    """
    if direction == "YES":
        # Bought YES at price_at_scan
        if outcome_yes == 1:
            return round(1.0 - price_at_scan, 4)  # win
        else:
            return round(-price_at_scan, 4)  # lose
    else:
        # Bought NO at (1 - price_at_scan)
        no_price = 1.0 - price_at_scan
        if outcome_yes == 0:
            return round(1.0 - no_price, 4)  # win
        else:
            return round(-no_price, 4)  # lose


# --- Load all predictions ---
def load_snapshot_market_map(scan_date):
    """Load contemporaneous canonical snapshot keyed by ticker."""
    path = RAW_SNAPSHOTS / f"{scan_date}-markets.json"
    if not path.exists():
        return {}

    try:
        markets = json.loads(path.read_text())
    except Exception:
        return {}

    if not isinstance(markets, list):
        return {}

    return {
        m.get("ticker"): m
        for m in markets
        if m.get("ticker")
    }


def load_all_predictions():
    """
    Load original selected trades plus separate full-coverage Track B forecasts.

    Selected top-7 rows keep their original model labels.
    Full-coverage Track B rows use a distinct *_full_coverage model label so the
    two analyses remain separate and cannot collide in resolution deduplication.
    """
    predictions = []

    for f in sorted(RAW_SCANS.glob("*.json")):
        # Never treat read-only backup copies as separate predictions.
        if ".FIRST_VALID_FORWARD_BACKUP." in f.name:
            continue

        try:
            data = json.loads(f.read_text())
        except Exception:
            continue

        if data.get("error"):
            continue

        model = data.get("model", "unknown")
        scan_date = data.get("date", f.stem[:10])

        # Original selected-trade analysis remains unchanged.
        for trade in data.get("trades", []):
            predictions.append({
                "scan_date": scan_date,
                "model": model,
                "prediction_scope": "selected_top7",
                "ticker": trade.get("ticker"),
                "direction": trade.get("direction"),
                "current_price": trade.get("current_price"),
                "implied_prob": trade.get("implied_prob"),
                "prob_range": trade.get("prob_range"),
                "prob_midpoint": trade.get("prob_midpoint"),
                "edge_pct": trade.get("edge_pct"),
                "confidence": trade.get("confidence"),
                "category": trade.get("category"),
                "correlation_cluster_id": trade.get("correlation_cluster_id"),
                "resolution_date": trade.get("resolution_date"),
            })

        # Separate full-coverage Track B forecasting diagnostic.
        # Restrict this diagnostic to the prospectively registered experiment
        # lanes and preserve all historical date exclusions.
        if data.get("track") != "B":
            continue

        if model not in FULL_COVERAGE_TRACK_B_MODELS:
            continue

        if scan_date in FULL_COVERAGE_EXCLUDED_DATES:
            continue

        forecasts = data.get("forecasts", []) or []
        if not forecasts:
            continue

        snapshot_map = load_snapshot_market_map(scan_date)

        for forecast in forecasts:
            ticker = forecast.get("ticker")
            market = snapshot_map.get(ticker)

            if not ticker or not market:
                log.warning(
                    "Skipping full-coverage forecast without canonical snapshot market: "
                    f"{scan_date} {model} {ticker}"
                )
                continue

            midpoint = forecast.get("prob_midpoint")
            implied = market.get("implied_prob")

            if midpoint is None or implied is None:
                log.warning(
                    "Skipping full-coverage forecast missing probability data: "
                    f"{scan_date} {model} {ticker}"
                )
                continue

            midpoint = float(midpoint)
            implied = float(implied)

            predictions.append({
                "scan_date": scan_date,
                "model": f"{model}_full_coverage",
                "source_model": model,
                "prediction_scope": "full_coverage_track_b",
                "ticker": ticker,
                "direction": "YES" if midpoint > implied else "NO",
                "current_price": market.get("yes_price"),
                "implied_prob": implied,
                "prob_range": forecast.get("prob_range"),
                "prob_midpoint": midpoint,
                "edge_pct": round(abs(midpoint - implied) * 100),
                "confidence": forecast.get("confidence"),
                "category": forecast.get("category"),
                "correlation_cluster_id": None,
                "resolution_date": None,
                "snapshot_id": data.get("snapshot_id"),
            })

    return predictions


def load_already_resolved():
    """Load tickers we've already resolved to avoid re-processing."""
    resolved = set()
    for f in RAW_RESOLVED.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            for r in data.get("resolutions", []):
                resolved.add((r.get("ticker"), r.get("scan_date"), r.get("model")))
        except:
            continue
    return resolved


# --- Main ---
def main():
    dry_run = "--dry-run" in sys.argv
    pk = load_private_key()

    predictions = load_all_predictions()
    already_resolved = load_already_resolved()
    log.info(f"Loaded {len(predictions)} predictions, {len(already_resolved)} already resolved")

    # Group by ticker
    ticker_map = {}
    for p in predictions:
        t = p["ticker"]
        if t not in ticker_map:
            ticker_map[t] = []
        ticker_map[t].append(p)

    # Check each unique ticker for settlement
    resolutions = []
    checked = 0
    settled = 0

    for ticker, preds in ticker_map.items():
        # Skip if all predictions for this ticker are already resolved
        all_resolved = all(
            (p["ticker"], p["scan_date"], p["model"]) in already_resolved
            for p in preds
        )
        if all_resolved:
            continue

        checked += 1
        time.sleep(0.3)  # rate limiting
        market = get_market_by_ticker(ticker, pk)

        if market is None:
            continue

        status = market.get("status", "")
        result = market.get("result", "")  # "yes" or "no" or ""

        if status not in ("settled", "finalized") or result not in ("yes", "no"):
            continue

        settled += 1
        outcome_yes = 1 if result == "yes" else 0
        settlement_price = market.get("last_price", None)

        log.info(f"SETTLED: {ticker} → {result.upper()}")

        for p in preds:
            key = (p["ticker"], p["scan_date"], p["model"])
            if key in already_resolved:
                continue

            midpoint = p.get("prob_midpoint") or 0.5
            price = p.get("current_price") or p.get("implied_prob") or 0.5
            direction = p.get("direction", "YES")

            brier = brier_score(midpoint, outcome_yes)
            logloss = log_loss_score(midpoint, outcome_yes)
            market_brier = brier_score(p.get("implied_prob", 0.5), outcome_yes)
            pnl = theoretical_pnl(direction, price, outcome_yes)

            resolution = {
                "ticker": ticker,
                "scan_date": p["scan_date"],
                "model": p["model"],
                "source_model": p.get("source_model"),
                "prediction_scope": p.get("prediction_scope", "selected_top7"),
                "direction": direction,
                "prob_midpoint": midpoint,
                "implied_prob": p.get("implied_prob"),
                "current_price": price,
                "outcome": result,
                "outcome_yes": outcome_yes,
                "brier": brier,
                "market_brier": market_brier,
                "brier_edge": round(market_brier - brier, 6),
                "log_loss": logloss,
                "theoretical_pnl": pnl,
                "edge_pct": p.get("edge_pct"),
                "confidence": p.get("confidence"),
                "category": p.get("category"),
                "correlation_cluster_id": p.get("correlation_cluster_id"),
                "resolved_at": datetime.now(timezone.utc).isoformat(),
            }
            resolutions.append(resolution)

            direction_correct = (direction == "YES" and outcome_yes == 1) or (direction == "NO" and outcome_yes == 0)
            log.info(
                f"  {p['scan_date']} {p['model']:6s} {direction:3s} "
                f"mid={midpoint:.3f} impl={p.get('implied_prob',0):.3f} "
                f"brier={brier:.4f} mkt_brier={market_brier:.4f} "
                f"edge={round(market_brier-brier,4):+.4f} "
                f"pnl={pnl:+.4f} "
                f"{'✅' if direction_correct else '❌'}"
            )

    # Summary
    if resolutions:
        avg_brier = sum(r["brier"] for r in resolutions) / len(resolutions)
        avg_mkt_brier = sum(r["market_brier"] for r in resolutions) / len(resolutions)
        avg_pnl = sum(r["theoretical_pnl"] for r in resolutions) / len(resolutions)
        wins = sum(1 for r in resolutions if r["theoretical_pnl"] > 0)
        losses = sum(1 for r in resolutions if r["theoretical_pnl"] < 0)

        summary = {
            "resolved_at": datetime.now(timezone.utc).isoformat(),
            "total_predictions": len(resolutions),
            "unique_tickers_settled": settled,
            "tickers_checked": checked,
            "avg_brier": round(avg_brier, 4),
            "avg_market_brier": round(avg_mkt_brier, 4),
            "avg_brier_edge": round(avg_mkt_brier - avg_brier, 4),
            "avg_theoretical_pnl": round(avg_pnl, 4),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / len(resolutions), 4) if resolutions else 0,
            "by_model": {},
            "by_category": {},
            "resolutions": resolutions,
        }

        # Per-model breakdown
        for model in set(r["model"] for r in resolutions):
            model_res = [r for r in resolutions if r["model"] == model]
            summary["by_model"][model] = {
                "count": len(model_res),
                "avg_brier": round(sum(r["brier"] for r in model_res) / len(model_res), 4),
                "avg_brier_edge": round(sum(r["brier_edge"] for r in model_res) / len(model_res), 4),
                "avg_pnl": round(sum(r["theoretical_pnl"] for r in model_res) / len(model_res), 4),
                "wins": sum(1 for r in model_res if r["theoretical_pnl"] > 0),
                "losses": sum(1 for r in model_res if r["theoretical_pnl"] < 0),
            }

        # Per-category breakdown
        for cat in set(r.get("category", "other") for r in resolutions):
            cat_res = [r for r in resolutions if r.get("category") == cat]
            summary["by_category"][cat] = {
                "count": len(cat_res),
                "avg_brier": round(sum(r["brier"] for r in cat_res) / len(cat_res), 4),
                "avg_brier_edge": round(sum(r["brier_edge"] for r in cat_res) / len(cat_res), 4),
                "avg_pnl": round(sum(r["theoretical_pnl"] for r in cat_res) / len(cat_res), 4),
            }

        log.info(f"\n{'='*60}")
        log.info(f"RESOLUTION SUMMARY")
        log.info(f"{'='*60}")
        log.info(f"Predictions scored: {len(resolutions)}")
        log.info(f"Avg Brier:        {avg_brier:.4f}")
        log.info(f"Avg Market Brier: {avg_mkt_brier:.4f}")
        log.info(f"Brier Edge:       {round(avg_mkt_brier - avg_brier, 4):+.4f}")
        log.info(f"Avg Theo P&L:     {avg_pnl:+.4f}")
        log.info(f"Win/Loss:         {wins}/{losses} ({round(wins/len(resolutions)*100)}%)")

        if not dry_run:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            out_path = RAW_RESOLVED / f"{date}-resolved.json"
            out_path.write_text(json.dumps(summary, indent=2))
            log.info(f"Saved: {out_path}")
        else:
            print(json.dumps(summary, indent=2))
    else:
        log.info(f"No new settlements found. Checked {checked} tickers.")


if __name__ == "__main__":
    main()
