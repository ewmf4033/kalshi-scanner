# Shadow Experiment API Access Audit

**Date locked:** 2026-07-12  
**Status:** Recorded before any GPT-5.6 or Fable 5 experiment forecast fires.

## Purpose

This note makes the no-search implementation claim auditable per lane and distinguishes production data from experiment data.

## Per-lane tool-access findings

### GPT-5.6 Track A

- Prompt: price-visible Track A prompt built by `build_track_a_prompt()`.
- Search instruction: legacy search sentence must be present and is replaced exactly once; prompt drift causes a hard failure.
- API endpoint: OpenAI Responses API.
- Request payload fields: `model`, `input`, `max_output_tokens`.
- `tools`: absent.
- `tool_choice`: absent.
- `web_search`: absent.
- `search`: absent.
- `retrieval`: absent.
- Runtime guard: `assert_no_search_payload()` fails loudly if any forbidden tool/search field is added.

### GPT-5.6 Track B

- Prompt: blind no-search prompt in deterministic 25-market chunks.
- Blind payload: whitelist-only fields: ticker, title, subtitle, close_time, resolution_source.
- API endpoint: OpenAI Responses API.
- Request payload fields: `model`, `input`, `max_output_tokens`.
- `tools`: absent.
- `tool_choice`: absent.
- `web_search`: absent.
- `search`: absent.
- `retrieval`: absent.
- Runtime guard: `assert_no_search_payload()` fails loudly if any forbidden tool/search field is added.

### Fable 5 Track A

- Prompt: price-visible Track A prompt built by `build_track_a_prompt()`.
- Search instruction: legacy search sentence must be present and is replaced exactly once; prompt drift causes a hard failure.
- API endpoint: Anthropic Message Batches API.
- Per-request params: `model`, `max_tokens`, `messages`.
- `tools`: absent.
- `tool_choice`: absent.
- `web_search`: absent.
- `search`: absent.
- `retrieval`: absent.
- Runtime guard: `assert_no_search_payload()` runs on each request params object and on the batch root payload.

### Fable 5 Track B

- Prompt: blind no-search prompt in deterministic 25-market chunks.
- Blind payload: whitelist-only fields: ticker, title, subtitle, close_time, resolution_source.
- API endpoint: Anthropic Message Batches API.
- Per-request params: `model`, `max_tokens`, `messages`.
- `tools`: absent.
- `tool_choice`: absent.
- `web_search`: absent.
- `search`: absent.
- `retrieval`: absent.
- Runtime guard: `assert_no_search_payload()` runs on each request params object and on the batch root payload.

## Fail-closed launcher rule

`tools/shadow_experiment.py` refuses to run unless environment variable `SHADOW_NO_SEARCH_ENFORCED=1` is present.

The approved launcher is:

```bash
python3 run_shadow_experiment.py ...
```

The launcher sets the enforcement variable before importing and invoking the experiment module.

Direct execution of:

```bash
python3 tools/shadow_experiment.py ...
```

must exit without running the experiment.

## Production versus experiment data streams

The existing production scanner may retain its legacy search-enabled behavior for Haiku/Telegram continuity. That production lane and the new no-search Sonnet/GPT/Fable experiment lanes are different methodologies and must never be pooled as one contemporaneous control stream.

The historical clean n=14 Sonnet result remains contextual historical reference only. Formal experiment verdicts come from contemporaneous lane-vs-lane comparisons collected under identical experiment conditions.

## Required pre-cron tests

Before cron activation:

1. Pull the repository on the droplet.
2. Run `py_compile` on the experiment files.
3. Verify direct-module execution fails closed.
4. Run `python3 run_shadow_experiment.py --self-test-failure-path` and require success.
5. Run one dry shadow execution against a saved historical snapshot.
6. Confirm JSON parse success, chunk reassembly, identical snapshot IDs, sane Track B selection, and explicit partial-failure metadata.
7. Only then install cron, and cron must invoke `run_shadow_experiment.py`, never the module directly.
