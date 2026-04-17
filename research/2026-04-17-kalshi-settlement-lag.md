# Kalshi Settlement Lag Study

**Date:** 2026-04-17
**Author:** Ari
**Status:** Initial findings, n=18, re-run planned ~2026-05-15
**Script:** `tools/lag_study.py`
**Data:** `raw/lag_study/ticker_lag.json`, `raw/lag_study/summary.json`

## Question

Does Kalshi settle markets fast enough after trading close + mandated
`settlement_timer_seconds` that capital lock-up is negligible, or is there
per-category structure that should inform Kelly sizing on the scanner?

## Method

Pulled every unique ticker from `raw/resolved/*.json` and resolved backups.
For each, hit `/markets/{ticker}` to get `close_time`, `settlement_ts`, and
`settlement_timer_seconds`. Computed:

    total_lag_sec  = settlement_ts - close_time
    excess_lag_sec = total_lag_sec - settlement_timer_seconds

`excess_lag_sec` is the real metric — it strips out the mandated waiting
period and measures only Kalshi's operational delay.

## Findings (n=18)

| Category | n | Median excess | P90 | Max |
|---|---|---|---|---|
| KXCPIYOY (YoY CPI) | 4 | 1.5 sec | 1.5s | 1.5s |
| KXBTC (crypto) | 1 | 1m 53s | — | — |
| KXGOLDD (commodities) | 2 | 21 min | 21 min | 21 min |
| KXCPI (monthly CPI) | 2 | 36 min | 36 min | 36 min |
| KXHIGHCHI (weather, Chicago) | 3 | 5h 03m | 5h 03m | 5h 03m |
| KXHIGHNY (weather, NY) | 3 | 6h 03m | 6h 04m | 6h 04m |
| KXHIGHMIA (weather, Miami) | 3 | 6h 04m | 10h 27m | 10h 27m |

Clear bimodal structure:
- **Automated-feed categories** (CPIYOY, crypto) settle in seconds
- **Manual-review categories** (weather, monthly CPI) lag hours

## Actions

1. **Weather markets flagged for reduced position sizing.**
   Pre-committed kill line ("P90 excess_lag >2 hours → reduce sizing")
   triggered. Weather P90 is 5–10 hours. Scale Kelly fraction on any
   KXHIGH* ticker by capital efficiency penalty until verified otherwise.

2. **Per-category lag table documented** for future scanner revisions.
   To be consumed by Kelly sizing logic whenever scanner starts executing
   trades (not in current observe-mode).

3. **No action on econ/commodity/crypto** — lag is negligible or tolerable
   for position sizes currently contemplated.

## Open Questions

- **Why does monthly CPI (36m) lag YoY CPI (1.5s) by 3+ orders of magnitude
  when both come from the same BLS release?** Hypothesis: YoY is a
  pre-computed published value, monthly requires derivation. Check
  `rules_primary` text on both tickers.
- **Is weather lag a weekend/holiday artifact?** Three weather samples per
  city is thin. Some may have closed on a Sunday and waited for Monday
  staffing. Rerun after 30 more settlements to confirm.
- **Does lag correlate with market volume?** Low-volume markets may deprioritize
  in Kalshi's settlement queue. Worth testing at higher n.

## Limitations

- n=18 is too small for confident tail estimates. Medians are informative,
  P99 values are single-sample noise.
- Category inference is ticker-prefix-based and may need refinement as new
  prefixes appear.
- Sample is all from April 2026 — no seasonal / operational-state coverage.

## Follow-up

- Re-run `python3 tools/lag_study.py` after ~2026-05-15, target n >= 50.
- If weather lag stays >2h at n=30+, consider whether weather markets
  belong in the scanner's target universe at all given capital cost.
- If CPI vs CPIYOY gap holds, document the split as a sizing input.

