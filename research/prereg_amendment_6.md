# Preregistration Amendment 6 — Estimation Milestones, Effective-Sample Disclosure, Benchmark Lock, and Tradability Reporting

- **Experiment:** Forward test of frontier AI probability forecasts against contemporaneous Kalshi market prices
- **Repository:** `ewmf4033/kalshi-scanner`
- **File:** `research/prereg_amendment_6.md`
- **Drafted:** 2026-07-17 (UTC)
- **Status:** Pre-outcome under the Amendment 4 boundary; not pre-data
- **Effective:** Upon commit to the repository default branch. This amendment must be committed before any experiment outcome is intentionally inspected, scored, summarized, or used for analysis. Mechanical capture-only resolution may occur under §4.2a.

## 1. Pre-outcome declaration

1.1. Forward forecasts already exist for July 14, 15, and 16, 2026.
1.2. Some contracts forecast on those dates may have publicly settled.
1.3. As of this amendment's drafting, the resolver has never run, the scorecard remains an empty skeleton, and no experiment outcome has been intentionally inspected, scored, summarized, or used to guide this amendment.
1.4. Under Amendment 4's stated boundary, this is a pre-outcome amendment. It is not a pre-data amendment: the July 14–16 forecasts themselves exist and have been observed operationally.
1.5. This amendment does not alter, delete, rewrite, backfill, or reinterpret any previously stored forecast, snapshot, hash, or record.

## 2. Counting views and effective sample size

2.1. Every formal report must state three counts separately:
- **Forecast-instance n:** each stored model probability emitted for a specific ticker from a specific daily snapshot.
- **Unique-contract n:** distinct tickers within the scoring frame.
- **Independent underlying event-cluster n:** distinct underlying resolution events or shared outcome drivers within the scoring frame.

2.2. Repeated forecasts of the same ticker across different snapshot dates remain legitimate, retained, timestamped forecast instances. They must not be treated as independent observations for inference; all instances of a ticker are assigned to that ticker's underlying event cluster.

2.3. Every formal report must disclose the number of contracts and forecast instances contributed by each major event cluster, and must record the rule used to assign contracts to clusters.

2.4. All reported confidence intervals and uncertainty estimates must account for clustering at the event or outcome-driver level. Raw settled-contract n must never be described as equivalent to independent event-cluster n, and no model receives additional evidentiary weight because one underlying event generated multiple related contracts. This extends, and does not replace, Amendment 4's correlation rule.

## 3. Estimation milestones replace verdict gates

3.1. Amendment 4's rule that "at n=100 settled full-coverage predictions, a non-positive full-coverage Brier Skill Score fails the Track B forecasting claim," and any equivalent promote/kill reading of the n=50 checkpoint, are superseded as provided in §12.

3.2. The n=50 and n=100 settled full-coverage prediction counts are reporting milestones only. The n=100 milestone retains its calendar function for the Primary 2 insufficiency clause (§8.4), which remains controlling.

3.3. At each milestone, for Primary 1 and for each scoring frame, the report must include: the three counting views of §2.1; the mean paired model-minus-market Brier difference across the frame; the median paired Brier difference; the Brier Skill Score, reported descriptively; two-sided 95% cluster-bootstrap confidence intervals for the mean paired difference and for the BSS, resampling event clusters with replacement using at least 10,000 resamples, with the random seed recorded; and per-cluster contributions per §2.3.

3.4. If log loss is reported, model and market probabilities are clamped to [0.01, 0.99] before scoring. This clamp is locked here.

3.5. No success or failure verdict may be declared solely because a BSS point estimate is above or below zero. Milestone reports must use estimation language (effect sizes and intervals); "pass," "fail," "promote," and "kill" language must not be applied to Primary 1 at any milestone.

3.6. Scoring frames remain separate. The full-coverage frame and the selected top-7 frame keep separate settled-prediction clocks. A positive selected top-7 result cannot rescue a full-coverage shortfall, and a positive full-coverage result does not establish that top-7 opportunity selection is profitable or superior. These Amendment 4 frame-separation clauses are preserved unchanged.

## 4. Power and minimum-detectable-effect governance

4.1. No sample-size figure, power figure, or effect-size figure from any informal audit, external review, or conversational analysis — including AI-assistant simulations — is adopted by this amendment.

