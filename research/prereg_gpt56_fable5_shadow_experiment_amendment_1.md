# Shadow-Lane Experiment Pre-Registration — Amendment 1

**Date locked:** 2026-07-12  
**Status:** Locked before the first GPT-5.6, Fable 5, or new blind Track B forecast fires.

This amendment clarifies implementation constraints discovered during pre-launch audit. It does not change results because no new experiment forecast has yet been produced.

## 1. No-search rule

All new experiment lanes must run without external web search, browsing, retrieval, external tools, or API-assisted research in both Track A and Track B.

Reason: a search-enabled blind lane can encounter Kalshi, Polymarket, or media reports quoting prediction-market odds, which would destroy price blindness. Unequal tool access would also confound model quality with tool access.

The historical clean n=14 Sonnet 4.6 set remains the canonical historical reference, but it is not treated as a perfectly controlled contemporaneous no-search arm if its historical prompt/tool path had external search enabled. Contemporary model comparisons should use equal no-search conditions.

A future search-enabled variant requires a separate pre-registration.

## 2. Track B chunking rule

Track B must forecast every eligible market, but may do so in deterministic chunks of 25 markets per API call to avoid output truncation.

Requirements:

- all chunks derive from the same immutable canonical snapshot;
- chunk membership is deterministic by existing snapshot order;
- all successful chunk forecasts are reassembled before post-hoc selection;
- a malformed or truncated chunk is logged as a partial failure rather than crashing the scan;
- no failed chunk may be backfilled later with hindsight;
- the final lane result must list missing tickers and partial failures explicitly.

## 3. Blind payload whitelist

Track B payload construction must use a whitelist, not a blacklist.

Allowed fields only:

- ticker
- title
- subtitle
- close_time
- resolution_source

Any new Kalshi field is excluded by default unless a later audited change explicitly adds it.

## 4. Category ownership

Track B category is assigned deterministically by code from ticker/series prefix. The model does not output category.

## 5. Arithmetic ownership

Code recomputes `prob_midpoint` from `prob_range`. A model-supplied midpoint is never trusted. Any mismatch is logged as a validation warning rather than silently accepted.

## 6. Partial-failure rule

A chunk-level truncation, malformed JSON response, missing ticker, duplicate ticker, or provider outage must be recorded explicitly.

- partial success remains usable only with `partial=true`, missing tickers, and failure metadata stored;
- all-chunk failure becomes a full lane gap;
- no failure is silently converted into a zero-probability or skipped historical observation.

## 7. Experiment discipline

These implementation corrections are locked before the first new experiment forecast. After the first forecast fires, changing search access, chunk size, blind payload fields, category ownership, midpoint arithmetic, or partial-failure semantics requires a new pre-registration.