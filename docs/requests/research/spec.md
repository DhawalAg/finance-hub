# Finance Research Evidence — Working Spec

**Status:** V1 support contract for deployment recommendations
**Updated:** 2026-06-21

This spec defines the research evidence layer for the v1 deployment recommendation workflow. Research
owns theme discovery, candidate instruments, cited thesis notes, source provenance, source review, and
candidate readiness gaps. Strategy owns allocation intent, promotion, versioned strategy snapshots,
and dollar-denominated deployment recommendations.

The v1 product target is not a standalone research product. Research is the upstream evidence supplier
for:

```text
research themes + candidates + cited evidence
  -> explicit promotion into strategy
  -> deployment recommendation
```

Detailed source material remains in
[`requirements-dump.md`](../../../notes/finance-corpus/00-inbox/requirements-dump.md),
[`data-pipeline-spec.md`](../../../notes/finance-corpus/00-inbox/data-pipeline-spec.md), and
[`data-source-comparison.md`](../../../notes/finance-corpus/00-inbox/data-source-comparison.md). This
file is the durable research contract when those notes conflict.

## 1. V1 Responsibility

Research owns:

- free-form research themes and sub-themes;
- candidate instruments attached to those themes;
- candidate lifecycle state: `candidate | watching | approved | rejected`;
- editable thesis and dossier notes under `workspace/research/...`;
- reusable source metadata and links to themes or instruments;
- inline markdown citations using stored source IDs;
- source-review reminders for stale or time-sensitive evidence;
- explicit research gaps and candidate readiness summaries;
- promotion inputs for strategy.

Research does not own:

- portfolio snapshots, holdings, cash, deployment budgets, or allocation math;
- strategy sleeves, target weights, caps, or active strategy versions;
- price acquisition, price history, metrics, provider adapters, fundamentals caches, or quantitative
  provenance;
- trade execution, account placement, tax logic, or post-trade reconciliation.

The north star is:

> Every thesis claim traces to a cited source, stored research note, market-data fact, or deterministic
> tool result. The agent may synthesize the thesis; it must not invent evidence.

## 2. Deployment Evidence Contract

For v1 deployment recommendations, research must supply the cited-thesis portion of candidate
evidence. The planner may allocate dollars only to instruments that are both active-strategy eligible
and evidence-complete for the requested bucket.

Research supplies:

- `fin_instruments` entries for researched US-listed, USD-denominated stocks and ETFs;
- `fin_themes` and `fin_theme_instruments` edges that explain how a candidate maps to a theme;
- candidate status and rationale;
- editable theme or instrument notes containing the thesis;
- source rows and source links used by those notes;
- stable source IDs that markdown can cite as `[source:123]`;
- source freshness and review status;
- gap lists for missing thesis, stale sources, missing citations, or missing promotion state.

Market data supplies:

- latest price envelopes;
- one year of daily price history when available;
- 1m, 3m, 6m, and 1y returns;
- volatility, max drawdown, current drawdown, and 52-week-position context;
- compact provider-backed fundamentals and valuation context for one-time-buy eligibility;
- all provider adapters, secrets, retries, cache policy, and quantitative provenance.

Strategy supplies:

- active strategy version;
- sleeve targets and eligible instruments;
- portfolio snapshot and weight impact;
- DCA and one-time budgets;
- validation, warnings, blocks, and plan artifacts.

### Evidence Gates

Single stocks require a cited research thesis. Theme or sector ETFs require a cited thesis for the
sleeve or theme they express. Broad-market ETFs may use a compact ETF evidence pack instead of a full
cited thesis.

A candidate with missing or stale research evidence may still appear in `candidate_review`,
`watchlist_review`, or `allocation_review`. It cannot receive dollars in `deployment_draft` until the
required evidence exists and the candidate has been explicitly promoted into strategy.

One-time buys require a higher bar than DCA: the research thesis plus a written "why now" rationale
and compact valuation/fundamental context supplied through market-data seams.

## 3. Agent And Tool Boundary

The agent owns research judgment:

- deciding what themes to explore;
- reading filings, company materials, and trusted analysis;
- identifying key players;
- writing thesis notes;
- explaining why evidence matters;
- proposing whether a candidate should be watched, approved, or rejected.

Tools own durable structure:

- storing themes and candidate edges;
- writing and reading markdown notes at controlled paths;
- storing source metadata and source links;
- storing event dates with citations;
- composing grounded brief models;
- reporting missing or stale evidence.

No discovery or review tool mutates strategy state. Promotion is a separate user-confirmed action.

## 4. Domain Objects

### Theme

`fin_themes` stores research/exploration objects such as `compute`, `energy`, `model-providers`, or
`storage`.

V1 fields:

- `key`;
- `display_name`;
- `description`;
- `status = exploring | watching | archived`;
- `parent_key`;
- `note_path`;
- timestamps.

Themes are free-form and user-authored. Do not require GICS or another external taxonomy in v1.
Optional external tags can be added later when a real workflow needs them.

### Instrument

`fin_instruments` is the shared ticker reference used by research, market data, and strategy.

V1 is ticker-centric:

- US-listed;
- USD-denominated;
- `type = stock | etf`;
- `instrument_role = broad_market_etf | theme_etf | single_stock`.

Research may discover and annotate instruments. Strategy snapshots approved instruments into eligible
strategy state. Market data stores bars, metrics, and fundamentals for instruments. Do not expand
`fin_instruments` into an issuer/security/share-class master record until a real case requires it.

### Theme-Instrument Edge

`fin_theme_instruments` is the key-player and watchlist edge:

- `theme_key`;
- `ticker`;
- `status = candidate | watching | approved | rejected`;
- `role`;
- optional `conviction`;
- required `conviction_note` when conviction is present;
- free-form note.

Conviction is descriptive research metadata only. It is not copied into strategy weights and is not
used by deployment math.

### Research Note

Editable research prose lives as markdown under `workspace/research/...`. SQLite stores relative note
paths and structured metadata; it does not store thesis prose as a large text blob.

Default paths:

```text
workspace/research/themes/{theme_key}.md
workspace/research/instruments/{ticker}.md
```

Keep front matter minimal:

```yaml
---
finance_scope: theme
finance_key: compute
---
```

Do not mirror mutable SQLite state such as review status, prices, metrics, or source metadata into
front matter.

### Source

`fin_research_sources` stores reusable source metadata:

- URL;
- title;
- publisher;
- source type;
- publication date;
- first and latest access time;
- optional user-curated `trusted` flag.

`fin_research_source_links` attaches sources to themes or instruments, with association-specific
relevance notes, lifecycle status, and optional review reminders.

Markdown thesis notes cite sources inline:

```markdown
The thesis claim appears here. [source:123]
```

Do not build structured claim rows in v1. Add `fin_research_claims` later only if claim-level review,
contradiction handling, or cross-source reasoning becomes a real workflow.

### Event

`fin_events` stores cited event occurrences such as earnings and ex-dividend dates. Events are useful
for "what matters next" but are not required for the minimum deployment evidence loop unless a
candidate's thesis or one-time rationale depends on that event.

V1 event intake is manual and citation-backed. Provider-backed calendar ingestion is deferred to the
market-data layer.

## 5. Tools

All user-facing tools live under `finance.*` with thin wrappers over pure helpers in
`src/finance_hub/`.

### Build-Now Evidence Tools

| Tool | Purpose |
|---|---|
| `finance.set_theme(...)` | Create or update a theme. |
| `finance.list_themes(...)` | List themes by status or parent. |
| `finance.get_theme(...)` | Read one theme with instruments, sources, notes, and events. |
| `finance.map_instruments(...)` | Attach candidate instruments to a theme. |
| `finance.review_instrument(...)` | Mark a candidate `watching`, `approved`, or `rejected` with rationale. |
| `finance.set_research_note(...)` | Write an editable theme or instrument note under `workspace/research/...`. |
| `finance.get_research_note(...)` | Read the editable note back for grounding and iteration. |
| `finance.add_source(...)` | Upsert a cited source and link it to a theme or instrument. |
| `finance.list_sources(...)` | Read source metadata and active links. |
| `finance.review_source(...)` | Mark a source link active, superseded, or archived and update review metadata. |
| `finance.sources_due_for_review(...)` | Surface time-sensitive sources whose review date has passed. |
| `finance.candidate_evidence(...)` | Return one candidate's research evidence, citations, readiness state, and gaps. |
| `finance.research_priorities(...)` | Recompute missing or stale research evidence across current candidates. |

`candidate_evidence` is the minimum v1 read contract strategy needs from research. It should return
stable references, not rendered prose only.

### Compose And Readout Tools

Generated readouts are useful review artifacts, but they are not the v1 deployment release blocker.
Build them after the minimum evidence loop can support `candidate_review` and promotion.

| Tool | Purpose | V1 stance |
|---|---|---|
| `finance.theme_brief(...)` | Compose a grounded theme view from themes, candidates, notes, sources, events, and optional quant slots. | Follow-on after evidence loop. |
| `finance.render_theme_brief(...)` | Render generated markdown and static HTML readouts under `workspace/research/readouts/...`. | Follow-on research UX. |
| `finance.instrument_brief(...)` | Compose a deep-dive view for one ticker. | Deferred until theme/candidate evidence proves useful. |

