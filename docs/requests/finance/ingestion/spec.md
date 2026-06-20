# Finance Ingestion — Slice 1 Spec

**Status:** Implementation-ready
**Updated:** 2026-05-31
**Home package:** `src/finance_hub/`

This is the authoritative implementation contract for Slice 1. Decision history lives in
[`working-doc.md`](./working-doc.md). Holdings, prices, and scheduled acquisition remain deferred.

---

## 1. Objective

Build a statement-driven budget ingestion layer for the finance hub:

```text
CSV or agent extraction
  → raw source evidence
  → canonical transactions and balances
  → reconciliation
  → spending summary
  → historical surplus
```

Every reported number must trace to imported data or a deterministic tool result. The agent may
extract rows from a PDF and explain results, but code owns persisted facts, validation, arithmetic,
and reconciliation.

### Target user

Single user. The CLI and MCP-exposed agent are the frontends; there is no separate UI.

### Slice 1 outcomes

- Import Chase checking and credit-card CSV exports deterministically.
- Record agent-extracted rows from PDFs or unsupported formats, including Amex until its real CSV
  shape is available.
- Preserve raw evidence and canonical facts separately.
- Re-import the same source safely without double-counting.
- Reconcile posted transactions against asserted statement balances.
- Report spending and a confidence-gated historical-surplus estimate.

### Non-goals

- No Beancount ledger.
- No PDF parser in code.
- No trade execution, money movement, or order placement.
- No multi-currency support; Slice 1 is USD-only.
- No scheduled ingestion, aggregator integration, fuzzy matching, or bulk repair workflow.
- No full `finance.deployable_capital` calculation yet.
- No holdings, prices, reporting, fundamentals, or backtesting in Slice 1.

---

## 2. Architecture Fit

- Tools are plain `@tool`-decorated Python functions under the `finance.` namespace. The existing
  registry exposes them over CLI and MCP.
- Finance owns its `fin_*` tables under `src/finance_hub/store/`, using finance-owned migration
  helpers.
- Pure transformations live outside registered wrappers: money parsing, adapter normalization,
  categorization, flow typing, candidate matching, reconciliation, coverage assessment, and summary
  arithmetic.
- Thin wrappers load state, call pure functions, persist results, and return structured responses.
- Finance store helpers enable `PRAGMA foreign_keys = ON` for every SQLite connection.

### Acquisition Strategy

Slice 1 ships two entry paths:

1. `finance.import_csv`: deterministic Chase checking and credit-card CSV adapters.
2. `finance.record_transactions`: agent-extracted rows from PDFs or unsupported formats.

Both produce provisional source records and pass through the same canonical engine.

Later source adapters are additive:

- Phase 2: SimpleFIN for Chase and Amex transactions if manual cadence becomes annoying.
- Phase 3: Plaid or manual Positions CSV for Fidelity holdings.

Do not build a generalized adapter framework beyond the interface needed by the first real formats.

---

## 3. Canonical Semantics

### 3.1 Money

Persist and compute money as signed integer cents. Never use `REAL` or Python `float` for statement
money.

Agent-facing write tools accept decimal-string dollars:

```json
{"amount": "-12.34"}
{"balance": "-500.00"}
```

Parse with `Decimal`; reject values with more than two fractional digits rather than silently
rounding imported financial facts. Tool responses expose authoritative `*_cents` fields and may add
formatted dollar strings for readability.

### 3.2 Transaction Signs

Store transactions from the user's cash-flow perspective:

```text
negative = value leaving the user
positive = value arriving to the user
```

Examples:

| Event | Stored amount |
|---|---:|
| Checking deposit | positive |
| Checking withdrawal | negative |
| Card purchase or fee | negative |
| Card payment or refund | positive |

Adapters normalize source-native signs at the boundary. Do not infer a sign from merchant keywords.
Do not reject a transaction merely because of its direction and account kind: both signs are valid
for both assets and liabilities.

Hard-reject malformed values, unsupported currencies, unknown accounts, and disallowed zero-value
rows. Suspicious-but-possible rows become soft issues.

### 3.3 Balance Signs

Store asserted balances from the user's net-worth perspective:

```text
asset balance     = positive when owned
liability balance = negative when owed
```

Example: a credit-card statement showing `$500 owed` stores `balance_cents = -50000`.

Every account reconciles with one equation:

```text
ending_balance_cents
  = starting_balance_cents
  + sum(transaction.amount_cents)
```

### 3.4 Dates

- `posted_date` is required and canonical. Use it for reconciliation, summaries, filtering, and
  fallback matching.
