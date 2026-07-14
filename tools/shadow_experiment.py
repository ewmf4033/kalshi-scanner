#!/usr/bin/env python3
"""Pre-registered no-search GPT-5.6 / Fable 5 shadow experiment.

Fail-closed design:
- Must be launched through run_shadow_experiment.py, which sets SHADOW_NO_SEARCH_ENFORCED=1.
- Track A is price-visible but external-search instructions are explicitly removed with a drift assertion.
- Track B is price-blind, whitelist-only, chunked, and mechanically selected after forecasts lock.
- API payloads are audited to contain no tools/search/retrieval fields.
- All outputs are shadow-only and never enter Haiku or execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RAW_SNAPSHOTS = ROOT / "raw" / "snapshots"
RAW_SCANS = ROOT / "raw" / "scans"
RAW_BATCHES = ROOT / "raw" / "batches"
PROMPTS_DIR = ROOT / "tools" / "prompts"

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
ANTHROPIC_BATCHES_URL = "https://api.anthropic.com/v1/messages/batches"
BLIND_CHUNK_SIZE = 25

LEGACY_SEARCH_NEEDLE = (
    "- Use search to find grounding data: CME FedWatch, Cleveland Fed Nowcast, "
    "NOAA, BLS, polling aggregators, institutional research"
)
NO_SEARCH_REPLACEMENT = (
    "- Do not use external search, browsing, retrieval, tools, or external APIs. "
    "Forecast only from the supplied contract data and internal knowledge."
)

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


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_dirs() -> None:
    for directory in (RAW_SNAPSHOTS, RAW_SCANS, RAW_BATCHES):
        directory.mkdir(parents=True, exist_ok=True)


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt file missing: {path}")
    return path.read_text()


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


def build_track_a_prompt(markets: list[dict]) -> str:
    """Build price-visible Track A prompt with fail-loud no-search enforcement."""
    prompt = load_prompt("scanner.md")
    if LEGACY_SEARCH_NEEDLE not in prompt:
        raise RuntimeError(
            "Legacy search instruction not found — prompt drifted; refusing to run Track A"
        )
    prompt = prompt.replace(LEGACY_SEARCH_NEEDLE, NO_SEARCH_REPLACEMENT, 1)
    if LEGACY_SEARCH_NEEDLE in prompt:
        raise RuntimeError("Search instruction still present after replacement")
    prompt = prompt.replace("{{DATE}}", today_str())
    prompt = prompt.replace("{{SCAN_TIMESTAMP_UTC}}", now_iso())
    prompt = prompt.replace("{{INJECTED_KALSHI_API_JSON}}", json.dumps(markets, indent=2))
    prompt = re.sub(
        r"\{\{#if INJECTED_SPORTS_ODDS_JSON\}\}.*?\{\{/if\}\}",
        "",
        prompt,
        flags=re.DOTALL,
    )
    return prompt


def blind_payload(markets: list[dict]) -> list[dict]:
    """Whitelist-only payload: unknown/new Kalshi fields cannot leak by default."""
    return [
        {key: market.get(key, "") for key in BLIND_FIELD_WHITELIST}
        for market in markets
    ]


def chunk_markets(markets: list[dict], size: int = BLIND_CHUNK_SIZE) -> list[list[dict]]:
    return [markets[i : i + size] for i in range(0, len(markets), size)]


def build_blind_prompt(markets: list[dict], snap_id: str, chunk_id: str) -> str:
    template = load_prompt("scanner_blind.md")
    return (
        template.replace("{{DATE}}", today_str())
        .replace("{{SCAN_TIMESTAMP_UTC}}", now_iso())
        .replace("{{SNAPSHOT_ID}}", snap_id)
        .replace("{{CHUNK_ID}}", chunk_id)
        .replace("{{INJECTED_BLIND_MARKETS_JSON}}", json.dumps(blind_payload(markets), indent=2))
    )


def category_from_ticker(ticker: str) -> str:
    ticker = str(ticker or "").upper()
    for category, prefixes in CATEGORY_PREFIXES.items():
        if any(ticker.startswith(prefix) for prefix in prefixes):
            return category
    return "other"


def parse_json_object(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = "\n".join(
            line for line in text.splitlines() if not line.strip().startswith("```")
        ).strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0 or end <= 0:
        raise ValueError("No complete JSON object found; possible truncation")
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid/truncated JSON output: {exc}") from exc


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False))
    log.info("Saved %s", path)


def save_experiment_json(path: Path, data: dict) -> None:
    """Protect final experiment outputs from accidental overwrite."""
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except Exception as exc:
            raise RuntimeError(
                f"Refusing to overwrite unreadable existing experiment output: {path}"
            ) from exc

        existing_is_gap = existing.get("gap") is True
        new_is_gap = data.get("gap") is True
        allow_gap_retry = os.environ.get("SHADOW_ALLOW_GAP_RETRY") == "1"

        if not existing_is_gap:
            raise FileExistsError(
                f"Refusing to overwrite existing successful experiment output: {path}"
            )

        if new_is_gap:
            raise FileExistsError(
                f"Refusing to replace existing gap with another gap: {path}"
            )

        if not allow_gap_retry:
            raise FileExistsError(
                "Existing experiment output is a gap. "
                "To explicitly replace it with a successful retry, set "
                f"SHADOW_ALLOW_GAP_RETRY=1. Path: {path}"
            )

        log.warning("Explicitly replacing prior gap with successful retry: %s", path)

    save_json(path, data)


def assert_no_search_payload(provider: str, payload: dict) -> None:
    """Fail loud if request payload exposes search/tool/retrieval capabilities."""
    forbidden = {"tools", "tool_choice", "web_search", "search", "retrieval"}
    present = sorted(key for key in forbidden if key in payload)
    if present:
        raise RuntimeError(f"{provider} payload exposes forbidden search/tool fields: {present}")


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


def call_openai(prompt: str, model: str, max_output_tokens: int = 4096) -> tuple[dict, dict]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    payload = {
        "model": model,
        "input": prompt,
        "max_output_tokens": max_output_tokens,
    }
    assert_no_search_payload("OpenAI", payload)
    response = requests.post(
        OPENAI_RESPONSES_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=600,
    )
    response.raise_for_status()
    body = response.json()
    return parse_json_object(extract_openai_output_text(body)), body.get("usage", {}) or {}


def anthropic_headers() -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }


def anthropic_request_params(model: str, prompt: str, max_tokens: int = 8192) -> dict:
    params = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    assert_no_search_payload("Anthropic", params)
    return params


def normalize_blind_forecasts(
    forecasts: list[dict],
    canonical_markets: list[dict],
    *,
    source: str,
) -> tuple[list[dict], list[dict]]:
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


def mechanical_track_b_selection(forecasts: list[dict], canonical_markets: list[dict]) -> list[dict]:
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
    parsed.update({
        "model": model_label,
        "track": "A",
        "snapshot_id": snap_id,
        "api_usage": usage,
        "shadow_only": True,
        "external_search_enabled": False,
        "prompt_builder": "explicit_no_search_track_a_v2",
    })
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
        "external_search_enabled": False,
        "gap": True,
        "error": str(error),
        "trades": [],
        "no_trades_today": True,
    }


def run_openai(date: str) -> None:
    markets = load_snapshot(date)
    snap_id = snapshot_id(markets)
    model = os.environ.get("OPENAI_SHADOW_MODEL", "gpt-5.6")

    try:
        prompt_a = build_track_a_prompt(markets)
        parsed_a, usage_a = call_openai(prompt_a, model)
        output_a = decorate_track_a(parsed_a, model_label="gpt56_track_a", snap_id=snap_id, usage=usage_a)
    except Exception as exc:
        log.exception("GPT-5.6 Track A gap: %s", exc)
        output_a = graceful_gap("gpt56_track_a", "A", snap_id, exc)
    save_experiment_json(RAW_SCANS / f"{date}-gpt56-track-a.json", output_a)

    all_forecasts: list[dict] = []
    warnings: list[dict] = []
    partial_failures: list[dict] = []
    usages: list[dict] = []
    for index, chunk in enumerate(chunk_markets(markets), start=1):
        chunk_id = f"{date}-gpt56-track-b-{index:02d}"
        try:
            prompt_b = build_blind_prompt(chunk, snap_id, chunk_id)
            parsed, usage = call_openai(prompt_b, model)
            normalized, chunk_warnings = normalize_blind_forecasts(
                parsed.get("forecasts", []), markets, source=chunk_id
            )
            all_forecasts.extend(normalized)
            warnings.extend(chunk_warnings)
            usages.append(usage)
        except Exception as exc:
            log.exception("GPT-5.6 Track B chunk gap %s: %s", chunk_id, exc)
            partial_failures.append({"chunk_id": chunk_id, "error": str(exc)})

    if all_forecasts:
        output_b = decorate_track_b(
            all_forecasts,
            model_label="gpt56_track_b",
            snap_id=snap_id,
            usage=usages,
            canonical_markets=markets,
            warnings=warnings,
            partial_failures=partial_failures,
        )
    else:
        output_b = graceful_gap(
            "gpt56_track_b", "B", snap_id,
            RuntimeError(f"No successful Track B chunks; failures={partial_failures}"),
        )
    save_experiment_json(RAW_SCANS / f"{date}-gpt56-track-b.json", output_b)


def submit_fable_batch(date: str) -> None:
    markets = load_snapshot(date)
    snap_id = snapshot_id(markets)
    model = os.environ.get("FABLE_SHADOW_MODEL", "claude-fable-5")

    requests_payload: list[dict] = [
        {
            "custom_id": f"{date}-fable5-track-a",
            "params": anthropic_request_params(model, build_track_a_prompt(markets)),
        }
    ]
    for index, chunk in enumerate(chunk_markets(markets), start=1):
        chunk_id = f"{date}-fable5-track-b-{index:02d}"
        requests_payload.append({
            "custom_id": chunk_id,
            "params": anthropic_request_params(model, build_blind_prompt(chunk, snap_id, chunk_id)),
        })

    payload = {"requests": requests_payload}
    assert_no_search_payload("Anthropic batch root", payload)

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
    save_json(state_path, {
        "date": date,
        "snapshot_id": snap_id,
        "batch_id": body.get("id"),
        "processing_status": body.get("processing_status"),
        "submitted_at": now_iso(),
        "model": model,
        "request_count": len(requests_payload),
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
        raise RuntimeError(f"Fable batch state missing batch_id: {state_path}")

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
        return

    results_response = requests.get(
        f"{ANTHROPIC_BATCHES_URL}/{batch_id}/results",
        headers=anthropic_headers(),
        timeout=120,
    )
    results_response.raise_for_status()

    markets = load_snapshot(date)
    fable_a: dict | None = None
    fable_a_usage: dict = {}
    fable_a_failure: dict | None = None
    all_forecasts: list[dict] = []
    warnings: list[dict] = []
    track_b_failures: list[dict] = []
    usages: list[dict] = []

    for line in results_response.text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        custom_id = row.get("custom_id", "")
        result = row.get("result", {}) or {}
        try:
            if result.get("type") != "succeeded":
                raise RuntimeError(f"Anthropic batch result type={result.get('type')}")
            message = result.get("message", {}) or {}
            parsed = parse_json_object(extract_anthropic_message_text(message))
            usage = message.get("usage", {}) or {}
            if custom_id.endswith("track-a"):
                fable_a = parsed
                fable_a_usage = usage
            elif "track-b-" in custom_id:
                normalized, chunk_warnings = normalize_blind_forecasts(
                    parsed.get("forecasts", []), markets, source=custom_id
                )
                all_forecasts.extend(normalized)
                warnings.extend(chunk_warnings)
                usages.append(usage)
        except Exception as exc:
            log.exception("Fable result gap %s: %s", custom_id, exc)
            failure = {"custom_id": custom_id, "error": str(exc)}
            if custom_id.endswith("track-a"):
                fable_a_failure = failure
            else:
                track_b_failures.append(failure)

    if fable_a is not None:
        output_a = decorate_track_a(
            fable_a, model_label="fable5_track_a", snap_id=snap_id, usage=fable_a_usage
        )
    else:
        output_a = graceful_gap(
            "fable5_track_a", "A", snap_id,
            RuntimeError("Missing or failed Fable Track A result"),
        )
    save_experiment_json(RAW_SCANS / f"{date}-fable5-track-a.json", output_a)

    if all_forecasts:
        output_b = decorate_track_b(
            all_forecasts,
            model_label="fable5_track_b",
            snap_id=snap_id,
            usage=usages,
            canonical_markets=markets,
            warnings=warnings,
            partial_failures=track_b_failures,
        )
    else:
        output_b = graceful_gap(
            "fable5_track_b", "B", snap_id,
            RuntimeError(f"No successful Fable Track B chunks; failures={track_b_failures}"),
        )
    save_experiment_json(RAW_SCANS / f"{date}-fable5-track-b.json", output_b)


def self_test_failure_path() -> None:
    """Deliberately exercise truncation and arithmetic-recompute paths without API calls."""
    try:
        parse_json_object('{"forecasts": [')
    except ValueError:
        pass
    else:
        raise AssertionError("Truncated JSON did not fail as expected")

    sample_markets = [{
        "ticker": "KXCPI-TEST",
        "title": "Test",
        "subtitle": "",
        "close_time": "",
        "resolution_source": "",
        "implied_prob": 0.40,
        "yes_price": 0.40,
    }]
    normalized, warnings = normalize_blind_forecasts(
        [{"ticker": "KXCPI-TEST", "prob_range": [0.5, 0.7], "prob_midpoint": 0.99}],
        sample_markets,
        source="self-test",
    )
    if normalized[0]["prob_midpoint"] != 0.6:
        raise AssertionError("Midpoint recomputation failed")
    if not any(w.get("type") == "midpoint_mismatch_recomputed" for w in warnings):
        raise AssertionError("Midpoint mismatch warning missing")
    log.info("Failure-path self-test passed")


def main() -> None:
    if os.environ.get("SHADOW_NO_SEARCH_ENFORCED") != "1":
        raise SystemExit(
            "Refusing to run: launch via run_shadow_experiment.py so no-search enforcement is active"
        )

    parser = argparse.ArgumentParser(description="Run pre-registered no-search shadow experiment")
    parser.add_argument("--date", default=today_str())
    parser.add_argument("--run-openai", action="store_true")
    parser.add_argument("--submit-fable-batch", action="store_true")
    parser.add_argument("--poll-fable-batch", action="store_true")
    parser.add_argument("--self-test-failure-path", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    ensure_dirs()
    did_work = False
    if args.self_test_failure_path:
        self_test_failure_path()
        did_work = True
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
        parser.error(
            "Choose --run-openai, --submit-fable-batch, --poll-fable-batch, "
            "--self-test-failure-path, or --all"
        )


if __name__ == "__main__":
    main()
