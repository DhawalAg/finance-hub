# Finance Research Lens — Working Spec

Last updated: 2026-06-04
Status: scaffold for a block-by-block sharpening pass — the open questions (R1–R15) are the agenda

This is the **research lens** of the finance hub: the workflow for going **top-down through
industries → key players → deep research on the industry / companies / instruments**, and for
preserving the thesis, the important dates, and the trusted-source analysis that a deployment
decision rests on. It covers raw requirements **#2 (instrument discovery)** and **#3 (company &
instrument research)**, and is the home for the deferred **financial-analysis** layers
(fundamentals, filings, metrics).

It is specced apart from
[requirements-dump.md](../../../../notes/finance-corpus/00-inbox/requirements-dump.md) (planner source
material) and the [market-data scaffold](../market-data/spec.md) so each stays
single-purpose. Like the planner, this lens
is **fully buildable and useful today on agent + persistence alone** — every quantitative dependency
(prices, metrics, fundamentals, filings) sits behind a seam that can stay deferred.

> Companion docs:
> - [requirements-dump.md](../../../../notes/finance-corpus/00-inbox/requirements-dump.md) — the
>   2026-05-28 sharpening pass (headless tool
>   registry, the **sleeve**, the agent/tool reframe, the plugin seams). This lens produces research
>   candidates + evidence; a later explicit promotion snapshots approved research into planner-owned
>   sleeves.
> - [data-pipeline-spec.md](../../../../notes/finance-corpus/00-inbox/data-pipeline-spec.md) +
>   [data-pipeline-answers.md](../../../../notes/finance-corpus/00-inbox/data-pipeline-answers.md)
>   — the price/metrics subsystem. This lens **reads** `fin_metrics` / `fin_price_bars`; it does not
>   compute them.
> - [data-source-comparison.md](../../../../notes/finance-corpus/00-inbox/data-source-comparison.md) —
>   the provider decision this lens
>   activates: **FMP** (`FundamentalsProvider`/`EarningsProvider`/`EstimatesProvider`, screening-grade)
>   + **edgartools** (`FilingsProvider`, free, decision-grade ground truth).
> - [finance-ingestion spec](../ingestion/spec.md) — the
>   active budget slice, the *other* producer feeding the planner. This spec mirrors its conventions
>   (pure-core + thin `@tool` wrapper, `fin_*` tables, finance-owned migrations,
>   north-star provenance).

---

## 1. North star (inherited, extended from numbers to claims)

The planner's north star is *"every number traces to imported data or a tool result, not model
freehand."* Research extends it from **numbers** to **claims**:

> **Every thesis claim traces to a cited source (a filing, a trusted-source analysis, a price, or a
> computed metric) — never model freehand.** Tools persist the structure, the dates, the sources, and
> the fetched facts; the agent does the research and writes the prose, but the prose stands on cited
> sources and structured facts the tools can produce on demand.

This is what makes a deployment decision *defensible* on the thesis side, exactly as reconciliation +
`historical_surplus` make the budget evidence defensible. A later `deployable_capital` composition
layer may combine that evidence with liquidity, reserves, obligations, and an explicit user override.

---

## 2. The reframe applied to research (the load-bearing section)

Research is the lens where the temptation to *build a research engine* is strongest and most wrong.
The corpus reframe (tools own facts/state; the agent owns judgment/synthesis) draws an unusually clean
line here:

- **The agent owns the research itself** — at runtime, with web access and document reading:
  mapping an industry to its structure and sub-segments, naming the key players, reading filings,
  forming and writing the thesis, judging what matters next. This is precisely what an LLM does best.
  **None of this is code.** (Resolves req #3's "Cheap via agent" verdict and req #2's "Agent + web
  maps theme→tickers".)
- **The tools own the durable output of that research** — the structured, retrievable, provenanced
  residue: the industry/theme map, the key-player edges (the watchlist), the thesis note's location,
  the important dates, the cited/trusted sources, and (deferred) the fetched fundamentals/filings/metrics.

So the research lens is **mostly a persistence + retrieval + provenance layer over agent-driven
research**, plus a set of deferred data seams. There is no "discovery algorithm," no scraper, no
NLP — the same way the budget lens has no PDF parser.

| Capability | Who owns it | Form |
|---|---|---|
| "What industries should I look at?" | **Agent** (judgment + web) | runtime reasoning |
| "Which companies are the key players in compute?" | **Agent** (web research) | runtime reasoning |
| "Persist these 6 tickers as the compute watchlist" | **Tool** | `fin_theme_instruments` rows |
| "Write the compute thesis" | **Agent** (synthesis) | markdown in the vault |
| "Store where that thesis lives + its sources" | **Tool** | note path + `fin_research_sources` |
| "When does NVDA report next?" | **Tool** (agent-entered now / FMP later) | `fin_events` row |
| "Is this 10-K number right?" | **Tool** (edgartools, deferred) | `FilingsProvider` |
| "What's the 3-month return / drift?" | **Tool** (market-data analytics, deferred) | `fin_metrics` |

---

## 3. The framing that makes this seamless: research produces *candidates + evidence*

The corpus first slice is the **planner**, defined as the join of three inputs:

```
plan_deployment(deployable_capital, cadence)
  reads:  deployable_capital    ← later composition over BUDGET evidence
          approved strategy     ← explicit promotion from RESEARCH candidates
          holdings              ← later holdings slice
          prices                ← market data (`finance.prices(...)` PriceEnvelope)
```

The budget lens (`docs/requests/finance/ingestion`) produces reconciled historical-surplus evidence
that a later capital-composition layer can turn into planner-ready capital. **This lens is the
investing-side upstream workflow:** it produces themes, candidate instruments, cited reasoning, and a
user-reviewed promotion into planner strategy state.

That is the seamless idea the coupling delivers: the top-down exploration flow you want
(**industry → key players → deeper research**) is not a side feature — it is the upstream evidence
workflow that informs the planner's strategy model. Completing the flow:

```
  BUDGET ──▶ historical-surplus evidence ─▶ capital composition ┐
  RESEARCH ─▶ themes + candidates + citations ─▶ approve strategy ┼──▶ PLANNER ─▶ deployment plan
  DATA PIPELINE ──────────────────────────▶ prices / metrics      ┘
```

### Theme ↔ sleeve (the central modelling decision — see R1)

A **theme** is the research/exploration object; a **sleeve** is a theme you've committed capital to (a
theme + a `target_weight`) inside a specific strategy version. You explore many industries you'll
never fund; allocation is a later explicit commitment, not a side effect of research. Lean:
**separate research themes from versioned planner sleeves**. Research compounds into the strategy
through an explicit promotion step. (Held open as R1.)

---

## 4. First-class objects

1. **Theme / industry** (`fin_themes`) — the exploration object: `compute`, `energy`, `model
   providers`, `storage`. Carries a research lifecycle `status ∈ {exploring, watching, archived}` and
   an optional `parent_key` for industry → sub-segment drill-down. Its prose thesis lives in the vault
   (a note path, not a TEXT blob).