4.2. Before any human or model inspects experiment outcomes for evaluative purposes, and before any scorecard, Brier score, Brier difference, BSS, confidence interval, P&L result, model comparison, or inferential report is generated, the following must be committed to the repository and reviewed: reproducible power-analysis code with a recorded random seed; fully documented simulation assumptions covering at minimum the market's probability-error distribution, the correlation between model and market errors, within-cluster outcome dependence, the distribution of contracts per event cluster, market-mix drift over time, and settlement censoring; a sensitivity analysis spanning a reasonable grid of those assumptions; a locked minimum detectable effect stated on both the paired Brier-difference scale and the BSS scale; and a locked final effective-event threshold stated in independent event-cluster n, with unique-contract n and forecast-instance n reported secondarily.

4.2a. Mechanical settlement capture is permitted before completion of §4.2 when necessary to preserve perishable or time-sensitive resolution records. Settlement capture is not outcome analysis. Captured outcomes must remain sealed from evaluative inspection: they may be written to immutable storage, but no human or model may read them for performance evaluation, no scorecard may be generated, and no Brier score, Brier difference, BSS, confidence interval, P&L, ranking, or conclusion may be computed until the §4.2 specification is committed. Operational metadata — that a capture ran, its timestamps, and record counts — may be logged; outcome values and directions must not be displayed, printed, or summarized.

4.2b. If the existing resolver combines settlement capture and scoring in one execution path, it must not be run in that combined mode before §4.2 is complete. A capture-only mode may be used or implemented prospectively, provided it writes settlement records without displaying, summarizing, scoring, ranking, or otherwise exposing experiment outcomes. Any such operational separation must preserve immutable timestamps and must not alter existing forecasts.

4.2c. Warning: anyone preparing or reviewing the power analysis must lock the simulation assumptions before examining experiment outcomes. The assumptions file should be committed separately before or simultaneously with the code that implements it.

4.3. The locked MDE and threshold must be recorded in a named, committed file. They may not be changed after any experiment outcome has been observed.

4.4. This amendment deliberately states no final event threshold and no expected calendar month, because none has yet been derived from reviewed code.

4.5. Any eventual confirmatory conclusion on Primary 1 must be evaluated against the locked threshold and the cluster-aware confidence interval, not against milestone optics.

## 5. Benchmark lock

5.1. The scoring benchmark is the contemporaneous YES bid/ask midpoint at snapshot time, as implemented in the live scanner:

```python
spread = yes_ask - yes_bid
mid_price = (yes_bid + yes_ask) / 2
implied_prob = mid_price

if spread >= 0.10:
    continue

if mid_price < 0.15 or mid_price > 0.85:
    continue
```

Consequently: the benchmark is not last-trade price; markets with spread ≥ 0.10 are excluded (spread strictly below 0.10 retained); markets with midpoint strictly below 0.15 or strictly above 0.85 are excluded (boundary values 0.15 and 0.85 retained).

5.2. The benchmark for every scored forecast is the `implied_prob` value stored in the same immutable snapshot from which the forecast was generated. No later-pulled, refreshed, or corrected quote may be substituted for scoring. The stored `yes_price` and `no_price` fields are retained but are not the benchmark.

5.3. `spread`, `volume`, `volume_24h`, and `open_interest` are retained as liquidity covariates and disclosed in formal reports.

5.4. Because the eligible universe is already restricted to midpoints within [0.15, 0.85], the scored universe and the contested band coincide. This observation changes no definition.

5.5. This section documents an existing implementation. No benchmark-method change is made.

## 6. Additional baselines

6.1. The following baselines are added prospectively: a constant 0.5 baseline; a category base-rate baseline; and the Kalshi midpoint baseline (identical to the §5 benchmark).

6.2. These baselines answer different questions and are complementary, not interchangeable: the 0.5 baseline tests whether a forecaster has any skill relative to no information; the category base-rate baseline tests whether it adds value over simple historical frequencies; the Kalshi midpoint baseline tests whether it adds value over the contemporaneous market. No baseline may be substituted for another after outcomes are observed, and no result may be reframed against a more favorable baseline post hoc.

6.3. The category base-rate method must be locked in a committed specification before any outcome inspection. It must be computed per category from an expanding window of resolutions strictly prior to the snapshot date of the forecast being scored, with shrinkage toward the overall resolved base rate and a stated minimum cell size. It must not use the outcomes being evaluated, nor any outcome resolved on or after the forecast's snapshot date. Until that specification is committed, the category base-rate baseline is not reported.

