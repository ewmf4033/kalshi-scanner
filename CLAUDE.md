# Kalshi Scanner Wiki — Schema (CLAUDE.md)

This is a prediction-market knowledge base following the LLM Wiki pattern. The LLM owns and maintains the wiki layer entirely. The human curates sources, directs analysis, and makes trading decisions.

## Architecture

```
kalshi-scanner/
├── raw/                          # IMMUTABLE — LLM reads, never modifies
│   ├── scans/                    # daily scanner JSON outputs (claude + gemini)
│   ├── consensus/                # synthesizer JSON outputs
│   ├── snapshots/                # Kalshi API market data pulls
│   ├── articles/                 # clipped macro research via Obsidian Web Clipper
│   └── assets/                   # downloaded images from clipped articles
├── wiki/                         # LLM-MAINTAINED — human reads, LLM writes
│   ├── index.md                  # master catalog
│   ├── overview.md               # current macro regime, active thesis, portfolio state
│   ├── markets/                  # one page per tracked Kalshi market/ticker
│   ├── concepts/                 # prediction market concepts, macro frameworks
│   ├── catalysts/                # upcoming event calendar pages by month
│   ├── models/                   # claude vs gemini performance tracking
│   ├── performance/              # trade outcomes, calibration, edge decay, scoring
│   └── logs/                     # archived log segments
├── log.md                        # append-only operations log (current window)
├── CLAUDE.md                     # this file
└── tools/
    ├── prompts/
    │   ├── scanner.md
    │   └── synthesizer.md
    ├── scanner.py                # daily cron
    ├── resolve.py                # settle markets, compute scoring metrics
    └── lint.py                   # wiki health checks, log rotation
```

## Write Authority Rules

**Append-only fields** (never overwrite):
- Thesis History
- Scanner History
- Edge Decay table

**Confidence-gated fields** (must include confidence + source_count):
- Any probability estimate
- Any outcome claim
- Any performance statistic

```yaml
confidence: low|medium|high
source_count: <integer>
```

If confidence is `low` → append only, flag for human review. Low-confidence claims do not propagate.

## Correlation Cluster Vocabulary

Both models must use these exact strings:

```
inflation | fed_policy | labor_market | growth_gdp | crypto_beta |
political_cycle | oil_energy | weather_temp | weather_precip | uncorrelated
```

## Page Types and Templates

### Market Page (`wiki/markets/{TICKER}.md`)
```yaml
---
ticker: KXRATECUTCOUNT-26DEC31
category: macro
status: active|settled|expired
resolution_date: 2026-12-31
first_scanned: 2026-04-05
times_flagged: 3
models_agreed: true|false
outcome: null|yes|no
settlement_price: null
correlation_cluster: fed_policy
domain: [macro, fed]
tags: [inflation, fed, rates]
---
```

**Contract Description** — exact resolution wording from Kalshi.

**Price History** — table: date | yes_price | implied_prob.

**Scanner History** — table: date | model | direction | edge_pct | prob_low | prob_high | grounding_source. Append-only.

**Thesis History** — dated entries, never overwritten:
```markdown
### [2026-04-05]
- **Direction:** YES
- **Reasoning:** [text]
- **Grounding:** [source URL or report]
- **Confidence:** high | source_count: 3
- **Macro regime at time:** inflationary
```

**Edge Decay** — table: scan_date | edge_at_scan | price_at_scan | latest_price | edge_remaining.

**Resolution Tracking** — clearly separated from model views:
- `outcome`: yes|no
- `settlement_price`: final price before resolution
- `executed_price`: actual fill price (null if not traded)
- `executed_contracts`: contracts filled (null if not traded)
- `theoretical_pnl`: scan price vs outcome
- `realized_pnl`: executed_price vs outcome (null if not traded)
- `brier_contribution`: (prob_midpoint - outcome)² — computed by resolve.py
- `log_loss_contribution`: computed by resolve.py

**Related** — wikilinks.

### Concept Page (`wiki/concepts/{slug}.md`)
```yaml
---
type: concept
tags: [bias, pricing]
sources: 3
---
```
Sections: Definition, Relevance to Trading, Historical Examples, Related.

### Catalyst Page (`wiki/catalysts/{month-year}.md`)
```yaml
---
type: catalyst-calendar
month: 2026-04
---
```
Sections: Calendar, Post-Event Notes.

### Model Performance Page (`wiki/models/{model-name}.md`)
Sections: Overall Stats, By Category, Notable Hits/Misses, Comparison.

### Performance Pages (`wiki/performance/`)
- `accuracy-by-model.md` — head-to-head
- `accuracy-by-category.md` — edge by market type
- `edge-decay.md` — how fast edges close
- `calibration.md` — prob_range midpoint vs actual outcomes
- `scoring.md` — **Brier score, log loss, expected calibration error (ECE) by model and category.** Computed by `resolve.py`, not the LLM. Updated on every resolution batch.

## Operations

### Ingest (daily, automated)
1. Read new scan + consensus JSONs
2. For each flagged trade: create or update market page (append Scanner History, Thesis History)
3. Update catalysts, overview, index
4. Append to log.md

Log rotation handled by `tools/lint.py`, not the LLM.

### Ingest (manual, articles)
1. Read article, discuss with human
2. Create/update concept pages, market pages (append to Thesis History)
3. Update index, append to log

### Query
1. Read index.md (L1), filter by tags
2. Read relevant pages (L2-L3)
3. **Two outputs rule:** answer AND wiki updates

### Resolve (via `tools/resolve.py`)
1. Find active markets past resolution_date
2. Look up outcomes via Kalshi API
3. Update market page: outcome, settlement_price, executed_price/contracts if traded
4. **Compute scoring metrics:** brier_contribution, log_loss_contribution per market
5. **Update `performance/scoring.md`:** aggregate Brier, log loss, ECE by model and category
6. Populate Edge Decay, append final Thesis History entry
7. Update performance/ and models/ pages
8. Append to log

### Lint (via `tools/lint.py`)
Python handles: log rotation, stale markets, cluster validation, orphan detection.
LLM-assisted: contradiction checks, missing concepts, stale overview.

## Indexing

```markdown
# Kalshi Scanner Wiki Index
Last updated: 2026-04-05
Current macro regime: inflationary

## Active Markets (0)
## Settled Markets (0)
## Concepts (0)
## Catalysts
## Performance
## By Correlation Cluster
```

## Conventions
- `[[wikilink]]` syntax, YAML frontmatter, tags for filtering
- Dates: YYYY-MM-DD, Prices: decimals 0-1, Edge: integer pct
- Thesis History is append-only
- correlation_cluster from ALLOWED list only
- Performance prefers realized_pnl; falls back to theoretical_pnl
- Scoring metrics (Brier, log loss) computed by Python, never by LLM

## Progressive Disclosure
- **L0 (~200 tokens):** This CLAUDE.md
- **L1 (~1-2K tokens):** wiki/index.md → filter by tags
- **L2 (~2-5K tokens):** Frontmatter + latest Thesis History entry
- **L3 (5-20K tokens):** Full page content
