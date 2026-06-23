# Finance Hub — Bootstrapping & Local Setup — Working Spec

**Status:** Sharpened via `/grill-with-docs`; ready for PRD synthesis
**Updated:** 2026-06-23

This spec defines the **bootstrapping** work: the changes needed to take finance-hub from
"importable Python package with a working tool registry" to "a person can install it, point it at
their real Fidelity export, run an end-to-end DCA deployment flow, and drive it from an MCP client."

It is operational/setup scope, not a new domain workflow. The domain contracts already live in
[`strategy/spec.md`](../strategy/spec.md), [`research/spec.md`](../research/spec.md), and
[`market-data/spec.md`](../market-data/spec.md). This spec only closes the gap between those
contracts and a usable local install.

## 1. Why This Exists

Slices 0–11 built the deployment recommendation pipeline, but several seams that a real user (or an
MCP client) needs are unwired or were built against an assumed data shape that does not match reality:

1. **No registered Fidelity CSV import tool.** Import is Python-only (`FidelityPortfolioCsvAdapter`),
   unreachable from `finance run` or MCP.
2. **The CSV adapter is wrong against real Fidelity exports.** See §4 — the `Type` column does not
   carry the security type, so every equity is silently misclassified as cash and the planner sees an
   empty portfolio.
3. **Price provider is not wired at startup.** Any market-data call from the CLI/MCP raises
   `LookupError: no PriceProvider configured` until Python code calls
   `factories.set_price_provider(...)`.
4. **No `.env` loading and no `.env.example`.** Secrets and config must be exported into the shell by
   hand; MCP clients launch the server with a minimal environment.
5. **No setup diagnostic.** Nothing answers "is this install ready, and if not, what do I fix?"
6. **Fundamentals have no live HTTP client.** The EODHD / Alpha Vantage adapters only replay recorded
   fixtures. This blocks **one-time buys** (which require fundamentals); **DCA works without them.**

## 2. Scope

### In scope

- `.env` self-loading in both the `finance` CLI and the `finance-mcp` server (via `python-dotenv`).
- A committed `.env.example` documenting every variable.
- Lazy price-provider auto-wiring driven by `FINANCE_HUB_PRICE_PROVIDER` (default `yfinance`).
- A correctness fix to `FidelityPortfolioCsvAdapter`'s security-type classification (§4).
- A registered `finance.import_portfolio_csv` tool that auto-extracts `as_of` and returns a rich
  import summary (§5).
- A read-only `finance check` diagnostic command with a `--live` opt-in (§6).
- MCP client registration documentation + a README quickstart (§7).

### Explicitly out of scope (deferred, named follow-ups)

- **Live fundamentals HTTP client (EODHD / Alpha Vantage).** This is the **immediate next step** after
  bootstrapping — it unlocks one-time buys — but it is its own spec and its own issues. Bootstrapping
  ships a DCA-complete flow first.
- **A `finance init` mutator** (create DB, scaffold workspace, copy `.env.example` → `.env`).
  `finance check` is read-only and only *reports* what to fix; a separate `init` command can mutate
  later.
- Live brokerage/bank sync, trade execution, non-Fidelity adapters.

## 3. Environment & Provider Wiring

### Decisions

- **Both entrypoints self-load `.env`** at startup using `python-dotenv` (added as a core
  dependency). One source of truth for secrets; the MCP client config stays a clean pointer to the
  binary and does not duplicate secrets. An optional `FINANCE_HUB_ENV` overrides the `.env` path.
- **Price-provider wiring is lazy.** Startup registers *how* to build the provider; yfinance (heavy:
  pulls pandas + network stack) is only imported on the first `get_price_provider()` call. A
  research-only or strategy-only session never imports the market-data stack. This requires a small
  factories change (e.g. `set_price_provider_factory(callable)` or lazy construction from a registered
  name) since today `set_price_provider` takes an already-built instance.
- **`FINANCE_HUB_PRICE_PROVIDER` semantics:** unset → `yfinance` (zero-config happy path);
  `none` → provider stays unconfigured (offline/tests); any other name → selects that provider
  (future `polygon`, etc.).

### `.env.example` contents

