#!/usr/bin/env python3
"""
Kalshi Daily Scanner
====================
Pull markets by series ticker → call Claude + Gemini in parallel → cross-validate → Telegram alert.

Usage:
    python3 tools/scanner.py              # full run
    python3 tools/scanner.py --pull-only  # just pull markets and save snapshot
    python3 tools/scanner.py --dry-run    # full run but skip Telegram alert
"""

import asyncio
import base64
import json
import os
import sys
import time
import re
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx
import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
RAW_SCANS = ROOT / "raw" / "scans"
RAW_CONSENSUS = ROOT / "raw" / "consensus"
RAW_SNAPSHOTS = ROOT / "raw" / "snapshots"
PROMPTS_DIR = ROOT / "tools" / "prompts"

KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
DIGEST_LENGTH = 32

# Series tickers to scan — add new ones as you discover them
SERIES_TICKERS = [
    # Macro / Economics
    "KXCPI",
    "KXCPIYOY",
    "KXRATECUT",
    "KXRATECUTCOUNT",
    "KXRECSSNBER",
    "KXGDP",
    "KXNFP",
    "KXPCE",
    "KXUNRATE",
    "KXPPI",
    "KXINITCLAIMS",
    # Commodities / Crypto
    "KXBTC",
    "KXETH",
    "KXOILWTI",
    "KXOIL",
    "KXGOLD",
    "KXGAS",
    # Weather
    "KXHIGHNY",
    "KXHIGHCHI",
    "KXHIGHLA",
    "KXHIGHMIA",
    "KXHIGHHOU",
    "KXHURRICANE",
    # Politics
    "KXTRUMP",
    "KXAPPROVAL",
    "KXHOUSEREP",
    "KXHOUSEDEMS",
    "KXSENATEREP",
    "KXSENATEDEMS",
    "KXFBI",
    "KXCABINET",
    "KXINAUGCABINET",
    "KXCEASEFIRE",
    "KXIRAN",
    # Finance
    "KXSP500",
    "KXFEDRATE",
]

TOP_N_MARKETS = 50

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scanner")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_env():
    env_path = ROOT / ".env"
    if not env_path.exists():
        log.error(f".env not found at {env_path}")
        sys.exit(1)
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def today_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_dirs():
    for d in [RAW_SCANS, RAW_CONSENSUS, RAW_SNAPSHOTS]:
        d.mkdir(parents=True, exist_ok=True)


def parse_dollar(val) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# 1. Kalshi Auth (RSA-PSS signing)
# ---------------------------------------------------------------------------