- `authorized_date` is optional provenance when the source exposes an earlier purchase date.
- Chase checking maps `Posting Date` → `posted_date`.
- Chase credit maps `Post Date` → `posted_date` and `Transaction Date` → `authorized_date`.
- If a source exposes one date, store it as `posted_date`.
- Pending authorizations are out of scope.

---

## 4. Data Model

The schema below is the intended baseline. Exact DDL may be split into ordered migrations.

```sql
CREATE TABLE fin_schema_migrations (
  version            INTEGER PRIMARY KEY,
  applied_at         TEXT NOT NULL
);

CREATE TABLE fin_accounts (
  key                TEXT PRIMARY KEY,
  display_name       TEXT NOT NULL,
  kind               TEXT NOT NULL CHECK (kind IN ('asset', 'liability')),
  subtype            TEXT NOT NULL CHECK (subtype IN ('checking', 'savings', 'credit_card', 'brokerage')),
  currency           TEXT NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
  active             INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
  include_in_budget  INTEGER NOT NULL DEFAULT 1 CHECK (include_in_budget IN (0, 1)),
  opened_on          TEXT,
  closed_on          TEXT,
  created_at         TEXT NOT NULL
);

CREATE TABLE fin_ingest_runs (
  id                 INTEGER PRIMARY KEY,
  adapter            TEXT NOT NULL,
  adapter_version    TEXT NOT NULL,
  source_label       TEXT,
  source_filename    TEXT,
  source_file_sha256 TEXT,
  started_at         TEXT NOT NULL,
  completed_at       TEXT,
  status             TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
  recorded_count     INTEGER NOT NULL DEFAULT 0,
  matched_count      INTEGER NOT NULL DEFAULT 0,
  quarantined_count  INTEGER NOT NULL DEFAULT 0,
  ignored_count      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE fin_transfer_groups (
  id                 INTEGER PRIMARY KEY,
  created_at         TEXT NOT NULL,
  source             TEXT NOT NULL CHECK (source IN ('auto', 'manual'))
);

CREATE TABLE fin_transactions (
  id                 INTEGER PRIMARY KEY,
  account            TEXT NOT NULL REFERENCES fin_accounts(key),
  posted_date        TEXT NOT NULL,
  authorized_date    TEXT,
  amount_cents       INTEGER NOT NULL CHECK (amount_cents != 0),
  payee              TEXT,
  description        TEXT,
  category_override  TEXT,
  flow_type_override TEXT CHECK (flow_type_override IS NULL OR flow_type_override IN ('income', 'expense', 'transfer', 'adjustment')),
  transfer_group_id  INTEGER REFERENCES fin_transfer_groups(id),
  canonical_match_key TEXT NOT NULL,
  created_at         TEXT NOT NULL,
  superseded_at      TEXT,
  superseded_by_id   INTEGER REFERENCES fin_transactions(id),
  supersede_reason   TEXT
);

CREATE TABLE fin_balances (
  id                 INTEGER PRIMARY KEY,
  account            TEXT NOT NULL REFERENCES fin_accounts(key),
  as_of_date         TEXT NOT NULL,
  balance_cents      INTEGER NOT NULL,
  source             TEXT NOT NULL,
  recorded_at        TEXT NOT NULL,
  superseded_at      TEXT,
  superseded_by_id   INTEGER REFERENCES fin_balances(id),
  supersede_reason   TEXT
);

CREATE TABLE fin_category_rules (
  id                 INTEGER PRIMARY KEY,
  pattern            TEXT NOT NULL,
  category           TEXT,
  flow_type          TEXT CHECK (flow_type IS NULL OR flow_type IN ('income', 'expense', 'transfer', 'adjustment')),
  priority           INTEGER NOT NULL DEFAULT 100,
  added_at           TEXT NOT NULL,
  CHECK (category IS NOT NULL OR flow_type IS NOT NULL)
);

CREATE TABLE fin_source_records (
  id                 INTEGER PRIMARY KEY,
  ingest_run_id      INTEGER NOT NULL REFERENCES fin_ingest_runs(id),
  source_record_key  TEXT NOT NULL UNIQUE,
  source_locator     TEXT NOT NULL,
  external_id        TEXT,
  raw_payload_json   TEXT NOT NULL,
  normalized_json    TEXT,
  transaction_id     INTEGER REFERENCES fin_transactions(id),
  disposition        TEXT NOT NULL CHECK (disposition IN ('recorded', 'matched_existing', 'quarantined', 'ignored')),
  created_at         TEXT NOT NULL
);

CREATE TABLE fin_ingest_issues (
  id                 INTEGER PRIMARY KEY,
  source_record_id   INTEGER REFERENCES fin_source_records(id),
  created_at         TEXT NOT NULL,
  severity           TEXT NOT NULL CHECK (severity IN ('hard', 'soft')),
  reason             TEXT NOT NULL,
  detail_json        TEXT,
  status             TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved', 'ignored')),
  resolution_note    TEXT,
  resolved_at        TEXT
);

CREATE UNIQUE INDEX fin_balances_current_account_date
  ON fin_balances(account, as_of_date)
  WHERE superseded_at IS NULL;

CREATE INDEX fin_transactions_account_posted
  ON fin_transactions(account, posted_date);
CREATE INDEX fin_transactions_match_key
  ON fin_transactions(canonical_match_key);
CREATE INDEX fin_ingest_issues_status_reason
  ON fin_ingest_issues(status, reason);
CREATE INDEX fin_category_rules_priority
  ON fin_category_rules(priority, id);
CREATE INDEX fin_source_records_run
  ON fin_source_records(ingest_run_id);
CREATE INDEX fin_source_records_transaction
  ON fin_source_records(transaction_id);
```

