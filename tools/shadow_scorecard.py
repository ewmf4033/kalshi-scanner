#!/usr/bin/env python3
"""Score pre-registered GPT-5.6 / Fable 5 shadow lanes from resolution files."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
RAW_SCANS = ROOT / "raw" / "scans"
RAW_RESOLVED = ROOT / "raw" / "resolved"
OUT_DIR = ROOT / "research" / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)

EXPERIMENT_MODELS = {
    "gpt56_track_a",
    "gpt56_track_b",
    "fable5_track_a",
    "fable5_track_b",
}

CONTAMINATED_START = "2026-04-11"
CONTAMINATED_END = "2026-04-16"


def load_scan_metadata() -> dict[tuple[str, str, str], dict]:
    """Map (scan_date, ticker, model) to snapshot/track metadata."""
    out: dict[tuple[str, str, str], dict] = {}
    for path in sorted(RAW_SCANS.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        model = data.get("model")
        date = data.get("date") or path.stem[:10]
        if not model or not date:
            continue
        for trade in data.get("trades", []) or []:
            ticker = trade.get("ticker")
            if not ticker:
                continue
            out[(date, ticker, model)] = {
                "snapshot_id": data.get("snapshot_id"),
                "track": data.get("track"),
                "shadow_only": data.get("shadow_only", False),
                "partial": data.get("partial", False),
            }
    return out


def load_resolutions() -> list[dict]:
    rows: list[dict] = []
    seen: set[tuple] = set()
    for path in sorted(RAW_RESOLVED.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        for row in data.get("resolutions", []) or []:
            key = (
                row.get("ticker"),
                row.get("scan_date"),
                row.get("model"),
                row.get("outcome"),
            )
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def bss(model_brier: float, market_brier: float) -> float | None:
    if market_brier <= 0:
        return None
    return 1.0 - (model_brier / market_brier)


def checkpoint_status(n: int, skill: float | None) -> str:
    if n < 50:
        return "NO_FORMAL_VERDICT"
    if n < 100:
        return "ADVANCE_TO_100" if skill is not None and skill > 0 else "ESCAPE_HATCH_ONLY"
    return "SUCCESS_CANDIDATE" if skill is not None and skill > 0 else "KILL"


def summarize_lane(rows: list[dict]) -> dict:
    n = len(rows)
    avg_brier = mean(r["brier"] for r in rows) if rows else None
    avg_market = mean(r["market_brier"] for r in rows) if rows else None
    skill = bss(avg_brier, avg_market) if rows else None
    avg_logloss = mean(r["log_loss"] for r in rows) if rows else None
    avg_pnl = mean(r["theoretical_pnl"] for r in rows) if rows else None
    return {
        "n": n,
        "avg_brier": round(avg_brier, 6) if avg_brier is not None else None,
        "avg_market_brier_lane_specific": round(avg_market, 6) if avg_market is not None else None,
        "brier_skill_score": round(skill, 6) if skill is not None else None,
        "avg_log_loss": round(avg_logloss, 6) if avg_logloss is not None else None,
        "avg_theoretical_pnl": round(avg_pnl, 6) if avg_pnl is not None else None,
        "checkpoint_status": checkpoint_status(n, skill),
    }


def paired_diagnostics(rows: list[dict], scan_meta: dict) -> dict:
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in rows:
        meta = scan_meta.get((row.get("scan_date"), row.get("ticker"), row.get("model")), {})
        snap = meta.get("snapshot_id")
        if not snap:
            continue
        groups[(row.get("scan_date"), row.get("ticker"), snap)].append(row)

    pairs: dict[str, list[dict]] = defaultdict(list)
    for (scan_date, ticker, snap), recs in groups.items():
        models = sorted({r.get("model") for r in recs if r.get("model")})
        for i, left in enumerate(models):
            for right in models[i + 1 :]:
                lrow = next(r for r in recs if r.get("model") == left)
                rrow = next(r for r in recs if r.get("model") == right)
                pairs[f"{left}__vs__{right}"].append({
                    "scan_date": scan_date,
                    "ticker": ticker,
                    "snapshot_id": snap,
                    "left_brier": lrow.get("brier"),
                    "right_brier": rrow.get("brier"),
                    "market_brier": lrow.get("market_brier"),
                })

    summary = {}
    for name, vals in sorted(pairs.items()):
        summary[name] = {
            "n_common": len(vals),
            "left_avg_brier": round(mean(v["left_brier"] for v in vals), 6),
            "right_avg_brier": round(mean(v["right_brier"] for v in vals), 6),
            "avg_market_brier": round(mean(v["market_brier"] for v in vals), 6),
        }
    return summary


def main() -> None:
    scan_meta = load_scan_metadata()
    all_rows = load_resolutions()
    experiment_rows = [r for r in all_rows if r.get("model") in EXPERIMENT_MODELS]

    by_model: dict[str, list[dict]] = defaultdict(list)
    for row in experiment_rows:
        by_model[row["model"]].append(row)

    report = {
        "historical_reference": {
            "canonical_clean_n": 14,
            "contaminated_rows_permanently_excluded": {
                "start": CONTAMINATED_START,
                "end": CONTAMINATED_END,
            },
            "note": "Historical reference is not a perfectly controlled contemporary no-search arm if its historical tool path used search.",
        },
        "metric_hierarchy": [
            "lane_specific_brier_skill_score",
            "calibration_diagnostics",
            "log_loss",
            "simulated_roi_theoretical_pnl",
        ],
        "lanes": {
            model: summarize_lane(rows)
            for model, rows in sorted(by_model.items())
        },
        "paired_same_ticker_same_snapshot": paired_diagnostics(experiment_rows, scan_meta),
    }

    out_path = OUT_DIR / "shadow_experiment_scorecard.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