def load_private_key(key_path: str):
    from cryptography.hazmat.primitives import serialization
    with open(key_path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def sign_request(private_key, timestamp_ms: str, method: str, path: str) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    message = f"{timestamp_ms}{method.upper()}{path}".encode("utf-8")
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def kalshi_auth_headers(api_key_id: str, private_key, method: str, path: str) -> dict:
    timestamp_ms = str(int(time.time() * 1000))
    signature = sign_request(private_key, timestamp_ms, method, path)
    return {
        "KALSHI-ACCESS-KEY": api_key_id,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# 2. Kalshi Market Puller (by series ticker)
# ---------------------------------------------------------------------------

def pull_markets_by_series(api_key_id: str, private_key, series_list: list[str]) -> list[dict]:
    """Pull open markets for each series ticker."""
    all_markets = []
    client = httpx.Client(timeout=30)
    found_series = 0

    for series in series_list:
        path = "/markets"
        params = {"limit": 200, "status": "open", "series_ticker": series}
        headers = kalshi_auth_headers(api_key_id, private_key, "GET", path)
        url = f"{KALSHI_BASE}{path}"

        try:
            r = client.get(url, params=params, headers=headers)
            if r.status_code == 429:
                log.warning(f"Rate limited on {series}, sleeping 2s...")
                time.sleep(2)
                headers = kalshi_auth_headers(api_key_id, private_key, "GET", path)
                r = client.get(url, params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
            markets = data.get("markets", [])
            if markets:
                found_series += 1
                all_markets.extend(markets)
        except Exception as e:
            log.warning(f"Error pulling {series}: {e}")

        time.sleep(0.3)

    client.close()
    log.info(f"Pulled {len(all_markets)} markets from {found_series}/{len(series_list)} series")
    return all_markets


def filter_and_enrich(markets: list[dict], top_n: int = TOP_N_MARKETS) -> list[dict]:
    """Filter for markets with real orderbooks and pre-compute fields."""
    enriched = []

    for m in markets:
        yes_bid = parse_dollar(m.get("yes_bid_dollars"))
        yes_ask = parse_dollar(m.get("yes_ask_dollars"))
        yes_price = parse_dollar(m.get("last_price_dollars")) or yes_ask
        no_bid = parse_dollar(m.get("no_bid_dollars"))
        no_ask = parse_dollar(m.get("no_ask_dollars"))
        volume = parse_dollar(m.get("volume_fp"))

        # Skip markets with no price or no orderbook
        if yes_price == 0 and yes_ask == 0:
            continue

        # Skip markets with no two-sided book
        if yes_bid == 0 and yes_ask == 0:
            continue

        # Derive no_price
        no_price = no_bid if no_bid > 0 else (1.0 - yes_price if yes_price > 0 else 0.5)

        # Implied probability
        denom = yes_price + no_price
        implied_prob = round(yes_price / denom, 4) if denom > 0 else 0.5

        # Spread
        spread = round(yes_ask - yes_bid, 4) if (yes_ask > 0 and yes_bid > 0) else 0.99

        # Mid price
        mid_price = round((yes_bid + yes_ask) / 2, 4) if (yes_ask > 0 and yes_bid > 0) else yes_price

        # Skip wide spreads (no real liquidity)
        if spread >= 0.20:
            continue

        enriched.append({
            "ticker": m.get("ticker", ""),
            "title": m.get("title", ""),
            "subtitle": m.get("yes_sub_title", "") or m.get("subtitle", ""),
            "category": m.get("category", m.get("market_type", "other")),
            "yes_bid": round(yes_bid, 4),
            "yes_ask": round(yes_ask, 4),
            "yes_price": round(yes_price, 4),
            "no_price": round(no_price, 4),
            "implied_prob": implied_prob,
            "spread": spread,
            "mid_price": mid_price,
            "volume": volume,
            "volume_24h": parse_dollar(m.get("volume_24h_fp")),
            "open_interest": parse_dollar(m.get("open_interest_fp")),
            "close_time": m.get("close_time", ""),
            "resolution_source": (m.get("rules_primary", "") or "")[:200],
        })

    # Sort by volume descending, take top N
    enriched.sort(key=lambda x: x["volume"], reverse=True)
    result = enriched[:top_n]
    log.info(f"Filtered to {len(result)} markets with real orderbooks (spread<20c) from {len(enriched)} candidates")
    return result


# ---------------------------------------------------------------------------
# 3. Prompt Loading
# ---------------------------------------------------------------------------

def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    if not path.exists():
        log.error(f"Prompt file not found: {path}")
        sys.exit(1)
    return path.read_text()


def build_scanner_prompt(markets_json: str) -> str:
    template = load_prompt("scanner.md")
    prompt = template.replace("{{DATE}}", today_str())
    prompt = prompt.replace("{{SCAN_TIMESTAMP_UTC}}", now_iso())
    prompt = prompt.replace("{{INJECTED_KALSHI_API_JSON}}", markets_json)
    prompt = re.sub(
        r"\{\{#if INJECTED_SPORTS_ODDS_JSON\}\}.*?\{\{/if\}\}",
        "",
        prompt,
        flags=re.DOTALL,
    )
    return prompt


def build_synthesizer_prompt(claude_output: str, gemini_output: str) -> str:
    template = load_prompt("synthesizer.md")
    prompt = template.replace("{{DATE}}", today_str())
    prompt = prompt.replace("{{CLAUDE_OUTPUT}}", claude_output)
    prompt = prompt.replace("{{GEMINI_OUTPUT}}", gemini_output)
    return prompt


# ---------------------------------------------------------------------------
# 4. Model Calls
# ---------------------------------------------------------------------------

async def call_claude(prompt: str) -> str:
    import anthropic

    log.info("Calling Claude...")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )
        text_parts = [b.text for b in response.content if hasattr(b, "text")]
        result = "\n".join(text_parts).strip()
        log.info(f"Claude responded ({len(result)} chars)")
        return result
    except Exception as e:
        log.error(f"Claude API error: {e}")
        return json.dumps({
            "date": today_str(), "model": "claude",
            "markets_analyzed": 0, "trades": [],
            "avoid": [], "no_trades_today": True,
            "notes": f"API error: {str(e)}",
        })


async def call_gemini(prompt: str) -> str:
    log.info("Calling Gemini...")
    api_key = os.environ["GEMINI_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8192},
    }

    try:
        r = requests.post(url, json=payload, timeout=180)
        r.raise_for_status()
        data = r.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError("No candidates in Gemini response")
        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = [p["text"] for p in parts if "text" in p]
        result = "\n".join(text_parts).strip()
        log.info(f"Gemini responded ({len(result)} chars)")
        return result
    except Exception as e:
        log.error(f"Gemini API error: {e}")
        return json.dumps({
            "date": today_str(), "model": "gemini",
            "markets_analyzed": 0, "trades": [],
            "avoid": [], "no_trades_today": True,
            "notes": f"API error: {str(e)}",
        })


async def call_synthesizer(claude_output: str, gemini_output: str) -> str:
    import anthropic

    log.info("Running synthesizer...")
    prompt = build_synthesizer_prompt(claude_output, gemini_output)
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        text_parts = [b.text for b in response.content if hasattr(b, "text")]
        result = "\n".join(text_parts).strip()
        log.info(f"Synthesizer responded ({len(result)} chars)")
        return result
    except Exception as e:
        log.error(f"Synthesizer error: {e}")
        return json.dumps({
            "date": today_str(), "no_trades_today": True,
            "consensus_trades": [],
            "notes": f"Synthesizer error: {str(e)}",
        })


# ---------------------------------------------------------------------------
# 5. JSON Parsing + Validation
# ---------------------------------------------------------------------------

def parse_model_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = [l for l in text.split("\n") if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        log.warning("No JSON object found in model output")
        return {"error": "no_json", "raw": text[:500]}
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError as e:
        log.warning(f"JSON parse error: {e}")
        return {"error": str(e), "raw": text[start:start + 500]}


def validate_edge(parsed: dict) -> dict:
    if "trades" not in parsed:
        return parsed
    for trade in parsed["trades"]:
        implied = trade.get("implied_prob")
        prob_range = trade.get("prob_range")
        if implied is None or prob_range is None:
            continue
        midpoint = (prob_range[0] + prob_range[1]) / 2
        trade["prob_midpoint"] = round(midpoint, 4)
        edge = abs(midpoint - implied) * 100
        trade["edge_pct"] = round(edge)
        correct_direction = "YES" if midpoint > implied else "NO"
        if trade.get("direction") != correct_direction:
            log.warning(
                f"Direction correction: {trade.get('ticker')} "
                f"was {trade.get('direction')}, should be {correct_direction}"
            )
            trade["direction"] = correct_direction
    return parsed


# ---------------------------------------------------------------------------
# 6. Telegram Alert
# ---------------------------------------------------------------------------

def send_telegram(message: str):
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    chunks = []
    while len(message) > 4000:
        split_at = message.rfind("\n", 0, 4000)
        if split_at == -1:
            split_at = 4000
        chunks.append(message[:split_at])
        message = message[split_at:]
    chunks.append(message)
    for chunk in chunks:
        try:
            r = requests.post(url, json={
                "chat_id": chat_id, "text": chunk, 
            }, timeout=10)
            r.raise_for_status()
        except Exception as e:
            log.error(f"Telegram error: {e}")


def format_telegram_alert(consensus: dict) -> str:
    date = consensus.get("date", today_str())
    lines = [f"*Kalshi Scanner {date}*\n"]

    rc = consensus.get("macro_regime_claude", "?")
    rg = consensus.get("macro_regime_gemini", "?")
    agree = "Y" if consensus.get("regime_agreement") else "N"
    lines.append(f"Regime: C={rc} G={rg} Agree={agree}\n")

    trades = consensus.get("consensus_trades", [])
    if not trades:
        lines.append("No consensus trades.")
    else:
        lines.append(f"*{len(trades)} Consensus Trade(s):*\n")
        for t in trades:
            lines.append(f"*{t.get('direction','?')} {t.get('ticker','?')}*")
            lines.append(f"  Edge: {t.get('consensus_edge',0)}% (agg: {t.get('aggressive_edge',0)}%)")
            lines.append(f"  Max px: {t.get('max_acceptable_price','?')} | Wt: {t.get('relative_weight',0)}/10")
            lines.append(f"  Cluster: {t.get('correlation_cluster_id','?')}")
            lines.append(f"  Catalyst: {t.get('catalyst','')}")
            valid = t.get("entry_valid_until", "")
            if valid:
                lines.append(f"  Valid until: {valid}")
            risk = t.get("risk_notes", "")
            if risk:
                lines.append(f"  Risk: {risk}")
            lines.append("")

    singles = consensus.get("single_source_trades", [])
    if singles:
        lines.append(f"\n*{len(singles)} Single-Source:*")
        for s in singles:
            lines.append(
                f"  {s.get('direction')} {s.get('ticker')} "
                f"({s.get('source')}, {s.get('edge')}% edge)"
            )

    contras = consensus.get("contradictions", [])
    if contras:
        lines.append(f"\n*{len(contras)} Contradiction(s):*")
        for c in contras:
            lines.append(f"  {c.get('market')} - {c.get('contradiction_type')}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 7. File Saving
# ---------------------------------------------------------------------------

def save_raw(subdir: Path, filename: str, data):
    path = subdir / filename
    if isinstance(data, (dict, list)):
        path.write_text(json.dumps(data, indent=2))
    else:
        path.write_text(str(data))
    log.info(f"Saved: {path}")


def append_log(entry: str):
    log_path = ROOT / "log.md"
    with open(log_path, "a") as f:
        f.write(f"\n{entry}\n")


# ---------------------------------------------------------------------------
# 8. Main Pipeline
# ---------------------------------------------------------------------------

async def run(args):
    load_env()
    ensure_dirs()
    date = today_str()
    ts = now_iso()

    # --- Step 1: Pull markets by series ---
    api_key_id = os.environ["KALSHI_API_KEY_ID"]
    key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "/root/kalshi_private.key")
    log.info(f"Loading Kalshi key from {key_path}")
    private_key = load_private_key(key_path)

    raw_markets = pull_markets_by_series(api_key_id, private_key, SERIES_TICKERS)
    markets = filter_and_enrich(raw_markets)
    save_raw(RAW_SNAPSHOTS, f"{date}-markets.json", markets)

    if args.pull_only:
        log.info(f"--pull-only: saved {len(markets)} markets. Done.")
        return

    if len(markets) == 0:
        log.warning("No markets with real orderbooks found. Aborting.")
        append_log(f"## [{date}] scan | ABORT\n- No markets with real orderbooks.")
        return

    # --- Step 2: Build prompt ---
    markets_json = json.dumps(markets, indent=2)
    scanner_prompt = build_scanner_prompt(markets_json)

    # --- Step 3: Call models in parallel ---
    claude_raw, gemini_raw = await asyncio.gather(
        call_claude(scanner_prompt),
        call_gemini(scanner_prompt),
    )

    claude_parsed = validate_edge(parse_model_json(claude_raw))
    gemini_parsed = validate_edge(parse_model_json(gemini_raw))
    claude_parsed.setdefault("model", "claude")
    gemini_parsed.setdefault("model", "gemini")

    save_raw(RAW_SCANS, f"{date}-claude.json", claude_parsed)
    save_raw(RAW_SCANS, f"{date}-gemini.json", gemini_parsed)

    # --- Step 4: Short-circuit if both empty ---
    if claude_parsed.get("no_trades_today") and gemini_parsed.get("no_trades_today"):
        log.info("Both models: no trades today.")
        consensus = {"date": date, "no_trades_today": True, "consensus_trades": []}
        save_raw(RAW_CONSENSUS, f"{date}-consensus.json", consensus)
        append_log(f"## [{date}] scan | No Trades\n- Both models passed.")
        if not args.dry_run:
            send_telegram(f"*Kalshi Scanner {date}*\n\nNo trades today.")
        return

    # --- Step 5: Synthesize ---
    log.info("Waiting 65s for rate limit cooldown...")
    import time as _t; _t.sleep(65)
    synth_raw = await call_synthesizer(
        json.dumps(claude_parsed, indent=2),
        json.dumps(gemini_parsed, indent=2),
    )
    consensus = parse_model_json(synth_raw)

    # Drop negative max_acceptable_price trades
    if "consensus_trades" in consensus:
        valid = [t for t in consensus["consensus_trades"]
                 if (t.get("max_acceptable_price") or 1) > 0]
        dropped = len(consensus["consensus_trades"]) - len(valid)
        if dropped:
            log.warning(f"Dropped {dropped} trades with negative limit price")
        consensus["consensus_trades"] = valid
        if not valid and not consensus.get("single_source_trades"):
            consensus["no_trades_today"] = True

    save_raw(RAW_CONSENSUS, f"{date}-consensus.json", consensus)

    # --- Step 6: Log ---
    n_c = len(claude_parsed.get("trades", []))
    n_g = len(gemini_parsed.get("trades", []))
    n_con = len(consensus.get("consensus_trades", []))
    append_log(
        f"## [{date}] scan | Daily Scan\n"
        f"- Markets: {len(markets)} | Claude: {n_c} | Gemini: {n_g} | Consensus: {n_con}"
    )

    # --- Step 7: Alert ---
    if consensus.get("no_trades_today"):
        log.info("No consensus trades.")
        if not args.dry_run:
            send_telegram(f"*Kalshi Scanner {date}*\n\nNo consensus trades. C:{n_c} G:{n_g}")
    else:
        alert = format_telegram_alert(consensus)
        if args.dry_run:
            print("\n--- DRY RUN ALERT ---")
            print(alert)
        else:
            send_telegram(alert)

    log.info("Done.")


def main():
    parser = argparse.ArgumentParser(description="Kalshi Daily Scanner")
    parser.add_argument("--pull-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
