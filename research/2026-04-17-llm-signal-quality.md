# LLM Scanner Signal Quality

**Date:** 2026-04-17
**Author:** Ari
**Status:** Study A retrospective (runs 2026-04-17). Study B forward-collection, analysis target ~2026-06-01.
**Script:** `tools/llm_signal_quality.py`
**Data:** `raw/scans/*.json`, `raw/resolved/*.json`, `raw/resolved.bak.*/*.json`

## Overview

Two questions about the Kalshi scanner's LLM predictions, sharing one data source and one script:

- Study A (retrospective): Is the confidence label ("high"/"medium"/"low") informative? Do high-confidence predictions have better Brier than medium?
- Study B (forward): When 2+ models agree on direction for the same ticker on the same scan date, is Brier better than on solo picks?

## Study A — Confidence Tier Calibration

### H0
Confidence label is noise. Brier score on "high" confidence picks is statistically indistinguishable from Brier on "medium".

### H1
Confidence label is informative. Higher confidence means lower Brier (better-calibrated prediction).

### Scope
All settled predictions across all models (claude, gemini, gemini_shadow, grok), from scan start through analysis run date. Known contamination: Apr 11-16 label bug (Grok/Gemini-shadow mislabeled as claude) is fixed going forward but historical records in that window may still be wrong. Interpret pre-fix claude rows with caution.

### Metrics
Primary: Avg Brier by confidence tier per model.
Secondary: Brier edge vs market price baseline per tier.
Diagnostic: Sample sizes per tier-model cell.

### Kill lines (pre-committed)
- If high-tier Brier >= medium-tier Brier across all models: confidence label is uninformative or inverted. Flag for prompt revision.
- If any cell has n < 5: insufficient data, rerun at higher n, do not interpret.
- If high-tier Brier is 10%+ better than medium across 2+ models: real signal. Confidence label is usable for position sizing.

### Limitations at current n
Total settled predictions are ~30-50 across all models. Per-tier-per-model cells may be n=3-10. Any finding is provisional. Re-run scheduled for 2026-05-15.

## Study B — Model Agreement as Signal

### H0
Model agreement on direction is noise. When 2+ models pick the same ticker-direction-date, avg Brier is statistically indistinguishable from solo-model picks.

### H1
Model agreement is informative. Multi-model agreement produces lower Brier than solo picks.

### Scope
All settled predictions where multiple distinct models picked the same (scan_date, ticker, direction). This study does NOT examine ticker-only agreement with opposing directions - that is "disagreement as uncertainty signal", filed as future research.

### Metrics
Primary: Avg Brier on multi-model agreed picks vs solo picks.
Secondary: Brier edge vs market on agreed picks.

### Kill lines (pre-committed)
- If n(agreed & settled) < 30 at analysis date: insufficient sample, extend collection, do not interpret.
- If Brier(agreed) >= Brier(solo) at n >= 30: model agreement is noise. Do not use as a filter.
- If Brier(agreed) is 10%+ better than Brier(solo) at n >= 30: use as a ranking boost in future scanner revisions. Research only, no deployment today.

### Current readiness (2026-04-17)
- 85 total ticker-days of predictions
- 13 ticker-days with 2+ model overlap
- 1 ticker-day with 3-model agreement
- Only a fraction are settled
NOT READY. Forward-collect through ~2026-06-01.

## Open questions (post-analysis only)

- Does confidence calibration vary by category? (macro vs sports vs crypto)
- Does model agreement quality vary by category?
- Is "agreement but wrong" concentrated in specific topic areas where LLM training data is weakest?

Do not pre-investigate.

## Follow-up schedule

- 2026-05-15: Rerun Study A alongside lag study. Note changes.
- 2026-06-01: Run Study B if n(agreed, settled) >= 30. Compare to kill lines. Append findings as "Update 2026-06-01" section in this memo.

## Study A findings (run 2026-04-17, n=49 settled across tiers)

Results table:

| model | conf | n | brier | mkt_brier | edge |
|---|---|---|---|---|---|
| claude | high | 11 | 0.0698 | 0.1149 | +0.0451 |
| claude | medium | 18 | 0.2328 | 0.2472 | +0.0145 |
| gemini | high | 1 | 0.0900 | 0.0272 | -0.0628 |
| gemini | medium | 16 | 0.3214 | 0.1811 | -0.1404 |
| gemini_shadow | high | 2 | 0.3193 | 0.2367 | -0.0826 |
| gemini_shadow | medium | 1 | 0.0900 | 0.0462 | -0.0438 |

Kill-line evaluation:

- "High-tier Brier 10%+ better than medium across 2+ models": NOT MET. Only claude shows the pattern (high 0.070 vs medium 0.233). Gemini high n=1 unusable. Gemini_shadow noise (n=2, n=1).
- "n < 5 do not interpret": TRIGGERED for gemini high, gemini_shadow high, gemini_shadow medium. Those rows excluded.

Provisional read:

- Claude confidence label appears informative - high-tier Brier dramatically better than medium-tier. Contaminated by Apr 11-16 label bug (some "claude" rows are actually mislabeled Grok/Gemini-shadow). Cannot cleanly attribute to Claude-the-model.
- Gemini losing to market on medium tier at n=16, edge -0.140. Large enough it's not noise. Flag for prompt review.
- Gemini_shadow has insufficient settled predictions (n=3 total across tiers). Needs more time.

No config changes. Rerun 2026-05-15, expect roughly double the settled sample. If claude-column finding persists post-label-fix, pattern is real. If gemini underperformance persists, revisit prompt.

## Study B readiness check (2026-04-17)

- Settled solo picks: 20
- Settled multi-model agreements: 5
- Target: >= 30 agreed+settled
- NOT READY. Need 25 more agreed+settled.

Re-check 2026-06-01.
