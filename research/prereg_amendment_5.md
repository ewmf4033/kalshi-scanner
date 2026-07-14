# Pre-Registration Amendment 5
## Operational Lane Isolation, Exit Semantics, Gap-Recording Limitations, and Fable Track A Status Record

Locked after the provider-isolation code change was committed at `4545d40`, but before the first uncontested automated scan governed by that change.

This amendment documents an operational robustness change only. It does not alter model prompts, model identifiers, market snapshots, no-search rules, selection thresholds, probability calculations, scoring methods, metric hierarchy, checkpoint rules, or live execution behavior.

The code and this documentation landed in two separate commits rather than one. That is a procedural deviation from the preferred practice of landing operational changes and their documentation together. Both commits precede the first uncontested automated scan governed by the change.

## 1. Independent provider/lane execution

Previously, the combined daily command executed requested provider actions sequentially without independent exception isolation for OpenAI and Grok.

A failure or overwrite-protection exception in an earlier provider could abort the process before later requested providers were attempted.

For example, an OpenAI failure could prevent Grok and Fable submission from running even though those providers were operationally independent.

Effective with code commit `4545d40`, each requested provider action is isolated with its own exception handling.

The intended behavior is now:

- an OpenAI failure must not prevent Grok from running;
- an OpenAI failure must not prevent Fable submission from being attempted;
- a Grok failure must not prevent Fable submission from being attempted;
- Fable submission and polling preserve their existing independent graceful-failure behavior.

This change affects only whether later requested provider actions are still attempted after an earlier provider error.

It does not change what any model sees, how any model forecasts, what markets are eligible, how probabilities are normalized, how trades are selected, how outputs are scored, or how outcomes are resolved.

## 2. Process exit semantics

The runner now maintains a `lane_failures` counter.

Each caught provider-action exception increments that counter.

After all requested independent provider actions have been attempted:

- if no requested provider action failed, the process exits normally;
- if one or more requested provider actions failed, the process exits with status code 1.

This preserves both requirements:

1. later independent providers still receive an opportunity to run after an earlier provider failure; and
2. cron or monitoring can still distinguish a clean run from a run containing one or more provider gaps.

A nonzero process exit does not imply that all requested lanes failed.

Run interpretation must consult individual lane outputs, explicit gap artifacts where present, and cron logs.

## 3. Gap-recording asymmetry and lane-day coverage

There is a known gap-recording asymmetry.

Some provider failures may produce an explicit filesystem gap artifact.

However, certain OpenAI or Grok failures that occur before a final experiment output is written may leave no dedicated gap JSON file for that lane-day.

Therefore, absence of a successful output file must not automatically be interpreted as proof that the lane was never attempted.

For complete lane-day coverage reconstruction, formal operational review must consult:

- successful experiment output files;
- explicit gap artifacts where present;
- canonical snapshot records;
- batch metadata where applicable;
- `logs/cron.log` or equivalent preserved operational logs.

This amendment does not retroactively invent missing gap files or permit hindsight backfilling.

No missing forecast may be reconstructed after resolution.

The asymmetry is documented as an operational limitation and must remain visible in experiment reporting.

## 4. Fable Track A deterministic-truncation status record

The July 14, 2026 Fable Track A batch result contains an incomplete JSON object and fails parsing with:

`No complete JSON object found; possible truncation`

Repeated polling of the same completed Fable batch reproduces the same Track A parsing failure.

Therefore, for the July 14 batch specifically:

- the failure is deterministic with respect to the already-completed stored batch result;
- additional polling cannot convert that historical Track A result into a valid forecast;
- the July 14 Fable Track A observation remains a permanent logged gap;
- no hindsight backfill is permitted.

This does not prove that every future Fable Track A run must fail.

However, the existing single-call Track A design is recognized as structurally vulnerable to output truncation.

Any future change to Fable Track A token limits, chunking, prompt structure, parsing behavior, or other output-generation methodology must be documented and locked before the first successful forecast under the changed method, consistent with Amendment 4 Section 9.

## 5. No methodology change

This amendment and code commit `4545d40` make no changes to:

- canonical snapshot construction;
- snapshot IDs;
- model prompts;
- model identifiers;
- no-search enforcement;
- Track A price visibility;
- Track B price blindness;
- Track B whitelist fields;
- Track B chunk size;
- probability midpoint recomputation;
- category thresholds;
- deterministic post-hoc direction;
- maximum selected opportunities;
- Brier scoring;
- market baselines;
- metric hierarchy;
- confirmatory primary questions;
- multiplicity policy;
- contested-band definition;
- correlation disclosure rules;
- n=50 or n=100 checkpoints;
- promotion or kill lines;
- live betting, sizing, capital allocation, or execution.

The sole operational purpose is to prevent one provider failure from suppressing independent later provider attempts while preserving a nonzero exit status for monitoring.

## 6. No live execution change

All experiment lanes remain shadow-only.

This amendment changes no live betting, order placement, position sizing, capital allocation, or automated trading behavior.