```dotenv
# Optional — only needed for the in-process LLM helper (runtime/llm.py).
# Not required for deterministic tools, and irrelevant in the MCP use case
# (Claude itself is the reasoning layer there).
ANTHROPIC_API_KEY=

# Price provider selection. Unset defaults to yfinance (no API key needed).
# Set to "none" to disable price fetching (offline / tests).
# FINANCE_HUB_PRICE_PROVIDER=yfinance

# Storage overrides (sensible defaults if unset).
# FINANCE_HUB_DB=./finance-hub.db
# FINANCE_HUB_WORKSPACE=./workspace

# Override where the CLI/MCP server looks for the .env file.
# FINANCE_HUB_ENV=

# Fundamentals providers — NOT YET WIRED (live client pending; see follow-up).
# Stubbed here so the keys are documented ahead of the fundamentals slice.
# EODHD_API_KEY=
# ALPHA_VANTAGE_API_KEY=
```

`.env` is gitignored; `.env.example` is the committed template.

## 4. Fidelity CSV Classification Fix

**This is a correctness bug in Slice 7, not new feature work.** It is in this spec but is its own
issue so git history records the fix honestly.

### The problem (verified against a real export)

A real `Portfolio_Positions_*.csv` has this header:

```text
Account Number, Account Name, Symbol, Description, Quantity, Last Price, Last Price Change,
Current Value, Today's Gain/Loss Dollar, Today's Gain/Loss Percent, Total Gain/Loss Dollar,
Total Gain/Loss Percent, Percent Of Account, Cost Basis Total, Average Cost Basis, Type
```

The `Type` column holds the **account registration** (`Cash` / `Margin`) — **not** the security type.
Every equity row (WMT, NVDA, AVGO, …) shows `Type = Cash`. There is **no security-type column.**

The current adapter maps `Type` directly to `asset_type` via `_FIDELITY_TYPE_MAP` and treats
`{stock, etf}` as supported. Against a real file, **every holding maps to `cash` → unsupported →
the planner sees zero positions.**

### The fix

- **Infer security type from `Description`** with a small, testable ruleset:
  - cash-sweep / non-position patterns (`FCASH**`, `HELD IN FCASH`, `Pending activity`) → cash /
    skip;
  - `Description` contains `ETF` → `etf`;
  - otherwise, a row with a real ticker → `stock`.
- **Repurpose the `Type` column as `account_registration`** (`cash` / `margin`) — genuine metadata we
  are currently misreading.
- **Skip cleanly:** the trailing legal-disclaimer paragraphs, the `Date downloaded …` line, blank
  separators, and `Pending activity`.
- **Build against the real sample as the test fixture** (a sanitized copy of
  `Portfolio_Positions_Jun-23-2026.csv`), not an assumed shape.

### `as_of` extraction

The CSV's final line is the only timestamp it carries:

```text
"Date downloaded Jun-23-2026 3:42 p.m ET"
```

Format: `Date downloaded {Mon}-{DD}-{YYYY} {H}:{MM} {a.m|p.m} ET` — quoted, abbreviated month,
`a.m`/`p.m` (periods, no trailing period), literal `ET` (map to America/New_York).

