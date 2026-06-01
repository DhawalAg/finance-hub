# Finance Hub — Instrument Deep-Dive Lens (Ghost Requirements)

Last updated: 2026-05-31
Status: **ghost requirements** — a target-experience note, not a finalized contract

This note writes down the *kind of research we want an agent to do for a single company / ticker*,
as a concrete deliverable plus a catalogue of research lenses. It is deliberately written as a set of
**ghost requirements**: the lenses describe the experience we want, and each lens then *pulls* a
capability, tool, or provider seam into the existing finance specs. Read it as "here is the artifact
we want; here is what hub-hub must grow to support it" — it feeds
[research/spec.md](../../../docs/requests/finance/research/spec.md),
[market-data/spec.md](../../../docs/requests/finance/market-data/spec.md), and
[strategy/spec.md](../../../docs/requests/finance/strategy/spec.md); it does not replace them.

> Sibling to [requirements-dump.md](./requirements-dump.md): that note specced the *planner*; this one
> specs the *instrument deep-dive*, which the research spec already reserves as `instrument_brief(ticker)`
> — the second compose artifact after `theme_brief`.

---

## 1. What this is (and what it is not)

The user's working samples — a 4-part deep dive, a relative valuation table, a skeptic risk assessment —
are not new architecture. They are **research lenses**: the prose-and-judgment work the research spec
assigns to the *agent*, composed into the cited instrument dossier the spec already plans to build.

This note's job is to:
1. fix what "a great ticker deep-dive" *is* as a deliverable (the solutioning fit);
2. catalogue the lenses that make it great (the actual research);
3. back-derive the capabilities / tools / provider seams each lens requires (the ghost requirements);
4. recommend how this integrates into hub-hub without breaking its boundary decisions.

It is **not** a runnable skill or script yet. The form factor (skill vs prompt vs tool surface) is a
*conclusion* of this note, captured in §6 — not a premise.

---

## 2. Solutioning fit — what the final output is

The deliverable is a **cited markdown dossier for one instrument**, agent-authored, stored in the vault
at `finance/instruments/<TICKER>.md`, optionally rendered to a derived do-not-edit HTML readout. This is
exactly the `instrument_brief(ticker)` artifact in the research spec, and it inherits every boundary
decision already made there:

- **North star (extended to claims):** every thesis claim traces to a cited source — a filing, a
  trusted-source analysis, a price, or a computed metric — never model freehand.
- **Compose, don't freehand:** the dossier *composes* agent prose (the lenses) with tool-owned facts
  (events, sources, conviction, quantitative slots). The agent writes judgment; tools own the numbers,
  dates, and provenance.
- **Graceful degradation:** every quantitative slot (price, metrics, fundamentals, valuation) carries
  explicit availability state (`available | missing | stale | not_configured`). A missing number is
  *labelled missing*, never invented or zeroed.
- **Grade every number:** each quantitative claim is tagged **decision-grade** (primary source —
  edgartools/EDGAR) or **screening-grade** (aggregator — FMP, or agent-read-from-web). A screening-grade
  number can appear, but it must say so; no decision rests on it.
- **Markdown is canonical; HTML is derived** and marked *generated — do not edit*.

So "best fit" is a **structured, cited, regenerable dossier with a fixed section contract** — not a chat
transcript, not a dashboard. The lenses below *are* that section contract.

---

## 3. The lens catalogue — the actual research

Each lens carries: the question it answers, what a strong answer contains, the capability that grounds
it, its grade, and where its durable residue persists. The first three rows are the user's worked
samples; the rest extend them into a reusable deep-dive contract.

| # | Lens | Question it answers | Grounding capability | Grade | Durable residue |
|---|---|---|---|---|---|
| L1 | **Business model** | How exactly do they make money? Core product in plain English; revenue by segment/equation. | Agent + web; segment $ from 10-K (edgartools) | Prose; segment $ = decision-grade | Dossier prose + `[source:N]` |
| L2 | **Moat & competition** | Top 3 competitors; is there a structural / technological / patent advantage rivals lack? Switching costs, network effects. | Agent + web | Screening (qualitative) | Dossier prose + sources |
| L3 | **Financial health** | Revenue growth, margins, FCF, balance sheet, debt, dilution trend. | edgartools (statements) decision-grade; FMP screening | Mixed — label per number | Quant slot (`fundamentals`) + sources |
| L4 | **Relative valuation table** | P/S (TTM + fwd), EV/EBITDA, gross margin, YoY rev growth, Value/Growth score, vs 2+ peers. | Provider numbers + **deterministic comparison tool** | Screening (aggregator metrics) | Computed table (tool), not freehand |
| L5 | **Catalysts (next 12 mo)** | Upcoming launches, regulatory approvals, partnerships, earnings dates. | Agent + web; earnings/ex-div from `fin_events` / EarningsProvider | Mixed — dates cited | `fin_events` rows + dossier prose |
| L6 | **Bear / skeptic case** | 3-point risk read: accounting irregularities, customer concentration, competitive threats. Search bear articles. | Agent + web (bear pieces); concentration from 10-K risk factors (edgartools) | Opinion-grade (bear pieces) + decision-grade (filings) | Sources (`source_type='opinion'`, `trusted=0`) |
| L7 | **Asymmetry check** | Low valuation floor vs high growth ceiling? What must go right / wrong? | Agent synthesis over L1–L6 | Judgment (cites the lenses it rests on) | Dossier prose |
| L8 | **Theme fit** | How does this instrument participate in the user's theme(s)? Role, conviction + rationale. | Agent judgment; persists to theme edge | Research metadata | `fin_theme_instruments` (role, conviction) |
| L9 | **What matters next** | The dated calendar: earnings, ex-div, lockups, known events. | `fin_events` / `upcoming_events` | Dates cited | `fin_events` rows |
| L10 | **Open questions / invalidation** | What remains unclear; what would change the view. | Agent judgment | Judgment | Dossier prose |

