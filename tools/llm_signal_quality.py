#!/usr/bin/env python3
"""
llm_signal_quality.py — Two-study analysis of Kalshi LLM predictions.

Study A (retrospective): Confidence tier calibration per model.
Study B (forward): Model agreement as signal, locked for 2026-06-01.

Usage:
    python3 tools/llm_signal_quality.py --study-a
    python3 tools/llm_signal_quality.py --study-b-check
    python3 tools/llm_signal_quality.py --study-b
"""

import json, argparse, statistics
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).resolve().parent.parent
RAW_RESOLVED = BASE / "raw" / "resolved"
OUT_DIR = BASE / "research" / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_all_resolutions():
    rows = []
    sources = list(RAW_RESOLVED.glob("*.json"))
    for bak in (BASE / "raw").glob("resolved.bak.*"):
        sources.extend(bak.glob("*.json"))
    for f in sources:
        try:
            d = json.loads(f.read_text())
            for r in d.get("resolutions", []):
                rows.append(r)
        except Exception as e:
            print(f"skip {f}: {e}")
    return rows


def study_a():
    """Confidence tier calibration by model."""
    rows = load_all_resolutions()
    groups = defaultdict(list)
    market_groups = defaultdict(list)
    for r in rows:
        model = r.get("model")
        conf = r.get("confidence")
        brier = r.get("brier")
        market_brier = r.get("market_brier")
        if model and conf and brier is not None:
            groups[(model, conf)].append(brier)
            if market_brier is not None:
                market_groups[(model, conf)].append(market_brier)

    print("\n=== STUDY A: Confidence Tier Calibration ===\n")
    print(f"{'model':<20} {'conf':<8} {'n':>4} {'brier':>8} {'mkt_brier':>10} {'edge':>8}")
    summary = {}
    for (model, conf), vals in sorted(groups.items()):
        n = len(vals)
        b = statistics.mean(vals)
        mb_vals = market_groups.get((model, conf), [])
        mb = statistics.mean(mb_vals) if mb_vals else None
        edge = (mb - b) if mb is not None else None
        edge_str = f"{edge:+.4f}" if edge is not None else "-"
        mb_str = f"{mb:.4f}" if mb is not None else "-"
        print(f"{model:<20} {conf:<8} {n:>4} {b:>8.4f} {mb_str:>10} {edge_str:>8}")
        summary[f"{model}__{conf}"] = {
            "n": n,
            "avg_brier": round(b, 4),
            "avg_market_brier": round(mb, 4) if mb is not None else None,
            "brier_edge": round(edge, 4) if edge is not None else None,
        }

    (OUT_DIR / "study_a_confidence.json").write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {OUT_DIR}/study_a_confidence.json")


def study_b_check():
    """Readiness check for agreement analysis."""
    resolutions = load_all_resolutions()
    groups = defaultdict(set)
    for r in resolutions:
        k = (r.get("scan_date"), r.get("ticker"), r.get("direction"))
        if r.get("model"):
            groups[k].add(r.get("model"))

    agreed_settled = sum(1 for models in groups.values() if len(models) >= 2)
    solo_settled = sum(1 for models in groups.values() if len(models) == 1)

    print(f"\n=== STUDY B: Readiness check ===\n")
    print(f"Settled solo picks: {solo_settled}")
    print(f"Settled multi-model agreements: {agreed_settled}")
    print(f"Target: >= 30 agreed+settled")
    if agreed_settled >= 30:
        print("READY for Study B. Run with --study-b.")
    else:
        print(f"NOT READY. Need {30 - agreed_settled} more agreed+settled.")


def study_b():
    """Model agreement Brier comparison."""
    resolutions = load_all_resolutions()
    groups = defaultdict(list)
    for r in resolutions:
        k = (r.get("scan_date"), r.get("ticker"), r.get("direction"))
        groups[k].append(r)

    agreed_brier = []
    solo_brier = []
    for k, recs in groups.items():
        models_in_group = {r.get("model") for r in recs if r.get("model")}
        for r in recs:
            b = r.get("brier")
            if b is None:
                continue
            if len(models_in_group) >= 2:
                agreed_brier.append(b)
            else:
                solo_brier.append(b)

    print(f"\n=== STUDY B: Agreement vs Solo ===\n")
    if agreed_brier:
        print(f"Agreed picks: n={len(agreed_brier)} avg_brier={statistics.mean(agreed_brier):.4f}")
    else:
        print("Agreed picks: n=0")
    if solo_brier:
        print(f"Solo picks:   n={len(solo_brier)} avg_brier={statistics.mean(solo_brier):.4f}")
    else:
        print("Solo picks: n=0")

    summary = {
        "n_agreed": len(agreed_brier),
        "avg_brier_agreed": round(statistics.mean(agreed_brier), 4) if agreed_brier else None,
        "n_solo": len(solo_brier),
        "avg_brier_solo": round(statistics.mean(solo_brier), 4) if solo_brier else None,
    }
    (OUT_DIR / "study_b_agreement.json").write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {OUT_DIR}/study_b_agreement.json")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--study-a", action="store_true")
    p.add_argument("--study-b-check", action="store_true")
    p.add_argument("--study-b", action="store_true")
    args = p.parse_args()
    if args.study_a:
        study_a()
    elif args.study_b_check:
        study_b_check()
    elif args.study_b:
        study_b()
    else:
        p.print_help()


if __name__ == "__main__":
    main()
