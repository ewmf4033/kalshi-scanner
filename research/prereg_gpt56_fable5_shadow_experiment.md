# GPT-5.6 / Fable 5 Shadow-Lane Experiment — Pre-Registration

**Date locked:** 2026-07-12  
**Repository:** `ewmf4033/kalshi-scanner`  
**Status:** Locked before any GPT-5.6 or Fable 5 API integration changes.  
**Execution mode:** Shadow only. No live betting, no sizing changes, no execution changes.

## 1. Purpose

This experiment asks two separate questions:

1. **Model question:** Does GPT-5.6 outperform the existing Sonnet 4.6 lane under the current v1 methodology?
2. **Methodology question:** Does removing Kalshi price exposure before probability estimation improve forecasting quality?

The experiment must keep these questions separate so a model change and a methodology change are not conflated.

## 2. Historical reference set

The canonical historical reference is the **clean post-fix n=14 baseline** previously identified for the existing v1 scanner.

The April 11-16, 2026 rows affected by the known model-label bug are **permanently excluded from all benchmark comparisons, pooled historical summaries, promotion decisions, and kill-line decisions** for this experiment.

The larger retrospective n=49 result is not the canonical baseline because it contains known label contamination.

## 3. Verified anchoring condition

The existing v1 scanner exposes market-price information before the model produces its probability estimate. The prompt includes fields such as:

- `yes_bid`
- `yes_ask`
- last trade / `yes_price`
- `implied_prob`
- `spread`
- `mid_price`
- volume and open interest

The v1 prompt also instructs the model to compare `prob_midpoint` against `implied_prob` to determine direction.

Therefore, a blind-price Track B is a real methodology change, not a hypothetical one.

## 4. Experimental tracks

### Track A — Existing anchored methodology

Track A preserves the current v1 prompt path and market-price visibility.

For each supported lane:

- the model receives the existing enriched market payload, including Kalshi price fields;
- the model estimates probabilities;
- the model self-selects trades under the existing prompt rules;
- existing category edge thresholds remain unchanged;
- the existing max-7-trades cap remains unchanged;
- no downstream synthesis result is used for raw lane scoring.

Primary Track A comparison:

- Sonnet 4.6 Track A
- GPT-5.6 Track A

Optional additional Track A lane:

- Fable 5 Track A, subject to cost/access availability.

Existing Grok and Gemini-shadow continuity may remain unchanged but they are not required to receive new Track B clones.

### Track B — Blind probability estimation with mechanical post-hoc selection

Track B must not expose Kalshi market-price fields before probability output is locked.

The blind model must output probability estimates without seeing:

- `yes_bid`
- `yes_ask`
- `yes_price`
- `implied_prob`
- `spread`
- `mid_price`
- any equivalent market-price-derived field

After the model's probabilities are locked, code — not the model — performs deterministic post-hoc selection against the canonical market snapshot.

For each forecasted market:

1. retrieve the canonical snapshot's `implied_prob`;
2. compute absolute edge as `abs(prob_midpoint - implied_prob)`;
3. determine direction mechanically:
   - `prob_midpoint > implied_prob` => YES
   - `prob_midpoint < implied_prob` => NO
4. apply the same category thresholds used by v1:
   - macro: 8%
   - weather: 5%
   - politics: 10%
   - crypto: 12%
   - tech: 10%
   - sports: 8%
   - other: 10%
5. rank surviving opportunities deterministically by descending absolute edge;
6. retain at most 7 selections.

Known limitation: Track A allows model discretion in both forecasting and self-selection, while Track B separates forecasting from deterministic code-based selection. This residual difference is acknowledged in advance and must not be hidden or reinterpreted later.

## 5. Canonical market snapshot rule

Every lane in a scan must use one immutable canonical market snapshot.

Requirements:

- one snapshot is saved before model calls;
- all lane prompts are derived from that exact snapshot;
- all later edge calculations use that same snapshot;
- no lane may refresh Kalshi prices after another lane has already forecast;
- every stored lane result must include a `snapshot_id` or content hash linking it to the exact snapshot used.

"Approximately the same time" is insufficient. The snapshot must be identical.

## 6. Raw-lane scoring only

The Haiku synthesizer is excluded from this experiment.

Rules:

- each model lane is scored raw;
- Haiku may continue operating downstream for legacy continuity if desired;
- Haiku output does not enter model-lane Brier, calibration, ROI, promotion, or kill-line decisions;
- no new GPT-5.6 or Fable 5 lane enters the synthesizer during this experiment unless a later, separately pre-registered study authorizes it.

## 7. Per-lane market baseline

Because lanes may select different markets, every lane's market baseline must be computed on that lane's own selected set only.

For lane L:

- `Model Brier_L` = average Brier across lane L's selected and settled predictions;
- `Market Brier_L` = average Brier of the canonical snapshot's implied probabilities for those exact same lane-L selections;
- `Brier Skill Score_L = 1 - (Model Brier_L / Market Brier_L)`.

A single global market Brier denominator across different lane opportunity sets is prohibited.

## 8. Metric hierarchy

Metrics are interpreted in this order:

1. **Primary:** Brier Skill Score versus the lane-specific Kalshi baseline.
2. **Secondary:** Calibration diagnostics, including probability buckets when bucket sample sizes are adequate.
3. **Tertiary:** Log loss.
4. **Quaternary:** Simulated ROI / theoretical P&L.

Win rate is diagnostic only and cannot be used as the primary verdict metric.

## 9. Sample-size checkpoints

Per lane:

- `n < 50 settled`: no formal verdict; do not declare a winner.
- `n = 50 settled`: first formal read; result remains provisional.
- `n = 100 settled`: primary promote/kill decision point.
- `n >= 200 settled`: category-level analysis may begin only where individual category cells themselves have sufficient sample.

A slow long-dated lane does not block evaluation of another lane that reaches the checkpoint first.

## 10. Promotion and kill lines

### At n = 50

Advance a lane to continued collection toward n=100 if:

- Brier Skill Score is positive; and
- no obvious catastrophic calibration failure is present.

If Brier Skill Score is less than or equal to zero at n=50:

- do not promote the lane;
- continue only under one of the pre-defined escape-hatch conditions below.

### Escape-hatch conditions

A lane with Brier Skill Score less than or equal to zero at n=50 may continue to n=100 only if at least one of these is true:

1. **Trivial cost condition:** projected API cost for that lane is less than $30 per month at the operating mode actually used; or
2. **Compelling paired-sample condition:** on common ticker/snapshot pairs shared with the reference lane, the paired analysis shows positive market-relative Brier skill for the candidate lane despite non-positive full-sample Brier Skill Score.

No other discretionary escape hatch may be invented after results are observed.

### At n = 100

Kill a lane if:

- Brier Skill Score remains less than or equal to zero.

A lane may be considered successful if:

- Brier Skill Score is positive;
- calibration is not catastrophically broken;
- the result is not obviously driven by one or two isolated outcomes;
- rolling-window diagnostics do not show the entire edge disappearing outside one short cluster.

No fixed 10% improvement requirement is imposed in advance.

## 11. Paired-sample analysis

Whenever two lanes forecast the same ticker from the same canonical snapshot, store a paired observation.

Paired analysis is secondary to each lane's full selected-set analysis but is required to help distinguish:

- forecasting quality;
- opportunity-selection differences;
- methodology effects.

Paired results must use identical outcomes and the same canonical snapshot baseline.

## 12. Resolution velocity and opportunity-set discipline

The existing scanner historically resolved enough predictions that n=50 may be reachable in weeks rather than months, but resolution speed varies by model and selected market horizon.

Do not widen the market universe, bias toward short-dated contracts, alter TOP_N, or change category eligibility merely to accelerate the experiment unless that change is separately documented and pre-registered before activation.

The long-dated-market problem, including unresolved Grok picks, must remain visible in reporting rather than being silently removed.

## 13. Fable 5 cost and reliability rule

Verified API pricing assumption for planning:

- standard API: $10 / million input tokens and $50 / million output tokens;
- Batch API: 50% lower, or $5 / million input tokens and $25 / million output tokens.

Because the scanner is a once-daily cron workload, Fable 5 should use batch processing where operationally practical.

Current rough planning estimate for a 100-market prompt is approximately 40K-60K input tokens with output capped at 8,192 tokens, implying an estimated batch-mode cost around $0.50-$0.80 per scan, or approximately $15-$25 per month at one scan per day. Actual usage must be measured and logged.

The Fable 5 lane must fail gracefully:

- model/API outage must not crash the scanner;
- the gap must be logged explicitly;
- missing forecasts must never be backfilled with hindsight;
- outage days remain missing observations.

## 14. API-call sequencing discipline

This pre-registration must be committed before any GPT-5.6 or Fable 5 API integration change is committed.

Required sequence:

1. verify current v1 prompt path;
2. verify resolution mechanics and velocity;
3. commit this pre-registration;
4. only then add model API calls and Track B mechanics;
5. keep code changes surgical and separable where practical.

## 15. Prohibited reinterpretations

After the first new forecast is produced, do not:

- redefine the canonical historical baseline;
- re-include the contaminated April 11-16 rows;
- change metric hierarchy because another metric looks better;
- replace lane-specific market baselines with a global denominator;
- change the n=50 or n=100 verdict checkpoints retroactively;
- invent a new escape hatch;
- blend Haiku synthesizer output into raw lane scoring;
- refresh market prices per lane and call them comparable;
- silently drop outage days;
- tune category thresholds after seeing experiment results without a new pre-registration.

## 16. Initial implementation scope

The minimum initial implementation should support:

- Sonnet 4.6 Track A, unchanged;
- GPT-5.6 Track A;
- Sonnet 4.6 Track B;
- GPT-5.6 Track B;
- one canonical immutable snapshot per scan;
- deterministic Track B selection in code;
- raw per-lane storage and scoring;
- lane-specific market Brier baselines;
- paired same-ticker/same-snapshot diagnostics;
- graceful model failure handling.

Fable 5 may be added as an additional Track A and/or Track B shadow lane once its exact API integration and actual cost are confirmed operationally.