**The judgment/fact line, made concrete.** L1–L2, L7, L10 are pure agent work (web + reasoning). L3–L5,
L9 rest on tool-owned numbers and dates. L6 mixes opinion sources with filing facts. L8 is the bridge to
the planner. This is the corpus reframe applied lens-by-lens.

### Worked example — the user's three samples, mapped

```
4-part deep dive       → L1 + L2 + L5 + L7   (business / moat / catalyst / asymmetry)
relative valuation tbl → L4                  (needs a real comparison capability — see DD-2/DD-3)
skeptic risk assessment→ L6                  (agent + web bear search, opinion-graded sources)
```

---

## 4. Ghost requirements — what each lens pulls into hub-hub

These are the capabilities the lenses *demand*. Each maps to an existing seam (mostly already designed)
or names a genuine gap to sharpen. IDs are `DD-*` to avoid colliding with the research spec's `R*`.

| ID | Requirement (pulled by) | Maps to existing spec | Status / gap |
|---|---|---|---|
| **DD-1** | An agent-authored, cited **instrument dossier** with a fixed lens contract | research spec `instrument_brief` + `set_research_note` + `render` | **Designed, unbuilt.** Add the *lens section contract* (this note §3) as the dossier template. |
| **DD-2** | **Cross-instrument comparison** (the valuation table L4) — peers in one table | research spec **R8** (cross-player screens = "fast follow") | **Gap.** L4 is precisely the deferred cross-player screen. Needs an explicit decision: is the table a deterministic tool or agent-composed-from-cited-cells? |
| **DD-3** | **Deterministic derived scores** (Value/Growth = P/S TTM ÷ rev-growth) | north star ("numbers trace to a tool result") | **Gap.** A computed ratio is arithmetic over numbers → must be a tool, not agent freehand. Implies a small `finance.compare(tickers, metrics)` capability. |
| **DD-4** | **Decision-grade fundamentals** (L1 segments, L3 statements, L6 concentration/red flags) | `FilingsProvider` (edgartools) | **Designed, deferred (R6/Block 10).** This dossier is a named trigger to activate edgartools. |
| **DD-5** | **Screening fundamentals + analyst estimates** (L3 ratios, L4 table, L7 growth ceiling) | `FundamentalsProvider` / `EstimatesProvider` (FMP) | **Designed, deferred.** Estimates are the one thing only an aggregator gives — needed for "forward P/S". |
| **DD-6** | **Prices + return/vol metrics** (valuation EV, momentum context) | `PriceProvider` / `MetricsProvider` (yfinance → FMP) | **Designed; price seam realized in planner slice.** Metrics deferred until `fin_price_bars` exists. |
| **DD-7** | **Extended event types** (L5 launches, approvals, partnerships, M&A) | research spec **R5 / Block 8** (v1 = `earnings` + `ex_dividend` only) | **Gap.** Catalysts need `product`, `regulatory`, `partnership` event types — or they stay as cited prose in L5. Decide per Block 8's additive path. |
| **DD-8** | **Opinion-source handling** (L6 bear articles) | provenance contract (Block 4): `source_type`, `trusted` flag | **Covered.** Bear pieces persist as `source_type='opinion'`, `trusted=0`; clearly labelled non-authoritative. |
| **DD-9** | **Theme-edge write** (L8 role + conviction) | `map_instruments` / `review_instrument` + `fin_theme_instruments` | **Covered.** Conviction stays research metadata; never auto-allocates (R9). |
| **DD-10** | **Scheduled / pushed delivery** of a dossier (if wanted) | reporting lens (deferred): Gmail/Drive/Calendar MCP + harness cron | **Deferred.** Out of scope for v1; the dossier is pull, not push, first. |

**The three real gaps are DD-2, DD-3, DD-7.** Everything else is either already designed or a deferred
seam this dossier gives a concrete reason to activate.

---

## 5. Insights worth flagging

1. **The valuation table is the spec's pressure point.** R8 deferred cross-player comparisons; the user's
   most-wanted artifact (L4) *is* one. This dossier is the demonstrated workflow that should pull R8
   forward — but only after per-instrument grounded fields (R8 v1) work. Recommend: ship L1–L3, L5–L10
   first on per-instrument data; add L4 as the comparison capability once `fundamentals` is grounded.
