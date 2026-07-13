#!/usr/bin/env python3
"""
Shadow-only GPT-5.6 / Fable 5 experiment runner.

This file is intentionally isolated from the legacy live scanner pipeline.
It reuses the canonical saved market snapshot, never changes execution,
and never enters the Haiku synthesizer.

Modes:
  python3 tools/shadow_experiment.py --run-openai
  python3 tools/shadow_experiment.py --submit-fable-batch
  python3 tools/shadow_experiment.py --poll-fable-batch
  python3 tools/shadow_experiment.py --all

Environment:
  OPENAI_API_KEY
  OPENAI_SHADOW_MODEL            default: gpt-5.6
  ANTHROPIC_API_KEY
  FABLE_SHADOW_MODEL             default: claude-fable-5

Outputs:
  raw/scans/YYYY-MM-DD-gpt56-track-a.json
  raw/scans/YYYY-MM-DD-gpt56-track-b.json
  raw/scans/YYYY-MM-DD-fable5-track-a.json
  raw/scans/YYYY-MM-DD-fable5-track-b.json
  raw/batches/YYYY-MM-DD-fable5.json

Important:
- Track A preserves the existing price-visible prompt.
- Track B removes price-derived fields before forecasting, then applies
  deterministic post-hoc selection against the exact same snapshot.
- Every stored output carries snapshot_id.
- Fable batch failures and outages are logged as gaps; never backfilled.
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

# Reuse legacy prompt builder / date helpers without changing live pipeline.
from tools.scanner import build_scanner_prompt, load_prompt, today_str

ROOT = Path(__file__).resolve().parent.parent
RAW_SNAPSHOTS = ROOT / "raw" / "snapshots"
RAW_SCANS = ROOT / "raw" / "scans"
RAW_BATCHES = ROOT / "raw" / "batches"

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
ANTHROPIC_BATCHES_URL = "https://api.anthropic.com/v1/messages/batches"

PRICE_DERIVED_FIELDS = {
    "yes_bid",
    "yes_ask",
    "yes_price",
    "no_price",
    "implied_prob",
    "spread",
    "mid_price",
}

EDGE_THRESHOLDS = {
    "macro": 0.08,
    "weather": 0.05,
    "politics": 0.10,
    "crypto": 0.12,
    "tech": 0.10,
    "sports": 0.08,
    "other": 0.10,
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
    for d in (RAW_SNAPSHOTS, RAW_SCANS, RAW_BATCHES):
        d.mkdir(parents=True, exist_ok=True)


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def snapshot_id(markets: list[dict]) -> str:
    return hashlib.sha256(canonical_json(markets).encode("utf-8")).hexdigest()


def load_snapshot(date: str) -> list[dict]:
    path = RAW_SNAPSHOTS / f"{date}-markets.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Canonical snapshot missing: {path}. Run the legacy scanner pull first."
        )
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError(f"Snapshot must be a JSON list: {path}")
    return data


def strip_price_fields(markets: list[dict]) -> list[dict]:
    """Remove all price-derived fields while preserving contract identity and rules."""
    return [
        {k: v for k, v in market.items() if k not in PRICE_DERIVED_FIELDS}
        for market in markets
    ]


def build_blind_prompt(markets: list[dict], snap_id: str) -> str:
    template = load_prompt("scanner_blind.md")
    return (
        template.replace("{{DATE}}", today_str())
        .replace("{{SCAN_TIMESTAMP_UTC}}", now_iso())
        .replace("{{SNAPSHOT_ID}}", snap_id)
        .replace(
            "{{INJECTED_BLIND_MARKETS_JSON}}",
            json.dumps(strip_price_fields(markets), indent=2),
        )
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
        raise ValueError("No JSON object found in model output")
    return json.loads(text[start:end])


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False))
    log.info("Saved %s", path)


def extract_openai_output_text(payload: dict) -> str:
    """Support Responses API output_text convenience field and nested output blocks."""
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


def call_openai(prompt: str, model: str) -> tuple[dict, dict]:
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
            "max_output_tokens": 8192,
        },
        timeout=600,
    )
    response.raise_for_status()
    payload = response.json()
    parsed = parse_json_object(extract_openai_output_text(payload))
    usage = payload.get("usage", {}) or {}
    return parsed, usage


def category_key(value: Any) -> str:
    raw = str(value or "other").strip().lower()
    return raw if raw in EDGE_THRESHOLDS else "other"


def mechanical_track_b_selection(
    blind_output: dict,
    canonical_markets: list[dict],
) -> list[dict]:
    """Apply v1 thresholds deterministically after blind forecasts are locked."""
    market_by_ticker = {m.get("ticker"): m for m in canonical_markets}
    selected: list[dict] = []

    for forecast in blind_output.get("forecasts", []) or []:
        ticker = forecast.get("ticker")
        market = market_by_ticker.get(ticker)
        if not market:
            continue

        prob_range = forecast.get("prob_range")
        if not isinstance(prob_range, list) or len(prob_range) != 2:
            continue
        try:
            midpoint = (float(prob_range[0]) + float(prob_range[1])) / 2.0
            implied = float(market["implied_prob"])
        except (KeyError, TypeError, ValueError):
            continue

        category = category_key(forecast.get("category") or market.get("category"))
        edge = abs(midpoint - implied)
        threshold = EDGE_THRESHOLDS[category]
        if edge < threshold:
            continue

        direction = "YES" if midpoint > implied else "NO"
        selected.append(
            {
                "market": forecast.get("market") or market.get("title", ""),
                "ticker": ticker,
                "direction": direction,
                "current_price": market.get("yes_price"),
                "implied_prob": implied,
                "prob_range": prob_range,
                "prob_midpoint": round(midpoint, 4),
                "edge_pct": round(edge * 100),
                "confidence": forecast.get("confidence", "medium"),
                "category": category,
                "grounding_source": forecast.get("grounding_source", ""),
                "reasoning_summary": forecast.get("reasoning_summary", ""),
            }
        )

    selected.sort(key=lambda x: x["edge_pct"], reverse=True)
    return selected[:7]


def decorate_track_a(parsed: dict, *, model_label: str, snap_id: str, usage: dict) -> dict:
    parsed = dict(parsed)
    parsed["model"] = model_label
    parsed["track"] = "A"
    parsed["snapshot_id"] = snap_id
    parsed["api_usage"] = usage
    parsed["shadow_only"] = True
    return parsed


def decorate_track_b(
    parsed: dict,
    *,
    model_label: str,
    snap_id: str,
    usage: dict,
    canonical_markets: list[dict],
) -> dict:
    selected = mechanical_track_b_selection(parsed, canonical_markets)
    return {
        "date": parsed.get("date", today_str()),
        "scan_timestamp": parsed.get("scan_timestamp", now_iso()),
        "model": model_label,
        "track": "B",
        "snapshot_id": snap_id,
        "markets_analyzed": parsed.get("markets_analyzed", len(parsed.get("forecasts", []))),
        "forecasts": parsed.get("forecasts", []),
        "trades": selected,
        "no_trades_today": len(selected) == 0,
        "api_usage": usage,
        "shadow_only": True,
        "selection_method": "deterministic_posthoc_v1_thresholds_max7",
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


def run_openai(date: str) -> None:
    markets = load_snapshot(date)
    snap_id = snapshot_id(markets)
    model = os.environ.get("OPENAI_SHADOW_MODEL", "gpt-5.6")

    # Track A: exact legacy price-visible prompt path.
    try:
        prompt_a = build_scanner_prompt(json.dumps(markets, indent=2))
        parsed_a, usage_a = call_openai(prompt_a, model)
        output_a = decorate_track_a(
            parsed_a, model_label="gpt56_track_a", snap_id=snap_id, usage=usage_a
        )
    except Exception as exc:
        log.exception("GPT-5.6 Track A gap: %s", exc)
        output_a = graceful_gap("gpt56_track_a", "A", snap_id, exc)
    save_json(RAW_SCANS / f"{date}-gpt56-track-a.json", output_a)

    # Track B: blind forecast first, deterministic selection second.
    try:
        prompt_b = build_blind_prompt(markets, snap_id)
        parsed_b, usage_b = call_openai(prompt_b, model)
        output_b = decorate_track_b(
            parsed_b,
            model_label="gpt56_track_b",
            snap_id=snap_id,
            usage=usage_b,
            canonical_markets=markets,
        )
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

    prompt_a = build_scanner_prompt(json.dumps(markets, indent=2))
    prompt_b = build_blind_prompt(markets, snap_id)

    payload = {
        "requests": [
            {
                "custom_id": f"{date}-fable5-track-a",
                "params": {
                    "model": model,
                    "max_tokens": 8192,
                    "messages": [{"role": "user", "content": prompt_a}],
                },
            },
            {
                "custom_id": f"{date}-fable5-track-b",
                "params": {
                    "model": model,
                    "max_tokens": 8192,
                    "messages": [{"role": "user", "content": prompt_b}],
                },
            },
        ]
    }

    state_path = RAW_BATCHES / f"{date}-fable5.json"
    if state_path.exists():
        existing = json.loads(state_path.read_text())
        if existing.get("batch_id"):
            log.info("Fable batch already submitted for %s: %s", date, existing["batch_id"])
            return

    response = requests.post(
        ANTHROPIC_BATCHES_URL,
        headers=anthropic_headers(),
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    body = response.json()
    state = {
        "date": date,
        "snapshot_id": snap_id,
        "batch_id": body.get("id"),
        "processing_status": body.get("processing_status"),
        "submitted_at": now_iso(),
        "model": model,
    }
    save_json(state_path, state)


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
        f"{ANTHROPIC_BATCHES_URL}/{batch_id}",
        headers=anthropic_headers(),
        timeout=60,
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
    seen: set[str] = set()
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

            if custom_id.endswith("track-a"):
                output = decorate_track_a(
                    parsed,
                    model_label="fable5_track_a",
                    snap_id=snap_id,
                    usage=usage,
                )
                save_json(RAW_SCANS / f"{date}-fable5-track-a.json", output)
            elif custom_id.endswith("track-b"):
                output = decorate_track_b(
                    parsed,
                    model_label="fable5_track_b",
                    snap_id=snap_id,
                    usage=usage,
                    canonical_markets=markets,
                )
                save_json(RAW_SCANS / f"{date}-fable5-track-b.json", output)
        except Exception as exc:
            track = "A" if custom_id.endswith("track-a") else "B"
            label = "fable5_track_a" if track == "A" else "fable5_track_b"
            log.exception("Fable %s gap: %s", track, exc)
            save_json(
                RAW_SCANS / f"{date}-fable5-track-{track.lower()}.json",
                graceful_gap(label, track, snap_id, exc),
            )

    expected = {f"{date}-fable5-track-a", f"{date}-fable5-track-b"}
    for missing in sorted(expected - seen):
        track = "A" if missing.endswith("track-a") else "B"
        label = "fable5_track_a" if track == "A" else "fable5_track_b"
        error = RuntimeError(f"Missing result row for {missing}")
        save_json(
            RAW_SCANS / f"{date}-fable5-track-{track.lower()}.json",
            graceful_gap(label, track, snap_id, error),
        )


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
            # Fable failures must never crash GPT or legacy scanner paths.
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