Generated readouts must carry a visible generated-artifact warning and be replaceable output. Editable
notes remain the source of research prose.

### Strategy Handoff

`finance.promote_to_strategy(...)` is designed at the research/strategy boundary and built with the
strategy slice. It snapshots user-approved research candidates into planner-owned strategy state.

Promotion is explicit and versioned. Later research edits do not mutate already-created strategy
versions.

## 6. Data Model

Finance-owned migrations use the finance migration table and normal SQLite constraints, matching the
other finance specs.

```sql
CREATE TABLE fin_themes (
  key          TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  description  TEXT,
  status       TEXT NOT NULL DEFAULT 'exploring',
  parent_key   TEXT,
  note_path    TEXT,
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL,
  FOREIGN KEY (parent_key) REFERENCES fin_themes(key),
  CHECK (status IN ('exploring','watching','archived'))
);

CREATE TABLE fin_instruments (
  ticker          TEXT PRIMARY KEY,
  type            TEXT NOT NULL DEFAULT 'stock',
  instrument_role TEXT NOT NULL,
  display_name    TEXT,
  note_path       TEXT,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL,
  CHECK (type IN ('stock','etf')),
  CHECK (instrument_role IN ('broad_market_etf','theme_etf','single_stock'))
);

CREATE TABLE fin_theme_instruments (
  theme_key       TEXT NOT NULL,
  ticker          TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'candidate',
  role            TEXT,
  conviction      INTEGER,
  conviction_note TEXT,
  note            TEXT,
  added_at        TEXT NOT NULL,
  updated_at      TEXT NOT NULL,
  PRIMARY KEY (theme_key, ticker),
  FOREIGN KEY (theme_key) REFERENCES fin_themes(key),
  FOREIGN KEY (ticker) REFERENCES fin_instruments(ticker),
  CHECK (status IN ('candidate','watching','approved','rejected')),
  CHECK (conviction IS NULL OR conviction BETWEEN 1 AND 5),
  CHECK (conviction IS NULL OR (conviction_note IS NOT NULL AND length(trim(conviction_note)) > 0))
);

CREATE TABLE fin_research_sources (
  id                INTEGER PRIMARY KEY,
  url               TEXT NOT NULL UNIQUE,
  title             TEXT,
  publisher         TEXT,
  source_type       TEXT,
  published_on      TEXT,
  trusted           INTEGER NOT NULL DEFAULT 0,
  first_accessed_at TEXT NOT NULL,
  last_accessed_at  TEXT NOT NULL,
  CHECK (trusted IN (0,1))
);

CREATE TABLE fin_research_source_links (
  source_id    INTEGER NOT NULL,
  scope        TEXT NOT NULL,
  key          TEXT NOT NULL,
  note         TEXT,
  status       TEXT NOT NULL DEFAULT 'active',
  review_after TEXT,
  reviewed_at  TEXT,
  linked_at    TEXT NOT NULL,
  PRIMARY KEY (source_id, scope, key),
  FOREIGN KEY (source_id) REFERENCES fin_research_sources(id),
  CHECK (scope IN ('instrument','theme')),
  CHECK (status IN ('active','superseded','archived'))
);

CREATE INDEX idx_fin_research_source_links_review
  ON fin_research_source_links(status, review_after);

CREATE TABLE fin_events (
  id             INTEGER PRIMARY KEY,
  scope          TEXT NOT NULL,
  key            TEXT NOT NULL,
  event_type     TEXT NOT NULL,
  event_date     TEXT NOT NULL,
  date_precision TEXT NOT NULL DEFAULT 'date',
  timing         TEXT NOT NULL DEFAULT 'unknown',
  status         TEXT NOT NULL DEFAULT 'scheduled',
  source_id      INTEGER NOT NULL,
  note           TEXT,
  recorded_at    TEXT NOT NULL,
  updated_at     TEXT NOT NULL,
  FOREIGN KEY (source_id) REFERENCES fin_research_sources(id),
  UNIQUE (scope, key, event_type, event_date),
  CHECK (scope IN ('instrument','theme')),
  CHECK (event_type IN ('earnings','ex_dividend')),
  CHECK (date_precision IN ('date','tentative')),
  CHECK (timing IN ('before_market','after_market','during_market','unknown')),
  CHECK (status IN ('scheduled','completed','cancelled'))
);
```

Deferred or externally owned tables:

- `fin_price_bars`: market-data acquisition;
- `fin_metrics`: market-data analytics;
- compact `fin_fundamentals` screening cache: market-data/provider layer;
- strategy tables: strategy/planning.

## 7. Source And Citation Rules

Search results are ephemeral by default. Persist only evidence the agent actually cites, links to a
research object, or intentionally preserves with `finance.add_source(...)`.