2. **A "score" is a tool, not a sentence.** "Value/Growth Score = P/S ÷ growth" looks like prose but is
   arithmetic over two numbers — by the north star it must be a tool computation with cited inputs, like
   the planner's `compute_plan`. This keeps the dossier defensible and prevents the agent from
   eyeballing a ratio.
3. **Grade, don't ban, screening numbers.** The dossier should *allow* aggregator/web numbers (otherwise
   it can't run today) but *label* them screening-grade, and reserve decision-grade for edgartools-sourced
   figures. This is the honest version of "every number traces to a source" while staying buildable now.
4. **Catalysts strain the event model.** L5 wants product/regulatory/partnership events the v1 `fin_events`
   enum doesn't have. Cheapest honest answer: keep those as **cited prose** in L5 for v1, and only add
   event types when a recurring "track these dated catalysts" workflow appears (per Block 8's additive
   path). Don't widen the enum speculatively.
5. **The dossier is buildable today, degrading gracefully.** L1, L2, L6, L7, L8, L10 need only agent + web
   + markdown persistence — zero new dependencies. The quantitative lenses (L3, L4, L5-dates, L9) slot into
   availability-gated holes. So a useful v1 ships before any provider spend, exactly as the research spec
   promises.

---

## 6. Recommended integration into hub-hub

**Where it lives.** This is the `instrument_brief` half of the research lens. Build it *after* the theme
flow (per the research spec build order), as the second compose artifact. The lens contract in §3 becomes
the dossier section template.

**Form factor (the answer to the question this note replaced).** Two complementary surfaces, not one:
- **Prompt/skill layer (the lens contract):** the §3 lenses + grading rules + section order are an
  *agent instruction*, best delivered as a reusable skill/prompt (e.g. `/finance-ticker <TICKER>`) in the
  same idiom as the `pm-*` skills. This is what makes the research repeatable and consistent.
- **Tool layer (the grounding):** `finance.set_research_note`, `add_source`, `record_event`,
  `instrument_brief`, and a new `finance.compare(...)` (DD-2/DD-3) own the facts, persistence, and
  deterministic math. These are the `@tool` wrappers the skill calls.

A standalone script is the wrong shape — it would re-implement judgment the agent should own. A pure prompt
with no tools can't satisfy the north star (no persistence, no deterministic scores). The pairing —
**skill for the lenses, tools for the facts** — is the fit.

**Build-order delta this note suggests** (additive to the research spec's order):
1. Land the theme flow + per-instrument `instrument_brief` (already planned).
2. Encode the §3 lens contract as the dossier template + a `/finance-ticker` skill (prompt layer).
3. Activate **edgartools** (DD-4) when the first thesis needs filing-grounded L1/L3/L6 — this dossier is
   the trigger.
4. Add `finance.compare(...)` + the Value/Growth score (DD-2/DD-3) once `fundamentals` is grounded, which
   pulls R8 forward deliberately.
5. Leave catalyst event-types (DD-7) and scheduled delivery (DD-10) deferred until a recurring need fires.

**Boundaries inherited (unchanged):** never invent a number a tool can't source; FMP statements are
screening-only; generated readouts are do-not-edit; discovery never mutates planner state; conviction is
never auto-allocation. The dossier strengthens these by making the grade of every claim explicit.

---

## 7. Open questions to sharpen (the agenda this note hands forward)

| # | Question | Lean |
|---|---|---|
| DDQ-1 | Is the valuation table (L4) a deterministic `finance.compare(...)` tool, or agent-composed from individually-cited cells? | **Tool** — a score is arithmetic; keep it defensible (DD-3). |
| DDQ-2 | Does L4 pull R8 (cross-player screens) forward, or do we ship per-instrument-only first? | Per-instrument first; add L4 once `fundamentals` is grounded. |
| DDQ-3 | Catalysts (L5): widen the `fin_events` enum (product/regulatory/partnership), or keep as cited prose? | **Cited prose in v1**; widen only on a recurring tracked-catalyst need. |
| DDQ-4 | What's the minimum peer-set logic for L4 — user-supplied peers, theme co-members, or agent-proposed? | Start user-supplied / theme co-members; agent-proposed needs its own grounding. |
| DDQ-5 | Where does "grade" (decision vs screening) live — per-number metadata, or a section-level convention? | Per-number label in prose + availability metadata in quant slots. |
| DDQ-6 | Does the dossier ever get pushed (email/Drive), or stay pull-only in v1? | Pull-only; delivery is the deferred reporting lens (DD-10). |

---

## 8. Status

Ghost requirements captured. Three real gaps identified (DD-2 cross-instrument comparison, DD-3
deterministic derived scores, DD-7 extended event types); the rest are already designed or are deferred
seams this dossier gives a concrete reason to activate. Recommended next step: when the research lens
reaches the `instrument_brief` slice, lift §3 into the dossier template and decide DDQ-1/DDQ-2 before
building L4.
