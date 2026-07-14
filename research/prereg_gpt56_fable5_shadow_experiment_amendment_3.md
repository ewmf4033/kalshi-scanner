# Pre-Registration Amendment 3
## Prospective Grok Addition and Full-Coverage Track B Diagnostic

Locked before the first successful forward Grok forecast.

This amendment does not alter, replace, or retroactively reinterpret any previously collected GPT-5.6 or Fable 5 forecasts.

## 1. Prospective Grok lanes

Add two new shadow-only lanes:

- grok_track_a
- grok_track_b

Grok must use the same methodology as the corresponding existing lanes:

### Grok Track A
- Same immutable canonical daily Kalshi snapshot.
- Price-visible.
- No external search, browsing, retrieval, tools, or external APIs.
- Same Track A prompt methodology.
- Same maximum of 7 selected opportunities.
- Same scoring methodology.

### Grok Track B
- Same immutable canonical daily Kalshi snapshot.
- Price-blind.
- Same whitelist-only payload:
  - ticker
  - title
  - subtitle
  - close_time
  - resolution_source
- Same deterministic chunk size of 25.
- Same mechanical midpoint recomputation.
- Same category thresholds.
- Same deterministic post-hoc direction and selection.
- Same maximum of 7 selected opportunities.
- Same failure and partial-failure rules.

The exact Grok API model identifier must be locked before its first successful forward forecast and recorded in the resulting experiment output.

## 2. Same opportunity set

All Track B model families must forecast the same canonical set of eligible markets from the same snapshot ID for a given daily run.

No model-specific market substitution or hindsight replacement is permitted.

## 3. Original top-7 analysis remains unchanged

The original pre-registered top-7 Track B analysis remains intact.

For each Track B lane, the existing selected-trade metrics continue to answer:

"When this model identifies its largest mechanically determined discrepancies versus Kalshi, does it outperform the market on those selected opportunities?"

No prior top-7 result, threshold, checkpoint, or selection rule is changed.

## 4. New full-coverage Track B forecasting diagnostic

A separate full-coverage Track B diagnostic is added prospectively and may also score already-collected valid forward Track B forecasts where the full forecast set was saved contemporaneously.

For every valid Track B forecast with a corresponding canonical contemporaneous Kalshi implied probability and eventual binary resolution, calculate:

- Brier score
- lane-specific market Brier score
- Brier Skill Score
- log loss
- calibration diagnostics

This full-coverage diagnostic answers:

"Across all valid price-blind forecasts, not merely the selected top 7, does the model forecast resolved Kalshi events more accurately than the contemporaneous Kalshi market?"

## 5. Metric hierarchy

The expanded reporting hierarchy is:

1. Full-coverage Track B Brier Skill Score
2. Original selected top-7 Track B Brier Skill Score
3. Calibration diagnostics
4. Log loss
5. Simulated top-7 ROI / theoretical P&L
6. Track A as secondary applied evidence

The original experiment is not deleted or rewritten; this amendment adds a separate, explicitly labeled full-coverage diagnostic.

## 6. Missingness and failures

- Failed API calls do not count.
- Malformed or truncated chunks are recorded as failures.
- No hindsight backfill is allowed.
- Partial Track B runs remain explicitly marked partial.
- Full-coverage n includes only valid forecasts that were actually returned and stored before resolution.
- Missing forecasts are never imputed.

## 7. Historical exclusions remain unchanged

- The April 10, 2026 technical dry run remains permanently excluded from formal experiment scoring.
- Previously identified contaminated historical periods remain treated according to the original pre-registration and amendments.

## 8. No live execution change

This amendment changes no live trading, position sizing, capital allocation, or execution behavior.

All lanes remain shadow-only.