Exact URL upsert is sufficient in v1. Do not build URL canonicalization, content hashing, duplicate
detection, crawler refresh, full-text snapshots, embeddings, or a publisher allowlist.

Source freshness is explicit:

- set `review_after` for time-sensitive evidence;
- show due-for-review warnings in evidence tools and briefs;
- mark links `superseded` when newer evidence replaces them;
- keep old source rows so historical citations remain explainable.

`trusted` is a user-curated signal, not a truth score. It can help prioritize review, but it does not
turn a claim into a fact without the underlying citation.

## 8. Quantitative Integration

Research composes quantitative context but does not compute it.

Candidate evidence and briefs may include optional slots:

```text
latest_price
metrics
fundamentals
upcoming_events
quantitative_availability
```

When a quantitative slot is present, it must include source, grade, and as-of metadata from the owning
market-data layer. When a slot is absent, return explicit availability:

```text
available | missing | stale | not_configured
```

Never render missing quantitative data as zero. Never let the agent invent a price, metric,
fundamental, valuation multiple, or event date.

Provider ownership remains in market data. Research may declare that a workflow needs fundamentals,
filings, or earnings dates, but adapters, secrets, retry policy, caching, and operational logs belong
to the market-data specs.

## 9. Generated Artifacts

`workspace/` is private runtime output and ignored by git because it may contain personal financial
context.

Default research artifact paths:

```text
workspace/research/themes/
workspace/research/instruments/
workspace/research/candidates/
workspace/research/watchlists/
workspace/research/priorities/
workspace/research/readouts/
```

Generated markdown includes minimal identity/provenance front matter only:

```yaml
---
generated: true
generated_by: finance.render_theme_brief
generated_at: 2026-06-21T10:15:00-05:00
artifact_type: theme_brief
theme_key: compute
---
```

Every generated markdown or HTML artifact must show:

```markdown
> GENERATED ARTIFACT - DO NOT EDIT AS SOURCE OF TRUTH.
> Regenerate this file from the finance tool that produced it.
```

Do not use generated artifacts as a database. Notes, source metadata, status, prices, metrics, and
promotion state stay in markdown notes or SQLite/tool output according to their ownership.

## 10. Build Order

The v1 research build should support deployment recommendations before broad research UX:

1. Theme, instrument, and candidate persistence.
2. Research note and source persistence with inline source-ID citations.
3. `candidate_evidence(...)` and `research_priorities(...)` gap reporting.
4. Strategy promotion handoff shape, implemented with the strategy slice.
5. Generated `theme_brief` and `watchlist_review` readouts.
6. Manual cited events for "what matters next."
7. `instrument_brief` and richer research UX.
8. Provider-backed filings, fundamentals, earnings calendars, and cross-player analytics when their
   market-data activation gates fire.

The first deployable slice is evidence plumbing, not a dashboard or generalized research engine.

## 11. Deferred Work

Deferred until a concrete workflow needs it:

- structured claim rows;
- full-text source snapshots;
- semantic search or embeddings;
- background crawling or auto-refresh;
- theme dashboards;
- generated static HTML as a release blocker;
- `instrument_brief` as the first artifact;
- cross-player screens, rankings, valuation models, and event-response analytics inside research;
- issuer/security/share-class normalization;
- paid provider activation by default.

## 12. Boundaries

Always:

- cite thesis claims with stored source IDs or grounded tool evidence;
- keep research state separate from strategy state;
- write editable research prose under `workspace/research/...`;
- store structured facts and relationships in SQLite;
- surface gaps instead of silently filling them.

Ask first:

- adding a paid provider or new provider dependency;
- changing the `workspace/research/` path convention after notes exist;
- expanding source capture beyond metadata and links;
- making generated readouts part of the first deployment release.

Never:

- mutate strategy from discovery or candidate review;
- turn research conviction into allocation math;
- invent prices, metrics, fundamentals, filings, event dates, or citations;
- treat aggregator fundamentals as decision-grade ground truth;
- commit real holdings, budgets, provider keys, SQLite databases, or generated `workspace/` artifacts;
- execute trades or place orders.

## 13. Readiness

Research is v1-ready when it can answer these questions for any candidate:

- What theme or sleeve does this candidate express?
- What is its current research status?
- Where is the cited thesis note?
- Which source IDs support the thesis?
- Are any sources stale or due for review?
- Is promotion into strategy still required?
- Which evidence gaps block DCA eligibility or one-time-buy eligibility?
- Which missing quantitative inputs must be supplied by market data?

That is enough for the deployment recommendation workflow to proceed. Rich theme briefs and
instrument dossiers can grow after this minimum evidence loop works.
