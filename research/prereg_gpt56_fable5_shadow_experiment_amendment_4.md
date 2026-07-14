# Pre-Registration Amendment 4
## Confirmatory Questions, Kill-Line Governance, Multiplicity, Correlation, Contested-Band Analysis, and Sonnet Remediation

Locked after the first forward GPT-5.6, Fable 5, and Grok 4.5 forecasts were generated, but before any July 14, 2026 experiment outcome was intentionally inspected or used for analysis.

This is therefore a pre-outcome amendment, not a pre-data amendment. The July 14 model forecasts themselves already exist and have been observed operationally.

This amendment does not alter, delete, rewrite, backfill, or reinterpret any previously stored forecast.

## 1. UTC dating clarification

The first valid forward experiment files are dated 2026-07-14 because the experiment ran after midnight UTC while the operator remained on July 13 local Pacific time.

The canonical July 14 snapshot and all July 14 lane outputs use the same snapshot ID.

No future-dated forecast claim is being made.

## 2. Sonnet implementation deviation and remediation

The original pre-registration specified Sonnet 4.6 Track A and Track B in the minimum implementation scope.

Those Sonnet lanes were not implemented before the first forward GPT-5.6, Fable 5, and Grok 4.5 experiment day.

This is an explicit protocol deviation.

The existing GPT-5.6, Fable 5, and Grok 4.5 forward forecasts remain valid within their prospectively locked lane methodologies, but no claim requiring a contemporaneous Sonnet control may be made from July 14 data.

**Sonnet model identifier is locked as of this amendment: `claude-sonnet-4-6`.**

Sonnet Track A and Track B lanes are added prospectively, effective the first scan after this amendment is committed. The locked identifier must be recorded verbatim in every resulting Sonnet experiment output. If the deployed lane code resolves to any identifier other than `claude-sonnet-4-6`, the lane must refuse to run rather than substitute a different model.

No Sonnet forecast may be backfilled for July 14 or any earlier date. The one-day (or greater) offset between Sonnet lane inception and the other lanes' inception is a documented fact of the record and must not be rewritten.

## 3. Confirmatory primary questions

Exactly two confirmatory primary questions are designated.

### Primary 1 — Forecasting edge

GPT-5.6 Track B full-coverage Brier Skill Score versus the contemporaneous Kalshi market baseline.

This is the primary test of whether GPT-5.6 forecasts resolved Kalshi contracts more accurately than the contemporaneous market across all valid stored price-blind forecasts.

### Primary 2 — Methodology effect

Within GPT-5.6, Track B versus Track A on common ticker/snapshot pairs.

This is the primary test of whether removing Kalshi price exposure before probability estimation improves forecasting quality within the same model family.

Only common ticker/snapshot observations may enter this paired comparison. Missing pairs remain missing and are never backfilled.

**Known data-generation constraint, acknowledged prospectively:** Track A emits probabilities only on its self-selected trades (maximum 7 per scan, with zero-trade abstention permitted and expected). Track B emits probabilities on all markets. Therefore Primary 2 pairs accumulate at between 0 and 7 per scan per model, and may accumulate slowly or not at all.

**Insufficiency clause:** If fewer than 30 valid settled common ticker/snapshot pairs exist on the calendar date when Primary 1 reaches its n=100 settled full-coverage checkpoint, Primary 2 is declared **inconclusive by insufficient data** and reverts permanently to exploratory status for this experiment. It may not be answered from whatever smaller set of pairs exists at that time, and no partial-pair analysis may be presented as a confirmatory result. A future pre-registration may redesign the methodology-effect test (for example, by requiring Track A lanes to emit full-coverage probabilities), but such a redesign applies only to data collected after that future lock.

## 4. Multiplicity policy

The two confirmatory primary questions above are the only cells that may independently support a strong confirmatory claim from this experiment.

All other lanes, frames, model comparisons, and slices are secondary or exploratory, including:

- GPT-5.6 selected top-7 Track B;
- all Fable 5 results;
- all Grok 4.5 results;
- all Sonnet results added prospectively under this amendment;
- cross-model leaderboards;
- category-level comparisons;
- best-performing-lane claims;
- any other unlisted subgroup or slice.

Secondary or exploratory findings may generate hypotheses for future pre-registered studies but cannot independently support the strong claim that this experiment established a general AI forecasting edge.