### Migration Ownership

`init_finance()` creates `fin_schema_migrations` if needed, then runs missing finance migrations in
order inside a transaction. Record each version only after success.

Do not use database-global `PRAGMA user_version`; finance owns explicit migration state in
`fin_schema_migrations`.

### Deletion Policy

Do not cascade-delete canonical financial facts. Corrections supersede facts while preserving source
evidence and revision history.

---

## 5. Lineage And Idempotency

Raw evidence and canonical facts are deliberately separate:

```text
fin_ingest_runs
  → fin_source_records
  → fin_transactions / fin_balances
```

- `fin_ingest_runs` records one committed import call.
- `fin_source_records` records every raw input row before canonical matching.
- `fin_transactions` and `fin_balances` store the app's current accepted facts.
- Store source filename and SHA-256, not statement file contents. Raw row JSON stays only in the local
  gitignored SQLite database.
- `dry_run=True` parses and validates but writes no runs, source records, issues, or facts.

### Source-Record Identity

Use source identity only for exact re-import idempotency:

| Source | Identity |
|---|---|
| Adapter with guaranteed stable external IDs | `(adapter, account, external_id)` |
| CSV without stable IDs | `(file_sha256, row_number)` |
| Agent/PDF extraction | `(caller_batch_key, row_locator)` |

### Canonical Matching

Canonical matching is separate from source identity. Build a non-unique candidate key from normalized
facts such as:

```text
(account, posted_date, amount_cents, normalized_payee)
```

Auto-link to an existing canonical transaction only when the match is exact and unambiguous.
Otherwise create a distinct canonical fact or quarantine an ambiguous cross-source candidate.

Consequences:

- Re-importing the same CSV adds no transactions.
- Two identical coffees from different CSV rows remain two transactions.
- CSV and PDF rows may link to one transaction when the match is unambiguous.
- No plausible charge is silently discarded.

Keep Slice 1 matching narrow. Defer fuzzy matching and historical whole-run replay until demonstrated
need.

---

## 6. Categorization And Flow Types

Category and budget flow type answer different questions:

- **Category:** what was this for? Example: `groceries`, `housing`, `dining`.
- **Flow type:** how does this affect budget arithmetic? One of:
  `income | expense | transfer | adjustment`.

Compute both on read. Persist only per-row manual overrides.

### Category Precedence

1. `category_override`
2. user rule
3. default in-code rule
4. `uncategorized`

### Flow-Type Precedence

1. linked transfer group → `transfer`
2. `flow_type_override`
3. user/default rule
4. negative amount → `expense`
5. positive amount → `income`

Rules may assign a category, a flow type, or both.

Summary arithmetic:

- `income`: contributes to income.
- `expense`: contributes to spend.
- `transfer`: excluded from income and spend.
- `adjustment`: nets against spend by category when possible; otherwise appears separately.

Defer automatic refund-to-original-purchase linking.

---

## 7. Reconciliation And Coverage

`fin_balances` stores asserted statement ending balances in canonical net-worth signs.

For consecutive balances `(b0 @ d0, b1 @ d1)` on one account:

```text
b0 + sum(transactions where posted_date in (d0, d1]) == b1
```

`finance.balance_check` reports each interval and logs mismatches to `fin_ingest_issues`. It never
auto-repairs data.

### Budget Coverage

Assess completeness on demand for accounts where:

