#!/usr/bin/env python3
"""
Shadow-only GPT-5.6 / Fable 5 experiment runner.

This runner is isolated from the legacy live scanner. It reuses one saved
canonical market snapshot, never changes execution, and never enters Haiku.

Track A: existing price-visible prompt path.
Track B: price-blind, no-search forecasts in 25-market chunks, followed by
 deterministic post-hoc selection against the exact canonical snapshot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.scanner import build_scanner_prompt, load_prompt, today_str  # noqa: E402

RAW_SNAPSHOTS = ROOT / "raw" / "snapshots"
RAW_SCANS = ROOT / "raw" / "scans"
RAW_BATCHES = ROOT / "raw" / "batches"

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
ANTHROPIC_BATCHES_URL = "https://api.anthropic.com/v1/messages/batches"
BLIND_CHUNK_SIZE = 25

# Track B payload is whitelist-only. New Kalshi fields cannot leak in by default.
BLIND_FIELD_WHITELIST = (
    "ticker",
    "title",
    "subtitle",
    "close_time",
    "resolution_source",
)

EDGE_THRESHOLDS = {
    "macro": 0.08,
    "weather": 0.05,
    "politics": 0.10,
    "crypto": 0.12,
    "tech": 0.10,
    "sports": 0.08,
    "other": 0.10,
}

# Deterministic category ownership. Models never assign category in Track B.
CATEGORY_PREFIXES: dict[str, tuple[str, ...]] = {
    "macro": (
        "KXCPI", "KXCPIYOY", "KXRATECUT", "KXRATECUTCOUNT", "KXRECSSNBER",
        "KXGDP", "KXNFP", "KXPCE", "KXUNRATE", "KXPPI", "KXINITCLAIMS",
        "KXFEDRATE",
    ),
    "weather": (
        "KXHIGHNY", "KXHIGHCHI", "KXHIGHLA", "KXHIGHMIA", "KXHIGHHOU",
        "KXHURRICANE",
    ),
    "crypto": ("KXBTC", "KXETH"),
    "tech": ("KXAIMODEL", "KXAILMMSYS"),
    "politics": (
        "KXTRUMP", "KXAPPROVAL", "KXHOUSEREP", "KXHOUSEDEMS",
        "KXSENATEREP", "KXSENATEDEMS", "KXFBI", "KXCABINET",
        "KXINAUGCABINET", "KXCEASEFIRE", "KXIRAN", "KXHORMUZ",
        "KXDHSSHUTDOWN", "KXSHUTDOWN", "KXAG", "KXZELDIN",
    ),
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("shadow_experiment")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_dirs() -> None:
    for directory in (RAW_SNAPSHOTS, RAW_SCANS, RAW_BATCHES):
        directory.mkdir(parents=True, exist_ok=True)


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def snapshot_id(markets: list[dict]) -> str:
    return hashlib.sha256(canonical_json(markets).encode("utf-8")).hexdigest()


def load_snapshot(date: str) -> list[dict]:
    path = RAW_SNAPSHOTS / f"{date}-markets.json"
    if not path.exists():
        raise FileNotFoundError(f"Canonical snapshot missing: {path}")
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError(f"Snapshot must be a JSON list: {path}")
    return data


def blind_payload(markets: list[dict]) -> list[dict]:
    """Whitelist-only blind payload. Unknown/new Kalshi fields are excluded."""
    return [
        {key: market.get(key, "") for key in BLIND_FIELD_WHITELIST}
        for market in markets
    ]


def chunk_markets(markets: list[dict], size: int = BLIND_CHUNK_SIZE) -> list[list[dict]]:
    return [markets[i : i + size] for i in range(0, len(markets), size)]


def category_from_ticker(ticker: str) -> str:
    ticker = str(ticker or "").upper()
    for category, prefixes in CATEGORY_PREFIXES.items():
        if any(ticker.startswith(prefix) for prefix in prefixes):
            return category
    return "other"


def build_blind_prompt(markets: list[dict], snap_id: str, chunk_id: str) -> str:
    template = load_prompt("scanner_blind.md")
    return (
        template.replace("{{DATE}}", today_str())
        .replace("{{SCAN_TIMESTAMP_UTC}}", now_iso())
        .replace("{{SNAPSHOT_ID}}", snap_id)
        .replace("{{CHUNK_ID}}", chunk_id)
        .replace("{{INJECTED_BLIND_MARKETS_JSON}}", json.dumps(blind_payload(markets), indent=2))
    )


def parse_json_object(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = "\n".join(
            line for line in text.splitlines() if not line.strip().startswith("```")
        ).strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0 or end <= 0:
        raise ValueError("No complete JSON object found in model output; possible truncation")
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid/truncated JSON output: {exc}") from exc


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False))
    log.info("Saved %s", path)


def extract_openai_output_text(payload: dict) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    chunks: list[str] = []
    for item in payload.get("output", []) or []:
        for content in item.get("content", []) or []:
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    if not chunks:
        raise ValueError("OpenAI response contained no text output")
    return "\n".join(chunks)


def call_openai(prompt: str, model: str, max_output_tokens: int = 8192) -> tuple[dict, dict]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    response = requests.post(
        OPENAI_RESPONSES_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "input": prompt,
            "max_output_tokens": max_output_tokens,
        },
        timeout=600,
    )
    response.raise_for_status()
    payload = response.json()
    return parse_json_object(extract_openai_output_text(payload)), payload.get("usage", {}) or {}


def normalize_blind_forecasts(
    forecasts: list[dict],
    canonical_markets: list[dict],
    *,
    source: str,
) -> tuple[list[dict], list[dict]]:
    """Validate forecasts, recompute arithmetic, assign code-owned categories."""
    market_by_ticker = {m.get("ticker"): m for m in canonical_markets}
    normalized: list[dict] = []
    warnings: list[dict] = []
    seen: set[str] = set()

    for raw in forecasts or []:
        ticker = raw.get("ticker")
        if ticker not in market_by_ticker:
            warnings.append({"type": "unknown_ticker", "ticker": ticker, "source": source})
            continue
        if ticker in seen:
            warnings.append({"type": "duplicate_ticker", "ticker": ticker, "source": source})
            continue
        seen.add(ticker)

        prob_range = raw.get("prob_range")
        if not isinstance(prob_range, list) or len(prob_range) != 2:
            warnings.append({"type": "invalid_prob_range", "ticker": ticker, "source": source})
            continue
        try:
            low = float(prob_range[0])
            high = float(prob_range[1])
        except (TypeError, ValueError):
            warnings.append({"type": "non_numeric_prob_range", "ticker": ticker, "source": source})
            continue
        if low > high:
            low, high = high, low
            warnings.append({"type": "reversed_prob_range_corrected", "ticker": ticker, "source": source})
        if not (0.0 <= low <= 1.0 and 0.0 <= high <= 1.0):
            warnings.append({"type": "out_of_bounds_prob_range", "ticker": ticker, "source": source})
            continue

        midpoint = (low + high) / 2.0
        supplied_mid = raw.get("prob_midpoint")
        if supplied_mid is not None:
            try:
                if abs(float(supplied_mid) - midpoint) > 1e-6:
                    warnings.append({
                        "type": "midpoint_mismatch_recomputed",
                        "ticker": ticker,
                        "supplied": supplied_mid,
                        "computed": round(midpoint, 6),
                        "source": source,
                    })
            except (TypeError, ValueError):
                warnings.append({"type": "invalid_supplied_midpoint_ignored", "ticker": ticker, "source": source})

        normalized.append({
            "ticker": ticker,
            "prob_range": [round(low, 6), round(high, 6)],
            "prob_midpoint": round(midpoint, 6),
            "confidence": raw.get("confidence", "medium"),
            "category": category_from_ticker(ticker),
        })

    return normalized, warnings


def mechanical_track_b_selection(
    forecasts: list[dict], canonical_markets: list[dict]
) -> list[dict]:
    market_by_ticker = {m.get("ticker"): m for m in canonical_markets}
    selected: list[dict] = []

    for forecast in forecasts:
        ticker = forecast["ticker"]
        market = market_by_ticker[ticker]
        midpoint = float(forecast["prob_midpoint"])
        implied = float(market["implied_prob"])
        category = category_from_ticker(ticker)
        edge = abs(midpoint - implied)
        if edge < EDGE_THRESHOLDS[category]:
            continue

        selected.append({
            "market": market.get("title", ""),
            "ticker": ticker,
            "direction": "YES" if midpoint > implied else "NO",
            "current_price": market.get("yes_price"),
            "implied_prob": implied,
            "prob_range": forecast["prob_range"],
            "prob_midpoint": round(midpoint, 4),
            "edge_pct": round(edge * 100),
            "confidence": forecast.get("confidence", "medium"),
            "category": category,
        })

    selected.sort(key=lambda item: item["edge_pct"], reverse=True)
    return selected[:7]


def decorate_track_a(parsed: dict, *, model_label: str, snap_id: str, usage: Any) -> dict:
    parsed = dict(parsed)
    parsed["model"] = model_label
    parsed["track"] = "A"
    parsed["snapshot_id"] = snap_id
    parsed["api_usage"] = usage
    parsed["shadow_only"] = True
    parsed["external_search_enabled"] = False
    return parsed


def decorate_track_b(
    forecasts: list[dict],
    *,
    model_label: str,
    snap_id: str,
    usage: Any,
    canonical_markets: list[dict],
    warnings: list[dict],
    partial_failures: list[dict],
) -> dict:
    selected = mechanical_track_b_selection(forecasts, canonical_markets)
    expected = {m.get("ticker") for m in canonical_markets}
    returned = {f.get("ticker") for f in forecasts}
    missing = sorted(t for t in expected - returned if t)
    return {
        "date": today_str(),
        "scan_timestamp": now_iso(),
        "model": model_label,
        "track": "B",
        "snapshot_id": snap_id,
        "markets_expected": len(canonical_markets),
        "markets_analyzed": len(forecasts),
        "missing_tickers": missing,
        "forecasts": forecasts,
        "trades": selected,
        "no_trades_today": len(selected) == 0,
        "api_usage": usage,
        "shadow_only": True,
        "external_search_enabled": False,
        "selection_method": "deterministic_posthoc_v1_thresholds_max7",
        "validation_warnings": warnings,
        "partial_failures": partial_failures,
        "partial": bool(missing or partial_failures),
    }


def graceful_gap(model_label: str, track: str, snap_id: str, error: Exception) -> dict:
    return {
        "date": today_str(),
        "scan_timestamp": now_iso(),
        "model": model_label,
        "track": track,
        "snapshot_id": snap_id,
        "shadow_only": True,
        "gap": True,
        "error": str(error),
        "trades": [],
        "no_trades_today": True,
    }


def run_openai_track_b(markets: list[dict], snap_id: str, model: str) -> dict:
    all_forecasts: list[dict] = []
    warnings: list[dict] = []
    partial_failures: list[dict] = []
    usages: list[dict] = []

    for index, chunk in enumerate(chunk_markets(markets)):
        chunk_id = f"c{index:02d}"
        try:
            parsed, usage = call_openai(build_blind_prompt(chunk, snap_id, chunk_id), model)
            normalized, chunk_warnings = normalize_blind_forecasts(
                parsed.get("forecasts", []), chunk, source=chunk_id
            )
            all_forecasts.extend(normalized)
            warnings.extend(chunk_warnings)
            usages.append({"chunk_id": chunk_id, "usage": usage})
        except Exception as exc:
            log.exception("GPT-5.6 Track B partial failure %s: %s", chunk_id, exc)
            partial_failures.append({"chunk_id": chunk_id, "error": str(exc)})

    if not all_forecasts:
        raise RuntimeError(f"All Track B chunks failed: {partial_failures}")

    return decorate_track_b(
        all_forecasts,
        model_label="gpt56_track_b",
        snap_id=snap_id,
        usage=usages,
        canonical_markets=markets,
        warnings=warnings,
        partial_failures=partial_failures,
    )


def run_openai(date: str) -> None:
    markets = load_snapshot(date)
    snap_id = snapshot_id(markets)
    model = os.environ.get("OPENAI_SHADOW_MODEL", "gpt-5.6")

    # Track A remains one price-visible call. No external tools/search are enabled.
    try:
        parsed_a, usage_a = call_openai(build_scanner_prompt(json.dumps(markets, indent=2)), model)
        output_a = decorate_track_a(parsed_a, model_label="gpt56_track_a", snap_id=snap_id, usage=usage_a)
    except Exception as exc:
        log.exception("GPT-5.6 Track A gap: %s", exc)
        output_a = graceful_gap("gpt56_track_a", "A", snap_id, exc)
    save_json(RAW_SCANS / f"{date}-gpt56-track-a.json", output_a)

    try:
        output_b = run_openai_track_b(markets, snap_id, model)
    except Exception as exc:
        log.exception("GPT-5.6 Track B gap: %s", exc)
        output_b = graceful_gap("gpt56_track_b", "B", snap_id, exc)
    save_json(RAW_SCANS / f"{date}-gpt56-track-b.json", output_b)


def anthropic_headers() -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }


def submit_fable_batch(date: str) -> None:
    markets = load_snapshot(date)
    snap_id = snapshot_id(markets)
    model = os.environ.get("FABLE_SHADOW_MODEL", "claude-fable-5")

    requests_payload = [
        {
            "custom_id": f"{date}-fable5-track-a",
            "params": {
                "model": model,
                "max_tokens": 8192,
                "messages": [{"role": "user", "content": build_scanner_prompt(json.dumps(markets, indent=2))}],
            },
        }
    ]

    for index, chunk in enumerate(chunk_markets(markets)):
        chunk_id = f"c{index:02d}"
        requests_payload.append({
            "custom_id": f"{date}-fable5-track-b-{chunk_id}",
            "params": {
                "model": model,
                "max_tokens": 8192,
                "messages": [{"role": "user", "content": build_blind_prompt(chunk, snap_id, chunk_id)}],
            },
        })

    state_path = RAW_BATCHES / f"{date}-fable5.json"
    if state_path.exists():
        existing = json.loads(state_path.read_text())
        if existing.get("batch_id"):
            log.info("Fable batch already submitted for %s: %s", date, existing["batch_id"])
            return

    response = requests.post(
        ANTHROPIC_BATCHES_URL,
        headers=anthropic_headers(),
        json={"requests": requests_payload},
        timeout=120,
    )
    response.raise_for_status()
    body = response.json()
    save_json(state_path, {
        "date": date,
        "snapshot_id": snap_id,
        "batch_id": body.get("id"),
        "processing_status": body.get("processing_status"),
        "submitted_at": now_iso(),
        "model": model,
        "expected_custom_ids": [item["custom_id"] for item in requests_payload],
    })


def extract_anthropic_message_text(message: dict) -> str:
    chunks: list[str] = []
    for block in message.get("content", []) or []:
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            chunks.append(block["text"])
    if not chunks:
        raise ValueError("Anthropic batch result contained no text")
    return "\n".join(chunks)


def poll_fable_batch(date: str) -> None:
    state_path = RAW_BATCHES / f"{date}-fable5.json"
    if not state_path.exists():
        log.warning("No Fable batch state for %s", date)
        return

    state = json.loads(state_path.read_text())
    batch_id = state.get("batch_id")
    snap_id = state.get("snapshot_id")
    if not batch_id:
        log.warning("Fable batch state missing batch_id: %s", state_path)
        return

    status_response = requests.get(
        f"{ANTHROPIC_BATCHES_URL}/{batch_id}", headers=anthropic_headers(), timeout=60
    )
    status_response.raise_for_status()
    status = status_response.json()
    state["processing_status"] = status.get("processing_status")
    state["last_polled_at"] = now_iso()
    save_json(state_path, state)

    if status.get("processing_status") != "ended":
        log.info("Fable batch %s not ended yet: %s", batch_id, status.get("processing_status"))
        return

    results_response = requests.get(
        f"{ANTHROPIC_BATCHES_URL}/{batch_id}/results",
        headers=anthropic_headers(),
        timeout=120,
    )
    results_response.raise_for_status()

    markets = load_snapshot(date)
    chunks_by_id = {f"c{i:02d}": chunk for i, chunk in enumerate(chunk_markets(markets))}
    all_forecasts: list[dict] = []
    warnings: list[dict] = []
    partial_failures: list[dict] = []
    usages: list[dict] = []
    seen: set[str] = set()
    track_a_saved = False

    for line in results_response.text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        custom_id = row.get("custom_id", "")
        seen.add(custom_id)
        result = row.get("result", {}) or {}

        try:
            if result.get("type") != "succeeded":
                raise RuntimeError(f"Anthropic batch result type={result.get('type')}")
            message = result.get("message", {}) or {}
            parsed = parse_json_object(extract_anthropic_message_text(message))
            usage = message.get("usage", {}) or {}

            if custom_id == f"{date}-fable5-track-a":
                save_json(
                    RAW_SCANS / f"{date}-fable5-track-a.json",
                    decorate_track_a(parsed, model_label="fable5_track_a", snap_id=snap_id, usage=usage),
                )
                track_a_saved = True
            elif "-fable5-track-b-" in custom_id:
                chunk_id = custom_id.rsplit("-", 1)[-1]
                chunk = chunks_by_id.get(chunk_id)
                if chunk is None:
                    raise RuntimeError(f"Unknown Track B chunk id {chunk_id}")
                normalized, chunk_warnings = normalize_blind_forecasts(
                    parsed.get("forecasts", []), chunk, source=chunk_id
                )
                all_forecasts.extend(normalized)
                warnings.extend(chunk_warnings)
                usages.append({"chunk_id": chunk_id, "usage": usage})
        except Exception as exc:
            log.exception("Fable result gap %s: %s", custom_id, exc)
            if custom_id == f"{date}-fable5-track-a":
                save_json(
                    RAW_SCANS / f"{date}-fable5-track-a.json",
                    graceful_gap("fable5_track_a", "A", snap_id, exc),
                )
                track_a_saved = True
            else:
                partial_failures.append({"custom_id": custom_id, "error": str(exc)})

    expected = set(state.get("expected_custom_ids", []))
    for missing in sorted(expected - seen):
        if missing == f"{date}-fable5-track-a":
            if not track_a_saved:
                save_json(
                    RAW_SCANS / f"{date}-fable5-track-a.json",
                    graceful_gap("fable5_track_a", "A", snap_id, RuntimeError("Missing Track A result row")),
                )
        else:
            partial_failures.append({"custom_id": missing, "error": "missing_result_row"})

    if all_forecasts:
        output_b = decorate_track_b(
            all_forecasts,
            model_label="fable5_track_b",
            snap_id=snap_id,
            usage=usages,
            canonical_markets=markets,
            warnings=warnings,
            partial_failures=partial_failures,
        )
    else:
        output_b = graceful_gap(
            "fable5_track_b",
            "B",
            snap_id,
            RuntimeError(f"No successful Track B chunks; failures={partial_failures}"),
        )
    save_json(RAW_SCANS / f"{date}-fable5-track-b.json", output_b)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run pre-registered shadow model experiment")
    parser.add_argument("--date", default=today_str())
    parser.add_argument("--run-openai", action="store_true")
    parser.add_argument("--submit-fable-batch", action="store_true")
    parser.add_argument("--poll-fable-batch", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    ensure_dirs()
    did_work = False

    if args.run_openai or args.all:
        run_openai(args.date)
        did_work = True

    if args.submit_fable_batch or args.all:
        try:
            submit_fable_batch(args.date)
        except Exception as exc:
            log.exception("Fable batch submission gap: %s", exc)
        did_work = True

    if args.poll_fable_batch:
        try:
            poll_fable_batch(args.date)
        except Exception as exc:
            log.exception("Fable batch poll gap: %s", exc)
        did_work = True

    if not did_work:
        parser.error("Choose --run-openai, --submit-fable-batch, --poll-fable-batch, or --all")


if __name__ == "__main__":
    main()