## 7. Top-7 tradability reporting

7.1. Top-7 reporting must state separately: gross hypothetical P&L computed at snapshot midpoints; executable-side hypothetical P&L, with YES positions priced at `yes_ask` and NO positions priced at 1 − `yes_bid`; the spread-crossing assumption (full spread crossing, as reflected in the executable-side prices above); Kalshi fees, computed under the fee schedule in effect on each hypothetical trade's snapshot date, with the schedule version and its retrieval date recorded; net hypothetical P&L after fees; and fill assumptions. Snapshots store no order-book depth; unless and until depth is stored, all selections are assumed filled in full at the executable-side price — an optimistic simplification that must be disclosed as a limitation — and no non-fill is modeled, which must likewise be disclosed.

7.2. The position-sizing convention (fixed contracts or fixed dollars per selection) must be stated in the committed pre-inspection specification and held constant across all reports.

7.3. Midpoint-based P&L must never be described as realizable trading profit. All P&L figures are hypothetical and shadow-only, and must be labeled as such.

7.4. The top-7 frame retains its own settled-prediction clock, per §3.6.

## 8. Track A interpretation

8.1. Track A is principally a price-aware deviation and opportunity-selection test: whether a model that can see Kalshi prices can identify a small set of deviations worth selecting.

8.2. Echoing the market may be rational. Zero-trade abstention may be rational. Zero trades do not, by themselves, establish forecasting failure.

8.3. No Track A full-coverage probabilities may be invented, estimated, or backfilled retroactively. Primary 2 remains restricted to common ticker/snapshot pairs, and missing pairs remain missing and are never backfilled.

8.4. Amendment 4's Primary 2 insufficiency clause remains controlling in full: if fewer than 30 valid settled common ticker/snapshot pairs exist on the calendar date when Primary 1 reaches its n=100 settled full-coverage checkpoint — now the §3.2 reporting milestone — Primary 2 is declared inconclusive by insufficient data and reverts permanently to exploratory status; it may not be answered from a smaller pair set, and no partial-pair analysis may be presented as confirmatory.

## 9. Track B scope

9.1. Track B tests whether a no-search model's internal probability prior can outperform contemporaneous Kalshi midpoint probabilities. It does not test a browsing-enabled research agent using live news, and results must not be described as evidence about such an agent.

9.2. The following secondary, exploratory strata are added: time to resolution; and likely material dependence of the resolution on developments after the model's training cutoff. Bin definitions and the outcome-blind classification procedure for the second stratum must be locked in the committed pre-inspection specification.

9.3. These strata are not confirmatory primary questions and may not be promoted after outcomes are observed, per Amendment 4's multiplicity rule.

## 10. Preservation and no retrospective rewriting

10.1. All existing snapshots, snapshot hashes, model forecasts, model identifiers, prompts, thresholds, eligibility filters, logged gaps, timestamps, and batch records are preserved unchanged.

10.2. No backfilling, no deletion of unfavorable observations, no outcome-driven reclassification, and no favorable-subgroup promotion is permitted.

10.3. This amendment changes no model prompt, model identifier, threshold, or forecast-generation method.

10.4. Every prohibition in Amendment 4's amendment-window boundary remains in force.

## 11. No live execution change

11.1. All lanes remain shadow-only. This amendment changes no betting, order placement, position sizing, execution, or capital-allocation behavior.

## 12. Supersession and conflicts

12.1. This amendment supersedes Amendment 4 only with respect to: (a) the interpretation of the n=50 and n=100 settled-prediction counts as promote/kill verdict gates, including the rule that a non-positive full-coverage BSS at n=100 fails the Track B forecasting claim; and (b) the raw settled-contract count as the sole evidentiary clock. Raw forecast-instance and settled-contract counting are retained and reported; unique-contract and independent event-cluster reporting are added, and cluster-aware inference is controlling for evidentiary conclusions.

12.2. All other Amendment 4 provisions are expressly preserved, including: the definitions of Primary 1 and Primary 2; the Primary 2 insufficiency clause; the multiplicity rule; the frame-separation clauses; the correlation-disclosure rule (as extended by §2); the amendment-window boundary; and the shadow-only rule.

12.3. All provisions of the base preregistration and of Amendments 1–5 not expressly superseded remain controlling. Where a provision conflicts directly with this amendment, this amendment controls only to the extent of the conflict.