```text
active = 1 AND include_in_budget = 1
```

Account `opened_on` and `closed_on` bound the periods it is expected to cover.

Use only fully reconciled intervals. The budget estimate uses the common reconciled window across all
included accounts and excludes unbracketed partial periods. Return:

- requested vs. actual covered period
- included accounts
- per-account coverage gaps
- `latest_reconciled_through`
- binary `confidence: "high" | "low"`

Do not store a separate coverage-status table yet.

---

## 8. Transfers

Internal transfers receive a durable two-leg link without introducing a full double-entry ledger.

Example:

```text
checking     -50000 cents
credit card  +50000 cents
```

`finance.record_transfer(from_txn_id, to_txn_id)` validates:

- distinct accounts
- equal absolute cents
- opposite signs

`finance.match_transfers(window_days=5)` uses a narrow heuristic:

- same absolute amount
- opposite signs
- distinct accounts
- nearby posting dates
- transfer-like rule evidence

Auto-link only unambiguous one-to-one matches. Quarantine ambiguous candidates and unmatched
transfer-like rows after the window. Defer split and multi-leg transfers.

---

## 9. Issues And Corrections

Nothing is silently dropped. Every source row is recorded, matched, quarantined, or intentionally
ignored.

Hard issues reject canonical persistence, for example:

- malformed amount or date
- unsupported currency
- unknown account
- disallowed zero-value row

Soft issues preserve the canonical fact but require attention, for example:

- suspicious-but-possible direction
- uncategorized transaction
- ambiguous transfer candidate
- missing transfer leg
- reconciliation mismatch

Corrections do not rewrite raw evidence. Default reads and reconciliation use only current,
non-superseded canonical facts.

---

## 10. Slice 1 Tools

### Intake And Inspection

| Tool | Purpose |
|---|---|
| `finance.import_csv(path, account=None, dry_run=False)` | Import Chase CSV rows through the canonical engine |
| `finance.record_transactions(transactions, batch_key, dry_run=False)` | Persist agent-extracted rows; each row supplies `posted_date`, decimal-string `amount`, account, and row locator |
| `finance.list_ingest_runs(limit=50)` | Inspect import batches |
| `finance.get_ingest_run(run_id)` | Inspect source records and issues for one batch |
| `finance.list_transactions(...)` | Inspect current canonical transactions with computed category and flow type |

### Configuration And Corrections

| Tool | Purpose |
|---|---|
| `finance.add_account(...)` | Add configured account metadata |
| `finance.update_account(key, ...)` | Update account scope or lifecycle |
| `finance.add_category_rule(pattern, category=None, flow_type=None, priority=50)` | Add user rule |
| `finance.list_category_rules()` | Inspect rules |
| `finance.delete_category_rule(rule_id)` | Remove rule; compute-on-read applies immediately |
| `finance.update_transaction(txn_id, category=None, flow_type=None, payee=None)` | Correct safe user-facing fields |
| `finance.supersede_transaction(txn_id, replacement, reason)` | Replace an incorrect canonical fact while retaining history |
| `finance.record_balance(account, as_of_date, balance, source="statement")` | Add asserted balance |
| `finance.replace_balance(account, as_of_date, balance, source="manual", reason=None)` | Supersede asserted balance |

### Integrity And Reporting

| Tool | Purpose |
|---|---|
| `finance.balance_check(account=None)` | Reconcile statement intervals and log gaps |
| `finance.match_transfers(window_days=5, dry_run=False)` | Link unambiguous internal transfers |
| `finance.record_transfer(from_txn_id, to_txn_id)` | Explicitly link a transfer pair |
| `finance.list_issues(status="open")` | Review quarantine and soft issues |
| `finance.resolve_issue(issue_id, status="resolved", note=None)` | Record issue disposition |
| `finance.spending_summary(start=None, end=None, account=None)` | Compute income, spend, adjustments, transfers, and categories |
| `finance.historical_surplus(lookback_months=3, buffer_cents=0, buffer_pct=0)` | Compute confidence-gated historical average surplus |

### Historical-Surplus Output

`finance.historical_surplus` returns:

- requested and actual fully reconciled period
- included accounts and coverage detail
- income, spend, adjustments, and average monthly surplus in cents
- `latest_reconciled_through`
- binary confidence
- transparent buffer assumptions
- `buffered_historical_surplus_cents`
- `planner_capital_cents`: populated only when confidence is high; otherwise `NULL`

This is not yet a claim that the amount is safe to invest. Future `finance.deployable_capital` may
compose historical surplus with liquid cash, reserve policy, upcoming obligations, and explicit user
override.

