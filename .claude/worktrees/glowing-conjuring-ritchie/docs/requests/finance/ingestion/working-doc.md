# Finance Ingestion — Decision Ledger

**Purpose:** concise record of design decisions and superseded proposals.
**Authoritative implementation contract:** [`spec.md`](./spec.md)
**Started:** 2026-05-30
**Last updated:** 2026-05-31

This file records why the design changed. It is not a second implementation spec.

---

## Current Status

| Area | Status | Result |
|---|---|---|
| Scope | decided | Slice 1 = statement-driven budget ingestion; Slice 2 holdings/prices deferred |
| Sources | decided | Chase CSV + agent extraction now; SimpleFIN and Plaid later only if needed |
| Money semantics | decided | Integer cents; cash-flow transaction signs; net-worth balance signs |
| Dates | decided | Required `posted_date`; optional `authorized_date` |
| Storage | decided | Raw source evidence separate from canonical facts |
| Idempotency | decided | Source-record identity separate from canonical candidate matching |
| Accounts | decided | Explicit subtype, lifecycle, currency, and budget-inclusion config |
| Schema | decided | Finance-owned migrations, SQLite FKs, `CHECK`s, and focused indexes |
| Categories | decided | Category and budget flow type computed on read with stored overrides |
| Reconciliation | decided | Same delta equation for assets and liabilities |
| Transfers | decided | Narrow two-leg links; no full ledger |
| Budget output | decided | `historical_surplus`, not premature `deployable_capital` |
| Corrections | decided | Append-only supersession and narrow inspection/repair tools |
| Testing | decided | `pytest` via `uv`; synthetic fixtures only |
| Slice 2 | deferred | Sharpen separately before holdings/prices implementation |

---

## Decision Log

### 2026-05-30 — Initial Reframe

- SQLite is the single source of truth for financial numbers. Drop Beancount as storage architecture;
  reuse parser ideas only.
- Recover Beancount's valuable safety property as `fin_balances` plus `finance.balance_check`.
- Acquisition is upstream of transformation. `import_csv` and `record_transactions` are the first two
  input paths feeding one engine.
- Source rollout is phased:
  - Slice 1: manual CSV and agent extraction.
  - Later: SimpleFIN for Chase/Amex transactions if manual cadence becomes annoying.
  - Later: Plaid or manual Positions CSV for Fidelity holdings.
- Money uses integer cents, never SQLite `REAL`.
- Categories compute on read. Persist only per-row overrides.
- Add a durable issue inbox so problematic rows are visible rather than silently dropped.
- Link internal-transfer legs rather than introducing a full double-entry ledger.
- Park Slice 2 scheduling and monitoring details until the price-snapshot slice is active.

### 2026-05-31 — Second-Pass Correctness Review

#### S1 — Canonical Money Semantics

- Transactions use the user's cash-flow perspective:
  `negative = value leaving`, `positive = value arriving`.
- Balances use the user's net-worth perspective:
  assets positive when owned; liabilities negative when owed.
- Normalize source-native values at the adapter boundary.
- Reconcile every account with:

```text
ending_balance_cents = starting_balance_cents + sum(transaction.amount_cents)
```

- Both transaction signs are valid for assets and liabilities. Do not reject rows merely because of
  direction and account kind.

#### S2 — Canonical Dates

- Store required `posted_date` for reconciliation, summaries, filtering, and fallback matching.
- Preserve optional `authorized_date`.
- Import posted transactions only; pending authorizations are deferred.

#### S3 — Tool-Boundary Money

- Agent-facing writes accept decimal-string dollars such as `"-12.34"`.
- Parse with `Decimal`; reject more than two fractional digits.
- Persist, compute, and return authoritative integer-cent fields. Do not pass floats through the
  statement-money path.

#### L1 — Import Lineage

- Add `fin_ingest_runs`: one row per committed import batch.
- Add `fin_source_records`: one row per raw input row with raw and normalized JSON, source locator,
  disposition, and canonical transaction link.
- Store filename and file hash, not statement contents. Raw row JSON remains only in local gitignored
  SQLite.
- `dry_run=True` writes nothing.

#### D1 — Identity And Matching

- Preserve every source row before canonical matching.
- Exact source identity handles re-import idempotency:
  stable external ID when guaranteed; file hash plus row number for CSV; batch key plus locator for
  agent extraction.
- Canonical candidate matching is separate and non-unique.
- Auto-link only exact unambiguous overlaps. Never silently discard a plausible charge.

#### M1 — Migration Ownership

- Add `fin_schema_migrations`.
- Run missing ordered finance migrations transactionally and record versions only after success.
- Do not use database-global `PRAGMA user_version`; finance owns explicit migration state in
  `fin_schema_migrations`.