No additional confirmatory primary cell may be promoted after outcomes are observed.

## 5. Track B kill-line governance

Track B contains two distinct questions and two distinct settled-prediction clocks.

### Full-coverage Track B forecasting claim

For Track B forecasting claims, full-coverage Track B Brier Skill Score governs the n=50 and n=100 forecasting checkpoints.

At n=100 settled full-coverage predictions, a non-positive full-coverage Brier Skill Score fails the Track B forecasting claim, subject only to rules already prospectively locked before outcome analysis.

### Selected top-7 opportunity-selection claim

Selected top-7 Track B Brier Skill Score is evaluated separately on its own settled-prediction clock.

The selected top-7 frame asks whether the model's largest mechanically identified discrepancies versus Kalshi outperform on those selected opportunities.

A positive selected top-7 result cannot rescue a failed full-coverage forecasting claim.

A positive full-coverage result does not establish that top-7 opportunity selection is profitable or superior.

The two frames must never be pooled or substituted for one another.

Because full-coverage predictions accumulate at approximately 100 per scan per lane while selected top-7 predictions accumulate at a maximum of 7 per scan per lane, the two frames will reach their respective n=50 and n=100 checkpoints on materially different calendar dates. The checkpoint that arrives first governs only its own frame's claim.

## 6. Contested-band secondary analysis

A named secondary contested-band analysis is prospectively defined as follows:

Include settled full-coverage Track B forecasts whose canonical contemporaneous Kalshi implied probability was between 0.10 and 0.90 inclusive.

For this stratum report:

- n settled contracts;
- model Brier score;
- market Brier score;
- Brier Skill Score;
- log loss;
- calibration diagnostics when sample sizes permit.

This contested-band analysis is secondary.

It does not replace full-coverage Track B BSS, does not govern the primary Track B kill line, and cannot independently establish the experiment's primary forecasting-edge claim.

No additional probability band may be promoted to confirmatory status after outcomes are observed.

## 7. Correlation and effective sample size

The original operational checkpoint n remains the count of settled prediction contracts per applicable lane or scoring frame.

This preserves the original pre-registration.

However, raw settled-contract n must not be described as equivalent to independent event n.

Formal reporting must additionally disclose, where determinable:

- unique resolved contracts;
- unique underlying resolution events;
- correlation clusters or shared outcome drivers;
- the number of contracts contributed by each major cluster.

Examples include multiple contracts driven by the same CPI release, Federal Reserve decision path, hurricane season outcome, daily weather observation, or other common underlying event.

Confidence intervals or uncertainty estimates must account for clustering at an appropriate event or outcome-driver level when such intervals are reported.

No model receives extra evidentiary weight merely because the same underlying event generates multiple related contracts.

## 8. Full-coverage and top-7 interpretations remain separate

Full-coverage Track B asks:

"Across all valid price-blind forecasts, does the model forecast resolved Kalshi contracts more accurately than the contemporaneous Kalshi market?"

Selected top-7 Track B asks:

"When this model identifies its largest mechanically determined discrepancies versus Kalshi, does it outperform the market on those selected opportunities?"

Neither frame substitutes for the other.

## 9. Fable Track A failure handling

The July 14 Fable Track A truncation remains a logged missing observation.

It is not backfilled.

Any future change to Fable Track A token limits, chunking, prompt structure, parsing behavior, or other methodology that materially changes output generation must be separately documented and locked before the first successful forecast under the changed method.

## 10. No outcome-driven reinterpretation

After any July 14 experiment outcome is observed, do not:

- redefine the two confirmatory primary questions;
- promote a secondary or exploratory cell to confirmatory status;
- change which Track B frame governs the forecasting kill line;
- change the contested-band definition;
- add a favorable probability slice and treat it as pre-registered;
- redefine raw settled-contract n as independent event n;
- silently remove correlated contracts;
- backfill missing forecasts;
- rewrite the Sonnet one-day offset;
- answer Primary 2 from an insufficient pair set in violation of the Section 3 insufficiency clause;
- use best-of-many-lanes performance as standalone evidence of general forecasting edge.

## 11. No live execution change

This amendment changes no live betting, execution, position sizing, capital allocation, or automated trading behavior.

All lanes remain shadow-only.