2. **Instrument** (`fin_instruments`, shared with the planner) — `{ticker, type ∈ stock|etf, ...}`. The
   research lens *discovers and annotates* these; the planner *allocates* to them. A "key player" = an
   instrument tagged to a theme.
3. **Theme↔instrument edge** (`fin_theme_instruments`) — the watchlist / key-player list (req #2):
   which instruments belong to a theme, with a review status (`candidate | watching | approved |
   rejected`), a `role` ("hyperscaler", "pure-play silicon"), and optional research conviction +
   rationale. That conviction is descriptive metadata, not automatic allocation input (R9).
4. **Research note / dossier** — the prose: the thesis, the industry deep-dive, the per-instrument
   analysis. Lives in the **vault as markdown** (corpus rule: *SQLite owns numbers, markdown owns
   prose*). SQLite stores only the relative note path + structured facts. The finance-specific vault
   convention is defined in Block 5; `hubs/research` is only a stub today.
5. **Important date / event** (`fin_events`) — earnings calls, ex-dividend, lockup expiry, product
   events. Structured facts; agent-entered now, `EarningsProvider`-fed later. Powers "what matters
   next" (req #3).
6. **Source** (`fin_research_sources` + `fin_research_source_links`, a finance-owned extension of the
   minimal core `Source` concept)
   — reusable cited/trusted analysis a note rests on, with source type, publication/access dates, and
   an optional user-curated `trusted` flag (req #3: "preserve trusted-source analysis"). One source
   may support multiple themes / instruments. In v1, claims cite source IDs inline in markdown;
   structured claim rows are deferred until claim-level reasoning is a demonstrated need.

### Hybrid knowledge-base model

The research lens is a hybrid knowledge base:

```text
Markdown owns research thinking.
SQLite owns structured facts and relationships.
Generated readouts combine both.
```

| Layer | Purpose | Editable? |
|---|---|---|
| Editable markdown notes | Detailed research, evolving reasoning, risks, invalidation conditions, and open questions | Yes |
| SQLite | Knowledge-base index, facts, relationships, lifecycle state, and note paths | Through tools |
| Generated markdown + HTML readouts | Current composed view for review and sharing | No — replaceable output |

Use this rule when expanding the model:

```text
If it needs filtering, validation, or deterministic composition → SQLite.
If it needs interpretation, nuance, or revision → Markdown.
```

Theme notes answer what the thesis is, why it matters now, what could invalidate it, what remains
unclear, and which companies appear important. Instrument notes answer what a company does, how it
participates in a theme, its advantages and risks, the supporting evidence, and what would change the
view. Conviction is only a compact structured summary; detailed reasoning remains in those editable
notes.

---

## 5. The structured exploration flow (the user's core want, walked end-to-end)

The drill-down, and the tool at each step (agent does the thinking, the tool persists the residue):

```
① Industry sweep      agent + web research the landscape
   → finance.set_theme("compute", status="exploring", parent="ai-buildout")
② Sub-segment map     agent decomposes the industry
   → finance.set_theme("silicon", parent="compute"); set_theme("networking", parent="compute")
③ Key players         agent names the companies/ETFs that matter, with web-cited reasoning
   → finance.map_instruments("silicon", [{ticker:"NVDA", role:"pure-play",
                                          conviction:5, conviction_note:"..."}, ...])
④ Deep research       agent reads filings/analysis, writes the thesis
   → finance.set_research_note(scope="theme", key="compute", <markdown>)  → vault path
   → finance.add_source(scope="instrument", key="NVDA", url=..., trusted=true)
⑤ What matters next   agent enters (or FMP feeds) the dates
   → finance.record_event("NVDA", "earnings", "2026-08-27", source_id=42, timing="after_market")
⑥ Grounded view       compose everything that traces to a tool/source
   → finance.instrument_brief("NVDA")  /  finance.theme_brief("compute")
   → finance.render_theme_brief("compute")  → markdown + static HTML readouts
⑦ Commit to strategy  explicitly promote approved research into versioned planner state
   → finance.promote_to_strategy(...)  → strategy version + sleeves + approved instruments → PLANNER
```

Steps ①–⑥ are the research lens; step ⑦ is the seam into the planner. The flow accumulates — you never
re-research an industry; you drill, annotate, and the structure compounds into the strategy.

---

## 6. Tools (research namespace — all thin wrappers over agent research)

All `finance.*`, co-located in `hubs/finance/`, pure helpers in submodules, `@tool` wrappers thin
(mirrors the budget slice). Namespace/hub relationship held open as R2.

| Tool | Signature (kwargs) | Returns | Notes |
|---|---|---|---|
| `finance.set_theme` | `key, display_name=None, description=None, status="exploring", parent=None` | `{theme_key, note_path}` | Create/update a theme (industry or sub-segment). Idempotent on `key`. |
| `finance.list_themes` | `status=None, parent=None` | `[{key, display_name, status, parent, instrument_count, has_note}]` | The industry index / drill-down — "go through industries". |
| `finance.get_theme` | `key` | `{theme, instruments:[…], events:[…], sources:[…], note_path}` | One theme's full structured view. |
| `finance.map_instruments` | `theme, instruments:[{ticker,type?,status?,role?,conviction?,conviction_note?,note?}]` | `{added, updated, watchlist:[…]}` | Persist key players / watchlist for a theme (req #2). Agent-added rows default to `candidate`. Upserts the instrument + the edge. Conviction is optional research metadata. |
| `finance.review_instrument` | `theme, ticker, status:"watching"\|"approved"\|"rejected", conviction=None, conviction_note=None, note=None` | `{theme, ticker, status, conviction}` | Explicitly review one candidate. Discovery alone never makes an instrument planner-eligible. A populated conviction requires rationale. |
| `finance.set_research_note` | `scope:"theme"\|"instrument", key, markdown` | `{note_path}` | Writes the **agent-authored** thesis/analysis to the configured vault; stores a relative path. Prose, not numbers. |
| `finance.get_research_note` | `scope, key` | `{note_path, markdown}` | Read the note back for grounding/iteration. |
| `finance.add_source` | `scope, key, url, title=None, publisher=None, source_type=None, published_on=None, trusted=False, review_after=None, note=None` | `{source_id}` | Promote relevant evidence from ad hoc research: exact-URL upsert, refresh last-access time, and attach it to a theme or instrument. `note` describes association-specific relevance (req #3). |
| `finance.list_sources` | `scope=None, key=None, trusted_only=False, include_inactive=False` | `[{…source…}]` | The provenance trail behind a thesis. Defaults to active source links. |
| `finance.review_source` | `source_id, scope, key, status="active", review_after=None, note=None` | `{source_id, scope, key, status, review_after}` | Re-check one source link; mark it active, superseded, or archived. Historical citations remain resolvable. |
| `finance.sources_due_for_review` | `as_of=None, scope=None, key=None` | `[{…source_link…}]` | Surface time-sensitive evidence whose explicit `review_after` date has passed. No crawler or scheduled refresh in v1. |
| `finance.record_event` | `ticker, event_type, event_date, source_id, status="scheduled", date_precision="date", timing="unknown", note=None` | `{event_id}` | Minimal manual v1 intake for instrument dates. Upserts the natural event identity. Agent-entered now; provider-fed later. |
| `finance.review_event` | `event_id, status=None, event_date=None, date_precision=None, timing=None, source_id=None, note=None` | `{event_id, status, event_date}` | Correct, confirm, postpone, complete, or cancel an existing event without deleting history. |
| `finance.upcoming_events` | `within_days=14, scope=None, key=None, include_tentative=True` | `[{key, event_type, event_date, date_precision, timing, status, days_until, source_id}]` | **"What matters next"** (req #3) — the daily/weekly digest input; later the reporting lens reads this. |
| `finance.instrument_brief` | `ticker` | `{instrument, themes:[…], position?, latest_price?, metrics?, fundamentals?, quantitative_availability:{…}, upcoming_events:[…], sources:[…], sources_due_for_review:[…], note_path}` | **Deep-dive for a ticker** (req #3) — a *compose/read* tool. Optional quant fields appear only when grounded data is available; availability metadata explains omissions (R7/R8). |
| `finance.theme_brief` | `theme` | `{theme, sub_themes:[…], key_players:[{ticker, role, conviction, snapshot?}], aggregate?, quantitative_availability:{…}, upcoming_events:[…], sources:[…], sources_due_for_review:[…], note_path}` | **The industry-level view** — structure + players + explicit source-upkeep warnings + optional grounded per-player snapshots. |
| `finance.render_theme_brief` | `theme, formats=("md","html")` | `{markdown_path?, html_path?}` | Atomically replace generated readouts under the configured vault from the same grounded `theme_brief` model + thesis note. Markdown is canonical; static HTML is derived from it. Both carry visible **generated — do not edit** warnings. No separate editing path, JavaScript, or dashboard. |

**Planner seam (design now; build with the planner):**

| Tool | Signature | Returns | Notes |
|---|---|---|---|
| `finance.promote_to_strategy` | `strategy_name, theme_weights:[{theme, target_weight}], instruments_by_theme=None, note=None` | `{strategy_id, version, sleeves:[…]}` | Explicitly snapshots approved research into versioned planner strategy state. Never called implicitly by discovery tools. |

**Deferred behind seams (do not build until activated — §7):**

| Tool | Seam | Provider | Trigger |
|---|---|---|---|
| `finance.fundamentals` | `FundamentalsProvider` / `FilingsProvider` | FMP (screening) + edgartools (ground truth) | research lens activates a thesis needing financials |
| `finance.metrics` | reads `fin_metrics` | market-data analytics (snapshot slice) | price-bar series exists |
| `finance.earnings_calendar` | `EarningsProvider` | FMP | yfinance earnings-date unreliability bites (corpus B2 #2) |

---

## 7. The deferred quantitative layers (financial analysis — folded in as seams, not built)

This is how #2 (metrics) and #3 (fundamentals/filings) couple in *seamlessly* without expanding the
build now. The qualitative lens (§4–§6) ships first and stands alone; each quantitative layer slots
into a slot that already exists in `instrument_brief` / `theme_brief`.

1. **MetricsProvider (the analytics layer)** — `fin_metrics` from
   [data-pipeline-answers §D](../../../../notes/finance-corpus/00-inbox/data-pipeline-answers.md) (returns,
   vol, drawdown, momentum, drift over
   the daily `fin_price_bars` series, `adj_close`-based). The research lens **reads** these to ground the
   "financial analysis" of a theme's players; it never computes them (the snapshot tool does). Until
   the snapshot slice lands, the `metrics` field is absent and `quantitative_availability.metrics`
   explains why — the brief degrades to qualitative (R7).
2. **FundamentalsProvider (FMP)** — statements, ratios, analyst estimates. Treated as
   **screening/directional only, never decision-grade** (the FMP restatement caveat in
   data-source-comparison). Fills the "fundamentals" slot of a brief; the agent fills it manually with
   cited sources until activated.
3. **FilingsProvider (edgartools, free)** — 10-K/10-Q/8-K/Form 4, XBRL statements. The **decision-grade
   ground truth** for any fundamental a thesis rests on (north-star aligned, primary source). Build
   requirement when activated: EDGAR identity env var, ≤8 req/s, cache-first, backoff (per
   data-source-comparison "Verified").
4. **EarningsProvider (FMP)** — reliable earnings dates to replace agent-entered / unreliable yfinance
   dates.

**Activation policy:** Block 10 defines the trigger gates. Research consumes market-data read seams;
adapter selection, secrets, operational logging, retry policy, and cache policy belong to the
market-data layer. The planner consumes `finance.prices(...)` price envelopes and remains unaware of
whether daily bars came from yfinance or a later replacement.

**Failure handling stays behind each deferred provider seam:** do not generalize the budget slice's
`fin_ingest_issues` inbox into a universal error table now. When a provider is activated, define its
operational log / retry policy alongside the owning data-pipeline slice. Interactive calls should fail
loud; scheduled runs should log-and-continue.

---

## 8. Data model (research-owned `fin_*` tables; shapes to confirm)

Finance owns these in `hubs/finance/store.py` (not `core/store.py`), via the finance-owned migration
table (`fin_schema_migrations`, per ingestion M1 — **not** global `PRAGMA user_version`). FK + `CHECK`
+ indexes per ingestion DB1.

```sql
CREATE TABLE fin_themes (
  key            TEXT PRIMARY KEY,             -- 'compute' | 'silicon' | 'energy'
  display_name   TEXT NOT NULL,
  description    TEXT,                         -- one-liner; the THESIS prose lives in the vault note
  status         TEXT NOT NULL DEFAULT 'exploring', -- 'exploring' | 'watching' | 'archived'
  parent_key     TEXT,                         -- industry → sub-segment drill-down; NULL = top-level
  note_path      TEXT,                         -- vault markdown path (prose); NULL until written
  created_at     TEXT NOT NULL,
  FOREIGN KEY (parent_key) REFERENCES fin_themes(key)
);

CREATE TABLE fin_instruments (                  -- shared with the planner's strategy model
  ticker       TEXT PRIMARY KEY,
  type         TEXT NOT NULL DEFAULT 'stock',  -- 'stock' | 'etf'   (USD-only v1; reject suffixes per pipeline E2)
  display_name TEXT,
  note_path    TEXT,                            -- per-instrument vault dossier; NULL until written
  created_at   TEXT NOT NULL,
  CHECK (type IN ('stock','etf'))
);

CREATE TABLE fin_theme_instruments (            -- the key-player / watchlist edge (M:N)
  theme_key   TEXT NOT NULL,
  ticker      TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'candidate', -- 'candidate' | 'watching' | 'approved' | 'rejected'
  role        TEXT,                             -- 'pure-play silicon' | 'hyperscaler' | 'picks-and-shovels'
  conviction  INTEGER,                          -- optional research metadata only (R9)
  conviction_note TEXT,                         -- required rationale when conviction is populated
  note        TEXT,
  added_at    TEXT NOT NULL,
  PRIMARY KEY (theme_key, ticker),
  FOREIGN KEY (theme_key) REFERENCES fin_themes(key),
  FOREIGN KEY (ticker)    REFERENCES fin_instruments(ticker),
  CHECK (status IN ('candidate','watching','approved','rejected')),
  CHECK (conviction IS NULL OR conviction BETWEEN 1 AND 5),
  CHECK (conviction IS NULL OR (conviction_note IS NOT NULL AND length(trim(conviction_note)) > 0))
);

CREATE TABLE fin_research_sources (             -- finance-owned extension of the core Source concept
  id          INTEGER PRIMARY KEY,
  url         TEXT NOT NULL UNIQUE,             -- exact-URL upsert in v1; no URL canonicalizer
  title       TEXT,
  publisher   TEXT,
  source_type TEXT,                             -- 'filing' | 'analysis' | 'opinion' | 'aggregation' | ...
  published_on TEXT,
  trusted     INTEGER NOT NULL DEFAULT 0,       -- 1 = a source the user vouches for (R10)
  first_accessed_at TEXT NOT NULL,
  last_accessed_at  TEXT NOT NULL,
  CHECK (trusted IN (0,1))
);

CREATE TABLE fin_research_source_links (        -- reuse one source across themes / instruments
  source_id   INTEGER NOT NULL,
  scope       TEXT NOT NULL,                    -- 'instrument' | 'theme'
  key         TEXT NOT NULL,
  note        TEXT,                             -- why this source matters to this research object
  status      TEXT NOT NULL DEFAULT 'active',   -- 'active' | 'superseded' | 'archived'
  review_after TEXT,                            -- explicit freshness reminder for time-sensitive evidence
  reviewed_at TEXT,
  linked_at   TEXT NOT NULL,
  PRIMARY KEY (source_id, scope, key),
  FOREIGN KEY (source_id) REFERENCES fin_research_sources(id),
  CHECK (scope IN ('instrument','theme')),
  CHECK (status IN ('active','superseded','archived'))
);
CREATE INDEX idx_fin_research_source_links_review
  ON fin_research_source_links(status, review_after);

CREATE TABLE fin_events (                        -- event occurrences (req #3 "what matters next")
  id          INTEGER PRIMARY KEY,
  scope       TEXT NOT NULL,                    -- 'instrument' | 'theme'
  key         TEXT NOT NULL,                    -- ticker or theme key
  event_type  TEXT NOT NULL,                    -- v1: 'earnings' | 'ex_dividend'
  event_date  TEXT NOT NULL,                    -- YYYY-MM-DD
  date_precision TEXT NOT NULL DEFAULT 'date',  -- 'date' | 'tentative'
  timing      TEXT NOT NULL DEFAULT 'unknown',  -- 'before_market' | 'after_market' | 'during_market' | 'unknown'
  status      TEXT NOT NULL DEFAULT 'scheduled', -- 'scheduled' | 'completed' | 'cancelled'
  source_id   INTEGER NOT NULL,                 -- citation / provenance for this occurrence
  note        TEXT,
  recorded_at TEXT NOT NULL,
  updated_at  TEXT NOT NULL,
  FOREIGN KEY (source_id) REFERENCES fin_research_sources(id),
  UNIQUE (scope, key, event_type, event_date),
  CHECK (scope IN ('instrument','theme')),
  CHECK (event_type IN ('earnings','ex_dividend')),
  CHECK (date_precision IN ('date','tentative')),
  CHECK (timing IN ('before_market','after_market','during_market','unknown')),
  CHECK (status IN ('scheduled','completed','cancelled'))
);
CREATE INDEX idx_fin_events_upcoming
  ON fin_events(status, event_date);
-- Deferred / separately owned by market data: fin_price_bars, fin_metrics, and a fin_fundamentals cache.
```

Notes:
- **`fin_instruments` is the shared join with the planner** — research populates it (discovery), the
  planner reads approved snapshots of it after explicit promotion (allocation). This is the concrete
  realization of §3's "research produces the candidate universe."
- **Prose is never a TEXT blob** — `note_path` stores a relative vault path; the agent authors, the tool
  stores the pointer. Keeps imported data / generated analysis / agent-authored thesis cleanly separated
  (corpus principle).
- **Research state is not planner state.** A later explicit promotion snapshots selected themes,
  weights, and approved instruments into versioned planner-owned strategy tables (R1/R11/R12).
- **Conviction is scoped research metadata.** It describes the current view of one ticker within one
  theme and requires rationale. It is not copied into planner weights or used by deployment math.
- **Sources are reusable.** `fin_research_source_links` keeps association-specific relevance separate
  from source metadata. Tools validate the polymorphic link target exists before inserting it. These
  finance-owned tables do not overload the generic core `sources` table, which is scoped to the
  existing company / person spine.
- **Staleness is surfaced, not silently "fixed."** A source remains historical evidence even when its
  link is superseded or archived. Briefs show active sources and flag explicit `review_after` dates
  that have passed; they do not crawl the web or delete citations.
- **Event acquisition and event storage stay separate.** V1 uses explicit manual intake through
  `record_event(...)`; later providers write through the same domain path rather than changing brief
  behavior.
- **`fin_events` is an occurrence ledger.** Store each historical and upcoming earnings / ex-dividend
  occurrence as its own row. Updating one tentative occurrence does not collapse prior completed
  occurrences for the same ticker.

---

## 9. Open questions (the sharpening agenda — R1–R15)

Work these block-by-block like the budget slice's S/L/D/etc. queue. Lean shown where one exists.

| # | Block | Question | Lean |
|---|---|---|---|
| **R1** | Model | Theme vs sleeve — one entity with a lifecycle or separate research-theme and strategy-sleeve objects? | **Separate objects.** Research themes remain exploratory; explicit promotion snapshots selected themes into versioned planner sleeves. |
| **R2** | Spine | Namespace + hub: `finance.*` in `hubs/finance` vs. reuse the generic `research` hub? | `finance.*`; **reuse the vault-dossier *pattern*** from `hubs/research`, not the hub. |
| **R3** | Taxonomy | Free-form agent-authored themes vs. anchor to a standard scheme (GICS sectors/industries)? | **Free-form** (the user's themes — "compute", "model providers" — aren't GICS); optional GICS tag. |
| **R4** | Vault | Where in the Obsidian vault do notes live; front-matter schema; one note per theme + per instrument; link structure? | Settle a finance-specific convention before writing. `hubs/research` is only a stub today. |
| **R5** | Events | Which `event_type`s in v1; agent-entered vs. `EarningsProvider`; how to expire stale dates; yfinance earnings-date unreliability. | Start `earnings`+`ex_dividend`, agent-entered; FMP when B2 #2 fires. |
| **R6** | Providers | Exact activation triggers + what's decision-grade (edgartools) vs screening (FMP) for *this* lens. | Per data-source-comparison trigger path; edgartools = decision-grade, FMP = screening. |
| **R7** | Dependency | Do briefs block on the metrics/price pipeline, or degrade gracefully when it's absent? | **Degrade gracefully** — quantitative fields optional; qualitative research stands alone. |
| **R8** | Scope | How much "financial analysis" in v1 — surface fundamentals/metrics with provenance, or computed cross-player screens/comparisons within a theme? | Start: **surface with provenance**; cross-player screens are a fast follow once metrics exist. |
| **R9** | Allocation tie-in | Does research `conviction` feed allocation automatically? | **No in v1.** Persist optional research metadata only; planner weights stay explicit user decisions. |
| **R10** | Trust | What source metadata and trust signal belong in v1? | User-curated `trusted` flag plus `source_type`, publisher, publication date, and access date. No global allowlist. |
| **R11** | Promotion | What explicit action moves research candidates into a planner-eligible universe? | Add `promote_to_strategy`; discovery tools never mutate planner state implicitly. |
| **R12** | Strategy history | Do planner strategies need versions from day one? | **Yes, minimally.** A promotion snapshots sleeves + approved instruments into a new immutable version. |
| **R13** | Claims | Do we need structured claim rows in v1 to satisfy provenance? | **No.** Require inline markdown citations + stored source metadata; revisit claims when cross-source reasoning is real. |
| **R14** | Instrument model | Is ticker-centric `fin_instruments` enough for v1? | **Yes.** Defer issuer/security/share-class normalization until a real case requires it. |
| **R15** | Artifact | What is the first user-visible research artifact? | A cited `theme_brief` with candidate statuses and explicit gaps / next questions, exported as canonical markdown + derived static HTML readouts. |

---

## 10. Sharpening Queue

Work through one block at a time. Record each adjudication in a concise decision ledger before
rewriting this scaffold into an implementation-ready spec.

| Order | Questions | Decision block | Status | Why this comes here |
|---|---|---|---|---|
| 1 | **R1, R11, R12** | Research state vs. planner strategy state | Approved 2026-05-31 | The ownership boundary determines tables, tools, and the safe handoff into deployment planning |
| 2 | **R15** | First user-visible artifact | Approved 2026-05-31 | The artifact determines the narrowest useful vertical slice |
| 3 | **R3, R14** | Theme taxonomy and ticker-centric instrument model | Approved 2026-05-31 | Keep discovery useful without prematurely modeling the whole securities domain |
| 4 | **R10, R13** | Provenance contract | Approved 2026-05-31 | Decide the minimum credible claim/source model before writing notes or briefs |
| 5 | **R4** | Vault note convention | Approved 2026-05-31 | Settle file paths and inline citation conventions only after the artifact and provenance contract |
| 6 | **R2** | Namespace and module ownership | Approved 2026-05-31 | Decide code placement once the first tool surface is clear |
| 7 | **R9** | Conviction metadata | Approved 2026-05-31 | Keep research judgment separate from automatic allocation |
| 8 | **R5** | Events fast follow | Approved 2026-05-31 | Add only after the cited exploration artifact works |
| 9 | **R7, R8** | Graceful quant integration | Approved 2026-05-31 | Confirm optional slots for metrics/fundamentals without implementing providers |
| 10 | **R6** | Provider activation triggers | Approved 2026-05-31 | Sharpen only when a real workflow requires filings, fundamentals, or calendar automation |

### Block 1 — Research State Vs. Planner Strategy State

**Problem:** exploration and deployment are different user commitments. An agent may discover a
company and map it to a theme, but that must not make the company planner-eligible automatically.
Research changes frequently; a deployment strategy needs a reviewable historical snapshot.

**Recommended contract:**

- `fin_themes` and `fin_theme_instruments` belong to research. They store exploration, evidence, and
  review status.
- `fin_theme_instruments.status` is `candidate | watching | approved | rejected`.
- Only an explicit user-confirmed `finance.promote_to_strategy(...)` action creates planner state.
- Planner-owned tables are separate and minimally versioned:

```text
fin_strategies
fin_strategy_versions
fin_strategy_sleeves
fin_strategy_instruments
```

- A strategy version snapshots selected themes, target weights, and approved instruments. Later
  research edits do not mutate an already-created deployment strategy version.
- Research `conviction` is optional metadata only. It never silently becomes allocation weight.

**Decision:** approved 2026-05-31.

### Decision Ledger

| Date | Block | Decision | Consequence |
|---|---|---|---|
| 2026-05-31 | R1, R11, R12 — research state vs. planner strategy state | Separate research themes / candidate review from planner-owned, minimally versioned strategy state. Require explicit user-confirmed promotion. | Keep research tables focused on exploration and evidence. Sharpen planner tables and `promote_to_strategy(...)` in the [strategy spec](../strategy/spec.md). |
| 2026-05-31 | R15 — first user-visible artifact | Start with a cited `theme_brief`. Export canonical markdown and derived static HTML readouts from the same grounded model + thesis note. | Build one portable research artifact before dashboards, screeners, generalized reports, or ticker-level briefs. |
| 2026-05-31 | R3, R14 — theme taxonomy and instrument model | Use free-form hierarchical research themes and a ticker-centric US-listed USD `stock | etf` reference model in v1. | Preserve extension points, but defer external taxonomy enforcement and securities-master complexity until a demonstrated workflow needs them. |
| 2026-05-31 | R10, R13 — provenance and upkeep | Store reusable finance-owned sources, link them to themes / instruments, cite stable source IDs from markdown, and surface explicit review reminders. Keep ad hoc search results ephemeral unless intentionally promoted. | Build a maintainable evidence trail without a crawler, knowledge graph, or structured claim extraction. |
| 2026-05-31 | R4 — vault-note convention | Store editable theme / instrument thesis notes separately from generated markdown / static-HTML readouts under a configurable vault root. Persist relative paths and keep front matter minimal. | Preserve a portable knowledge base while ensuring replaceable generated artifacts are visibly marked **do not edit**. |
| 2026-05-31 | R2 — namespace and module ownership | Keep user-facing tools and domain behavior under `finance.*` / `hubs/finance`, split storage, research logic, vault access, and rendering by responsibility, and extract generic vault helpers only after a second real consumer exists. | Preserve modular internals without building a premature cross-hub framework. |
| 2026-05-31 | R9 — conviction metadata | Store optional coarse `1..5` conviction + required short rationale on the ticker-within-theme edge. Keep detailed reasoning in editable notes and exclude conviction from promotion eligibility and planner math. | Preserve useful structured research judgment without introducing a hidden allocation algorithm. |
| 2026-05-31 | R5 — important events fast follow | Model cited historical and future event occurrences, with manual instrument-level intake first. Preserve additive provider enrichment and a later price-bar analytics seam without building calendar ingestion or simulations now. | Support “what matters next?” and future event-response analysis without expanding the first research slice. |
| 2026-05-31 | R7, R8 — graceful quantitative integration | Keep qualitative briefs useful without providers. Surface optional grounded quantitative context with explicit availability metadata, while leaving deterministic screens, valuations, and event-response analytics outside research rendering. | Quantitative enrichment remains additive and visible without turning the research lens into an analytics engine. |
| 2026-05-31 | R6 — provider activation triggers | Keep qualitative research independent of new provider dependencies. Put provider adapters and operations in market-data, activate them only when named recurring needs fire, and run a sharpening pass before each integration. | Preserve reversible seams and future expansion paths without premature provider work, spend, or coupling. |

### Block 2 — First User-Visible Artifact

**Problem:** the first slice needs a useful end-to-end outcome, not just persistence tools. Starting
with a dashboard, generalized screener, or generated-report pipeline would increase scope before the
core research workflow is proven.

**Recommended artifact:** a cited **theme brief** backed by `finance.theme_brief(theme)` and exported
by `finance.render_theme_brief(theme, formats=("md","html"))`.

The compose tool returns grounded structure:

```text
theme
sub_themes[]
key_players[] grouped by candidate | watching | approved | rejected
sources[]
note_path
optional quantitative slots when market-data slices exist
```

The generated markdown readout uses that grounded output and the markdown thesis note to present:

- what the theme is and why it merits attention;
- the industry / sub-segment map;
- the key companies or ETFs, their role, and their review status;
- cited reasoning and trusted sources;
- explicit gaps and next research questions.

Markdown is the canonical portable readout. HTML is a derived static view rendered from the same
readout, with lightweight embedded styling and no JavaScript. The thesis note remains the editable
prose source; generated readouts are replaced on each render rather than edited independently.

Do not build a dashboard, generalized report pipeline, or structured `research_gaps` table in v1.
The markdown note owns thesis prose and open questions; the compose tool owns durable structure. Add
`instrument_brief(ticker)` second, after one theme flow works end-to-end.

**Decision:** approved 2026-05-31.

### Block 3 — Theme Taxonomy And Ticker-Centric Instruments

**Problem:** a research system can become a securities master-data project quickly. The first slice
needs a useful way to organize exploration without prematurely modeling issuers, exchanges, share
classes, corporate actions, or an external industry taxonomy.

**Recommended contract:**

- Themes are free-form, user-authored research objects with stable slug keys, display names, and an
  optional parent theme. Examples: `ai-buildout`, `compute`, `networking`, `model-providers`.
- Do not force themes into GICS or another standard classification in v1. These are research
  hypotheses, not an industry reference database. Add optional external tags only when a real
  workflow needs them.
- Instruments are ticker-centric in v1: normalized uppercase US-listed USD `stock | etf` symbols.
- The same instrument may belong to many themes through `fin_theme_instruments`.
- Reject unsupported or ambiguous symbols clearly. Defer exchange-qualified identifiers, issuer /
  security normalization, ticker aliases, and share-class modeling until a real case requires them.

This keeps the model intentionally small while preserving an upgrade path.

**Decision:** approved 2026-05-31.

### Modular Evolution Principle

The finance layers should remain independently expandable without becoming a generalized platform
prematurely:

- Research owns themes, candidate review, notes, sources, and briefs.
- Strategy owns immutable promoted snapshots and allocation policy.
- Market data owns prices, metrics, and provider adapters.
- Ingestion owns statement-derived budget evidence.
- `fin_instruments` is a deliberately small shared reference contract across research, market data,
  and strategy. Each layer adds its own tables rather than expanding `fin_instruments` into a
  catch-all record.
- Cross-layer behavior is explicit and narrow. Research promotion snapshots approved tickers into
  strategy; market data returns grounded quantitative inputs; neither silently mutates research.
- Future enrichment should be additive: new reference tables, optional identifiers, and migrations
  when real cases require them. Do not pre-build issuer, exchange, share-class, or vendor models.

### Block 4 — Provenance Contract

**Problem:** citations need to be credible and reusable without turning v1 into a knowledge-graph or
claim-extraction system. A source attached directly to one theme or ticker is simple, but it duplicates
rows when the same filing or article supports multiple research objects and makes later claim-level
provenance awkward.

**Recommended contract:**

- Keep sources as first-class reusable rows in `fin_research_sources`: URL, title, publisher,
  `source_type`, publication date, first / latest access dates, and optional user-curated `trusted`.
- Associate a source with one or more themes / instruments through
  `fin_research_source_links(source_id, scope, key)`, with an optional association-specific relevance
  note, lifecycle status, and explicit `review_after` date for time-sensitive evidence.
- Let thesis markdown cite durable source IDs inline with a compact marker such as `[source:123]`.
  Markdown / HTML rendering resolves each marker to a human-readable numbered citation and emits a
  sources section.
- Structured quantitative fields continue to trace to their owning imported row, computed metric, or
  provider response. Do not duplicate numeric facts into prose-only citation records.
- Do not build structured `fin_research_claims` rows in v1. Add them later only if we need claim-level
  review, contradiction detection, or cross-source reasoning. The stable `source_id` contract leaves
  that path open.
- Treat `trusted` as a user-curated signal, not a global truth score or publisher allowlist.
- Store metadata and links in v1, not copied article / filing bodies. Defer full-text snapshots,
  extracted passages, semantic search, and embeddings until a demonstrated workflow needs them.
- Preserve an additive path for cached local copies of primary-source documents such as filings or
  investor presentations if URL durability or auditability becomes a real problem.

This adds one association table now, which is enough normalization to support reuse and future claim
links without designing a full research ontology.

**Maintenance and ad hoc research:**

1. Search results are ephemeral by default. Running an ad hoc web search does not persist every
   result. Persist only evidence the agent actually cites, links to a research object, or intentionally
   preserves with `finance.add_source(...)`.
2. Re-adding an exact URL upserts the existing source, updates `last_accessed_at`, and adds any missing
   theme / instrument link. Do not build URL canonicalization, content hashing, or duplicate-detection
   heuristics in v1.
3. Source freshness is explicit, not guessed. For time-sensitive evidence, set `review_after`. Briefs
   include due-for-review warnings from `finance.sources_due_for_review(...)`.
4. Re-checking a source uses `finance.review_source(...)`. Mark a link `superseded` when newer evidence
   replaces it or `archived` when it is no longer relevant. Keep old rows so historical briefs and
   citations remain explainable.
5. No background crawler, auto-refresh daemon, or universal review cadence in v1. A later reporting
   slice may surface the review queue periodically if manual review becomes burdensome.

**Decision:** approved 2026-05-31.

### Block 5 — Vault Note Convention

**Problem:** editable research notes and generated readouts need predictable locations without making
the filesystem a second structured database or hard-coding one machine's vault path.

**Recommended contract:**

- Resolve the vault root from `FINANCE_VAULT_ROOT`, falling back to the shared research-hub vault
  configuration when that exists. Fail clearly if no writable vault root is configured; do not commit
  personal vault contents into this repo.
- Store **relative paths** in SQLite so moving or syncing the vault does not require database rewrites.
- Keep editable thesis notes separate from replaceable generated readouts:

```text
finance/
  themes/
    compute.md
  instruments/
    NVDA.md
  readouts/
    themes/
      compute.md
      compute.html
```

- Use one editable markdown note per theme and per instrument when needed. Do not create separate note
  files for every source, event, or search result in v1; SQLite owns those facts.
- Keep front matter intentionally minimal:

```yaml
---
finance_scope: theme
finance_key: compute
---
```

- Do not mirror mutable SQLite state such as review statuses, source metadata, or prices into front
  matter. Rendered readouts pull that structure from tools each time.
- Thesis notes may link to related notes using ordinary relative markdown links. They cite source IDs
  inline using the approved `[source:123]` marker.
- `finance.set_research_note(...)` owns note-path creation and validation. `finance.render_theme_brief`
  replaces generated readouts atomically and never overwrites editable notes.
- Every generated readout must identify itself clearly as replaceable output:

```markdown
---
generated: true
generated_by: finance.render_theme_brief
---

> GENERATED ARTIFACT — DO NOT EDIT.
> Regenerate this file with `finance.render_theme_brief(...)`.
```

- Generated HTML readouts must include the same visible warning near the top of the page and a
  `<meta name="finance-generated" content="true">` marker.

This provides a stable convention while keeping the vault root configurable and the filesystem model
small.

**Decision:** approved 2026-05-31.

### Block 6 — Namespace And Module Ownership

**Problem:** finance research shares some patterns with the generic `research` hub, but its tables,
tools, and planner handoff are finance-specific. Putting finance behavior into the generic hub would
create cross-domain coupling; duplicating common filesystem helpers would also age poorly.

**Recommended contract:**

- Expose user-facing tools under the `finance.*` namespace and keep finance-owned tables, migrations,
  and behavior under `hubs/finance/`.
- Organize internal modules by responsibility rather than one large finance file:

```text
hubs/finance/
  __init__.py
  store.py
  research.py
  vault.py
  render.py
```

- `research.py` owns themes, instruments, source links, source review, briefs, and pure compose logic.
- `vault.py` owns finance-vault path resolution, note validation, and atomic file writes.
- `render.py` owns markdown / static-HTML rendering from a brief model. It does not query SQLite
  directly.
- Reuse generic helpers from `hubs/research` only after a real second consumer exists. Keep the initial
  finance implementation local, but design helper inputs generically enough that extraction later is
  mechanical.
- Keep registered `@tool` wrappers thin. Pure helpers accept plain values and return plain structures
  so storage, rendering, and future providers remain replaceable.

This keeps finance cohesive today and leaves a clean path to extract shared vault helpers later
without forcing a premature generic research framework.

**Decision:** approved 2026-05-31.

### Block 7 — Conviction Metadata

**Problem:** research benefits from recording a current judgment about a candidate, but a score can
look more objective than it is and can accidentally become a hidden allocation algorithm.

**Recommended contract:**

- Keep `conviction` optional and scoped to the **ticker-within-theme** edge, not the global instrument.
  The same company may have different relevance and conviction across themes.
- Use a deliberately coarse nullable `1..5` integer. Do not build weighted sub-scores, confidence
  formulas, or a ranking engine in v1.
- Require a non-empty `conviction_note` whenever a conviction score is stored. The rationale matters
  more than the number.
- Allow `map_instruments(...)` and `review_instrument(...)` to update conviction metadata.
- Show conviction + rationale in research briefs as descriptive context.
- Do not copy conviction into strategy target weights, sort deployment buys by it, or make it required
  for `approved` status. Any future use in allocation requires a separate explicit strategy-spec
  decision.

This captures useful judgment while preserving the hard boundary between research metadata and
deterministic planner policy.

**Decision:** approved 2026-05-31.

### Block 8 — Important Events Fast Follow

**Problem:** research benefits from knowing what matters next, but event coverage can expand into a
calendar-ingestion product quickly. The first cited theme flow should not depend on provider
automation.

**Recommended contract:**

- Keep events as a fast follow after the cited theme-brief path works end-to-end.
- Start with explicit manual instrument-level intake through `finance.record_event(...)` for
  `earnings` and `ex_dividend` events only. Add theme-scoped events and `product`, `lockup`, or other
  event types when an active research workflow needs them.
- Store each event in `fin_events` with scope (`theme | instrument`), key, type, date, date precision
  (`date | tentative`), optional market timing (`before_market | after_market | during_market |
  unknown`), lifecycle status (`scheduled | completed | cancelled`), cited `source_id`, note, and
  recorded / updated timestamps. V1 writes instrument-scoped rows; the schema preserves a narrow
  additive path for theme events later.
- Require a cited source for every persisted v1 event date. An ad hoc search may find the date, but
  `finance.add_source(...)` promotes the evidence before `finance.record_event(...)` persists it.
- Upsert the same scoped type + date rather than creating duplicates. Use `finance.review_event(...)`
  to confirm a tentative date, correct a changed date, mark completion, or preserve a cancellation.
- Show upcoming events in theme / instrument briefs. Keep past events as historical rows; default
  upcoming views show scheduled events only and exclude completed / cancelled rows.
- Treat each `fin_events` row as the current state of one event **occurrence**. Record material
  corrections in the note and cited source. Add a separate event-revision table later only if
  changed-date auditability becomes a real requirement.
- Do not build recurring-event rules, calendar sync, notifications, or automatic refresh in v1.
- Add an `EarningsProvider` behind the market-data layer only when manual upkeep or unreliable free
  data becomes a demonstrated pain point.

**Deferred provider enrichment (additive when `EarningsProvider` activates):**

```text
provider
provider_event_id       optional
fiscal_period_end       useful for earnings
first_seen_at
last_seen_at
```

Do not add these fields to the manual slice before validating the provider response shape. When the
provider activates, normalize API rows and upsert through the same event-domain path used by
`finance.record_event(...)`.

**Later analytics / simulation seam:**

```text
fin_events
  JOIN fin_price_bars
  ON ticker + trading sessions around event_date
  → deterministic event-response metrics or on-demand simulations
```

The research layer stores event occurrences and presents context. The market-data layer owns price
bars. A later analytics slice computes event responses such as next-session return, `[-5,+5]`
trading-session return, volatility around earnings, peer reactions, and theme-relative performance.
Use adjusted prices for historical returns and interpret the response window using `timing`.

When that slice is sharpened, account for trading days vs. calendar days, corporate actions,
tentative vs. confirmed dates, revised dates, provider gaps, look-ahead bias, and survivorship bias.
Do not persist simulation results as hand-authored markdown.

This keeps the first event slice useful and auditable without coupling research to a paid calendar
provider or scheduling system.

**Decision:** approved 2026-05-31.

### Block 9 — Graceful Quantitative Integration

**Problem:** the qualitative research flow should work before prices, metrics, filings, and
fundamentals are fully activated. But when quantitative data is missing, a brief must distinguish
“not available yet” from zero, stale data, or an unsupported request.

**Recommended contract:**

- Keep `theme_brief` and `instrument_brief` useful with themes, candidates, notes, sources, and events
  even when all quantitative providers are absent.
- Add optional brief slots for grounded `latest_price`, `metrics`, and `fundamentals`. Never synthesize
  a numeric placeholder or silently treat missing data as zero.
- Return explicit availability metadata so rendered readouts can explain gaps:

```text
quantitative_availability:
  prices:       available | missing | stale | not_configured
  metrics:      available | missing | not_configured
  fundamentals: available | missing | not_configured
```

- When a slot is populated, include source / as-of metadata from the owning market-data or provider
  layer. Research composes the data; it does not recompute or copy the underlying quantitative rows.
- In v1, surface per-instrument grounded fields only. Do not build computed cross-player screens,
  rankings, valuation models, or event-response analytics inside the research layer.
- Add comparisons later as a separate deterministic analytics capability once the relevant
  market-data tables exist and a concrete workflow justifies it.

This makes quantitative enrichment additive and visible while keeping the research lens useful on
day one.

**Decision:** approved 2026-05-31.

### Block 10 — Provider Activation Triggers

**Problem:** the architecture needs provider seams without turning the initial research workflow into
a provider-integration project. Free APIs still have maintenance cost, and paid providers should be
justified by recurring workflow value.

**Recommended contract:**

1. **Do not add a new provider dependency for qualitative research v1.** Manual cited research, theme
   notes, instrument notes, and generated briefs remain useful without API-backed fundamentals,
   estimates, or earnings intake.
2. **Keep provider implementation ownership in the market-data layer.** Research declares consumer
   requirements and reads stable interfaces. Market-data owns adapters, configuration, secrets,
   caching, retry behavior, and operational logging.
3. **Use a free daily-bar `PriceProvider` as the first market-data implementation.** The planner and
   research read `finance.prices(...)` / metrics, not a yfinance-specific API. A later provider switch
   must not require planner changes.
4. **Activate `edgartools` when an active thesis needs repeatable filing or XBRL-grounded financial
   extraction that manual cited reading cannot reasonably cover.** Treat SEC filings as the
   fundamentals source of record. Even though the library is free, activation still requires a small
   implementation pass for issuer identity, SEC access policy, caching, and retry behavior.
5. **Activate FMP only when a concrete recurring need appears.** Valid triggers include:
   - the event workflow needs a reliable earnings calendar often enough that manual upkeep is
     burdensome;
   - research repeatedly needs analyst estimates or consensus context;
   - the free price implementation exceeds the market-data reliability threshold;
   - analytics needs cleaner historical coverage without routine operator intervention.
6. **Treat FMP financial statements as screening context, not decision-grade ground truth.**
   Filing-grounded extraction remains authoritative for thesis-critical financial claims.
7. **Defer specialized providers until a named workflow demands them.** Revisit Polygon for intraday
   or professional-grade backtesting, Finnhub for real-time news or sentiment alerts, and sec-api for
   filing search or surveillance at scale.
8. **Run an activation sharpening pass before each provider integration.** Confirm the current API
   shape and commercial terms, then specify any schema enrichment, migrations, configuration,
   secrets, caching, retries, and failure reporting required by that adapter.

**Free price reliability threshold:** move off the initial free implementation when errors or empty
scheduled snapshots exceed approximately 10% over a rolling two-week window. Reporting or analytics
requirements may justify a switch earlier.

**Boundary:** this block records the activation policy and consumer expectations. The market-data
spec owns provider-adapter implementation details.

**Decision:** approved 2026-05-31.

---

## 11. Build order (incremental — narrowest real need first)

1. **Theme + instrument structure** — `set_theme` / `list_themes` / `get_theme` / `map_instruments` /
   `review_instrument`,
   `fin_themes` + `fin_instruments` + `fin_theme_instruments`. This alone delivers the exploration flow
   (industry → sub-segment → key players → reviewed watchlist). Highest leverage; build first.
2. **Research notes + sources** — `set_research_note` / `get_research_note` (vault) + `add_source` /
   `list_sources` / `review_source` / `sources_due_for_review` (`fin_research_sources` +
   `fin_research_source_links`). Preserves thesis + trusted analysis and surfaces explicit upkeep
   reminders (req #3).
3. **Compose the first artifact** — `theme_brief` + `render_theme_brief` markdown/static-HTML export
   with inline citations, candidate statuses, explicit gaps, and graceful degradation when quant
   fields are absent. Add `instrument_brief` after one theme flow works end-to-end.
4. **Planner handoff contract** — design the `promote_to_strategy` snapshot shape; build the strategy
   tables with the planner rather than letting research tables double as planner state.
5. **Important dates (fast follow)** — `record_event` / `upcoming_events` (`fin_events`). "What matters next."
6. **Compose tools expansion** — add optional grounded quantitative slots + explicit availability
   metadata to both briefs; degrade gracefully when quant fields are absent.
7. **(Deferred seams, trigger-gated)** — `FilingsProvider` (edgartools) when a thesis needs ground
   truth; `FundamentalsProvider`/`EarningsProvider` (FMP) when the lens is live; `metrics` once the
   snapshot slice exists.

Each step is a commit; pure helpers TDD'd; stop after step 1 + one end-to-end exploration path for
review (per the corpus pacing rule).

---

## 12. Boundaries

**Always:**
- Every thesis claim cites a source the tools can produce (`fin_research_sources`, a filing, a metric).
- The agent authors prose in the vault; tools persist structure + provenance. Keep imported data,
  generated analysis, and agent-authored thesis cleanly separated (corpus principle).
- Quantitative fields in a brief come from `fin_metrics` / `fin_price_bars` / price envelopes /
  provider-backed seams — never freehand.

**Ask first:**
- Activating a paid provider (FMP) or adding a dependency (edgartools, FMP client) — confirm + a
  sharpening pass, like Slice 2.
- Changing the vault path/front-matter convention after the first note is written.
- Anything that writes outside `fin_*` tables or the configured vault location.

**Never:**
- Invent a price, metric, fundamental, or earnings date the tools can't source.
- Treat FMP statement data as decision-grade (it's screening only — ground decisions in edgartools).
- Manually edit generated markdown / HTML readouts; update thesis notes or structured facts and
  regenerate them.
- Execute trades or place orders (inherited, absolute).
- Commit real provider API keys, an EDGAR identity, or vault contents that shouldn't be in the repo.

---

## 13. Status

Scaffold revised; **R1–R15 are the agenda.** The qualitative lens (themes → reviewed candidates →
notes/sources → cited brief) is fully buildable today on agent + persistence, with zero new
dependencies and no provider spend. Explicit promotion into versioned strategy state is designed
alongside this lens and built with the planner. The quantitative layers (metrics, fundamentals,
filings, events automation) stay deferred until their triggers fire.