- The import tool **auto-extracts this as `as_of`** (it is the most honest "when was this portfolio
  true" signal — position `Current Value`s reflect prices at download time).
- An explicit `as_of` argument, if provided, **overrides** it.
- If the line is missing **and** no explicit `as_of` is given → **hard error** (never silently stamp
  "now"). Day-level precision is sufficient for the planner's freshness logic.

## 5. `finance.import_portfolio_csv` Tool

Wraps the fixed adapter as a registered tool (reachable from `finance run` and MCP).

```python
finance.import_portfolio_csv(*, csv_path: str, as_of: str | None = None) -> dict
```

- `as_of` optional; auto-extracted from the CSV download line when omitted (§4), explicit value wins,
  error if neither.
- Returns a **rich summary** so the import shows its work (classification was silently wrong before):

```json
{
  "snapshot_id": "snap_...",
  "as_of": "2026-06-23T15:42:00-04:00",
  "as_of_source": "csv_download_timestamp",
  "supported": {"count": 17, "tickers": ["WMT", "NVDA", "..."]},
  "cash": {"count": 1, "value": "1234.56"},
  "unsupported": {"count": 0, "tickers": []},
  "skipped_rows": 3
}
```

`as_of_source` is `csv_download_timestamp` or `explicit_override`.

## 6. `finance check` Command

A **read-only** diagnostic — reports, never mutates. Each line is green / yellow / red with a
fix hint. Default run is network-free; `--live` opts into real provider pings (mirrors the existing
`-m live` pytest convention).

| Check | Severity logic |
|---|---|
| Package import / Python version | red if `finance_hub` not importable or Python too old |
| SQLite store | green with migration count + latest version; red if unreachable |
| Workspace dir | green if exists/writable; yellow "created on first write" otherwise |
| Price provider (wiring) | green if installed + wired; red if selected provider missing |
| Price provider (`--live`) | opt-in real fetch (e.g. `SPY`); off by default |
| Fundamentals provider | **yellow** — "not configured; DCA works, one-time buys blocked until the fundamentals client lands" |
| `ANTHROPIC_API_KEY` | **yellow/optional** — only needed by the in-process LLM helper; irrelevant for deterministic tools and the MCP use case |
| Env vars | report which of `FINANCE_HUB_DB`, `FINANCE_HUB_WORKSPACE`, `FINANCE_HUB_PRICE_PROVIDER` are set vs defaulted |

Each non-green line prints the exact remediation command rather than just flagging a problem.

## 7. MCP Setup & Quickstart Docs

- An MCP client registration snippet (the `.mcp.json` / client-config three-liner pointing at the
  `finance-mcp` binary), relying on the server's `.env` self-load so no secrets live in the MCP
  config.
- A README quickstart tying the whole flow together: install → `cp .env.example .env` → `finance
  check` → `finance.import_portfolio_csv` → research → `promote_to_strategy` → `snapshot` (prices) →
  `generate_deployment_plan` → `plan_readiness_check` → `approve_deployment_plan`.

## 8. Implementation Issues

Dependency order: **#1 → (#2 → #3), #4, #5** can parallelize once #1 lands.

1. **`.env` loading + provider auto-wiring + `.env.example`.** `python-dotenv` core dep; self-load in
   CLI + MCP; lazy yfinance factory with `FINANCE_HUB_PRICE_PROVIDER` semantics; committed
   `.env.example`. Foundation everything else assumes.
2. **Fidelity adapter classification fix.** Infer security type from `Description`; repurpose `Type`
   as `account_registration`; parse the `Date downloaded` timestamp; sanitized real-sample fixture.
   (Correctness bug in Slice 7.)
3. **`finance.import_portfolio_csv` tool.** Wraps the fixed adapter; auto-`as_of`; rich summary.
   Depends on #2.
4. **`finance check` command.** Read-only diagnostic; `--live` opt-in. Depends on #1.
5. **MCP setup documentation + README quickstart.**

## 9. Decisions Pinned (Grilling Record)

- Fundamentals live client is **deferred but the explicit immediate next step**, its own spec/issues.
- `finance check` is **read-only**; a `finance init` mutator is a separate future command.
- `finance check` reports fundamentals and `ANTHROPIC_API_KEY` as **yellow**, naming the exact
  consequence; never cries wolf with all-red.
- Price-provider check is **wiring-only by default**, `--live` opt-in.
- `FINANCE_HUB_PRICE_PROVIDER` unset → yfinance; `none` → disabled; named → selects.
- Provider instantiation is **lazy** (no yfinance import for non-price sessions).
- CSV `as_of` is **auto-extracted** from the download line; explicit override wins; **error** if
  neither (no silent "now").
- Security type is **inferred from `Description`**; `Type` becomes `account_registration`; built
  against the real sample fixture.
- The adapter fix **stays in this spec as its own issue** (honest history).
- Import tool returns a **rich summary**, not a bare `snapshot_id`.
- Both entrypoints **self-load `.env`** via **`python-dotenv`** (core dependency).
- `.env.example` includes **commented-out** EODHD / Alpha Vantage stubs ahead of the fundamentals
  slice.