#### A1 — Account Configuration

- Expand accounts with `subtype`, `currency`, `active`, `include_in_budget`, `opened_on`, `closed_on`,
  and `created_at`.
- Use account lifecycle dates when assessing completeness.
- Avoid hardcoded report scope by account name.

#### DB1 — Schema Safeguards

- Enable SQLite foreign keys on every connection.
- Add FKs, `CHECK`s, and query-path indexes.
- Avoid cascade-deleting canonical financial facts.
- Keep the scope narrow: cheap baseline protections now, generalized automation later only if needed.

#### T1 — Transfers

- Add `fin_transfer_groups`; keep `fin_transactions.transfer_group_id`.
- Explicit linking names existing transaction IDs.
- Auto-match only one-to-one exact-amount, opposite-sign, nearby-date candidates with transfer-like
  evidence.
- Quarantine ambiguity and missing legs. Defer split and multi-leg transfers.

#### B1 — Category Vs. Flow Type

- Category answers purpose, such as `groceries`.
- Flow type answers budget arithmetic: `income | expense | transfer | adjustment`.
- Compute both on read with stored overrides.
- Linked transfers are authoritative. Defer automatic refund-to-purchase linking.

#### B2 — Coverage Gate

- Compute completeness on demand; do not store a coverage-status table.
- Use only fully reconciled intervals and the common covered window across active budget accounts.
- Exclude unbracketed partial periods.
- Return binary confidence, requested vs. actual period, gaps, and `latest_reconciled_through`.
- Return `planner_capital_cents = NULL` when confidence is low.

#### B3 — Honest Budget Output

- Slice 1 exposes `finance.historical_surplus`.
- Buffers are transparent user-selected scenario assumptions.
- Do not label historical average surplus as “safe to invest.”
- Defer `finance.deployable_capital` until liquidity, reserves, obligations, and explicit override are
  designed.

#### W1 — Narrow Correction Workflow

- Build import inspection, issue resolution with notes, safe transaction updates, transaction
  supersession, balance replacement, and category-rule inspection/removal.
- Preserve source evidence and superseded canonical history.
- Defer whole-run replay, automated repair suggestions, bulk editing, and a dedicated UI.

#### G1 — Testing

- Use `pytest` managed with:

```bash
uv add --dev pytest
uv run pytest
```

- Initial `unittest` recommendation was superseded after the full matrix showed repeated need for
  parametrization, temp SQLite fixtures, environment overrides, and synthetic file fixtures.

---

## Superseded Proposals

| Earlier proposal | Replaced by |
|---|---|
| Use `PRAGMA user_version` for finance migrations | `fin_schema_migrations` owned by finance |
| Reject some transaction directions based on asset/liability kind | Both signs valid; reject malformed data and soft-flag suspicious rows |
| Use one UNIQUE transaction fingerprint for dedup | Preserve source rows; separate exact source identity from non-unique canonical matching |
| Accept silent same-day identical-charge collisions in v1 | Preserve both source rows and canonical facts |
| Treat category alone as budget classification | Separate computed category and flow type |
| Expose `finance.deployable_capital` from average surplus | Expose `finance.historical_surplus`; defer full deployable-capital composition |
| Use `unittest` to avoid a dependency | Use pytest as a dev dependency via `uv` |
| Treat recent reconciliation as sufficient | Require a common fully reconciled coverage window |

---

## Scope Boundary

### Build In Slice 1

- Finance-owned schema migrations and enforced SQLite constraints.
- Accounts, import runs, raw source records, canonical transactions, balances, issues, and transfers.
- Integer-cent parsing and posted-date semantics.
- Deterministic Chase checking and credit CSV import.
- Agent-extracted transaction intake.
- Exact re-import idempotency and narrow exact overlap matching.
- Reconciliation, spending summary, historical surplus, and narrow correction tools.
- Pytest suite with synthetic fixtures.

### Defer

- Amex deterministic CSV adapter until a real fixture exists.
- Aggregators, scheduled ingestion, and email acquisition.
- Fuzzy matching, whole-run replay, and bulk correction.
- Full deployable-capital composition.
- Holdings, prices, reporting, and dedicated UI.

---

## Background References

- [`requirements-dump.md`](../../../notes/finance-corpus/00-inbox/requirements-dump.md)
- [`data-pipeline-spec.md`](../../../notes/finance-corpus/00-inbox/data-pipeline-spec.md)
- [`data-pipeline-answers.md`](../../../notes/finance-corpus/00-inbox/data-pipeline-answers.md)
- `../finance-hub/scripts/import_chase.py`
- `../finance-hub/scripts/import_fidelity.py`
