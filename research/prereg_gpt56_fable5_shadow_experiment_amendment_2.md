# GPT-5.6 / Fable 5 Shadow Experiment — Amendment 2

**Locked:** 2026-07-12, before the first successful GPT-5.6, Fable 5, or new blind Track B forecast.

## Purpose

This amendment fixes the GPT-5.6 output-token cap before any successful experiment forecast has been recorded.

The first attempted GPT-5.6 historical dry run on snapshot `2026-04-10` did not produce a valid forecast. OpenAI rejected the Track A request with HTTP 429 before generation because the organization-level GPT-5.6 tokens-per-minute limit was 10,000 TPM while the request was counted as 13,278 requested tokens.

The exact diagnostic returned:

- HTTP status: `429`
- error code: `rate_limit_exceeded`
- error type: `tokens`
- TPM limit: `10000`
- requested tokens: `13278`

Earlier failed requests caused by `insufficient_quota` also produced no valid forecast and are excluded from the experiment sample.

## Locked implementation change

For GPT-5.6 only:

- Track A `max_output_tokens` is fixed at `4096`.
- Each Track B chunk `max_output_tokens` is fixed at `4096`.
- Track B chunk size remains fixed at 25 markets.
- No prompt content, search policy, payload whitelist, category ownership, midpoint arithmetic, selection threshold, maximum-seven rule, snapshot semantics, scoring rule, or failure-handling rule changes.
- Fable 5 / Anthropic token limits are unchanged by this amendment.

## Rationale

The prior GPT-5.6 default of 8,192 output tokens caused the full Track A request to exceed the current 10,000 TPM request ceiling. Reducing the GPT-5.6 output cap to 4,096 is an infrastructure compatibility fix made before the first successful forecast, not a response to model performance.

Based on the rejected request, lowering the output cap by 4,096 tokens reduces the same Track A request from approximately 13,278 requested tokens to approximately 9,182 requested tokens, below the observed 10,000 TPM ceiling.

## Data-integrity treatment

- No failed 429 request is a valid forecast.
- No failed or interrupted dry-run output is included in `n`.
- Existing gap JSON files from failed attempts remain operational logs only and must never be scored as forecasts.
- The first successful contemporaneous experiment observation begins only after this amendment is committed and the corresponding code change is present on the executing droplet.

## No hindsight rule

This amendment is locked before any successful experiment forecast. After the first successful forecast, changing the GPT-5.6 output-token cap requires a new prospective amendment and may not be justified by observed forecasting performance.