---

## 11. Testing

Use `pytest` as a dev dependency:

```bash
uv add --dev pytest
uv run pytest
```

Keep fixtures synthetic. Never commit real statements, account data, API keys, or SQLite contents.

### Pure-Core Tests

- Decimal-string dollars → integer cents; reject floats and excess fractional digits.
- Asset and liability balance normalization using the shared reconciliation equation.
- Posting-date mapping and optional authorization date.
- Category and flow-type precedence.
- Common fully reconciled coverage window and low-confidence output.

### SQLite Integration Tests

- Finance migrations are idempotent; FK and `CHECK` violations fail.
- Chase checking and credit-card CSV imports normalize correctly.
- Exact same-file re-import adds no canonical transactions.
- Two identical-looking CSV rows remain distinct transactions.
- CSV plus agent extraction links one unambiguous transaction without double-counting.
- Card purchase, payment, refund, and fee reconcile correctly.
- Posting-date boundary reconciliation succeeds.
- Transfer matching links an unambiguous pair and quarantines ambiguity or missing legs.
- Superseding a transaction and replacing a balance preserve raw evidence.
- `dry_run=True` writes nothing.

---

## 12. Acceptance Criteria

1. `finance.import_csv` ingests synthetic Chase checking and credit-card fixtures with correct posted
   dates, signs, and source-record lineage.
2. Re-running the same file adds zero canonical transactions while preserving clear batch results.
3. Two identical-looking rows in one CSV remain two canonical transactions.
4. Agent-extracted rows use the same canonical engine and can link an exact, unambiguous overlap
   without double-counting.
5. Liability balances store as negative amounts owed and reconcile with the same equation as assets.
6. `finance.spending_summary` distinguishes categories from flow types and excludes linked transfers.
7. `finance.balance_check` names reconciliation windows and gaps and logs mismatches.
8. `finance.historical_surplus` calculates only over a common fully reconciled window and returns
   `planner_capital_cents = NULL` when confidence is low.
9. Issues are durable and reviewable; raw source evidence is never silently discarded.
10. Corrections preserve source evidence and superseded canonical history.
11. `init_finance()` uses finance-owned ordered migrations and is idempotent.
12. Schema foreign keys, `CHECK`s, and query indexes exist; foreign keys are enabled per connection.
13. CLI and MCP expose the registered tools.
14. No Slice 1 runtime dependency is added; `pytest` is a dev dependency only.

---

## 13. Build Order

1. Enable SQLite FK enforcement; add finance-owned migrations and baseline schema.
2. Add pure money, date, normalization, category, flow-type, and reconciliation helpers with pytest
   coverage.
3. Add account configuration, ingest runs, source records, canonical transaction persistence, issues,
   and inspection tools.
4. Add deterministic Chase CSV import and exact source-record idempotency.
5. Add agent-extracted transaction intake and narrow exact cross-source matching.
6. Add balances, reconciliation, and common-window coverage assessment.
7. Add transfers and narrow auto-matching.
8. Add corrections and supersession.
9. Add spending summary and historical surplus.
10. Verify tool registration through CLI and MCP with synthetic fixtures.

Stop after the first Chase end-to-end import plus reconciliation path for review before completing the
remaining tools.

---

## 14. Deferred Work

### Explicitly Deferred From Slice 1

- Amex deterministic CSV adapter until a real export fixture is available.
- Automated aggregators and scheduled ingestion.
- Fuzzy cross-source matching, bulk editing, and whole-run replay.
- Full deployable-capital composition.
- Dedicated UI.

### Slice 2: Holdings And Market-Data Reads

Slice 2 gets its own sharpening pass before implementation. It must settle holdings snapshots, sold
positions, brokerage cash, source/as-of provenance, share precision, and the market-data
daily-bar / price-envelope read contract.

Useful background remains in:

- [`notes/finance-corpus/00-inbox/data-pipeline-spec.md`](../../../../notes/finance-corpus/00-inbox/data-pipeline-spec.md)
- [`notes/finance-corpus/00-inbox/data-pipeline-answers.md`](../../../../notes/finance-corpus/00-inbox/data-pipeline-answers.md)
- [`notes/finance-corpus/00-inbox/requirements-dump.md`](../../../../notes/finance-corpus/00-inbox/requirements-dump.md)

Reference parsing logic remains in `../finance-hub/scripts/import_chase.py` and
`../finance-hub/scripts/import_fidelity.py`. Reuse parsing ideas; do not inherit the Beancount
architecture.
