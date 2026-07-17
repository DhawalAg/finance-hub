# Eval Fixtures

Fixture scripts are Phase 1 deliverables. Each script builds one named fixture by running
real migrations and real tools against a temporary SQLite DB. Never hand-crafted SQL.

## Fixture Specs (Phase 0 authoring — scripts not yet written)

### `fidelity_sample_csv` (used by R1)

**What it contains**: an empty, freshly-migrated DB. The fixture also places
`tests/fixtures/fidelity_positions_sample.csv` into the trial dir at `fixture/fidelity_sample.csv`.
No data is pre-seeded — CSV import is the action under test.

**Script task**: run `migrations.run()` on a temp DB. Copy the sample CSV into the trial dir.
Set `FINANCE_HUB_DB` and `FINANCE_HUB_WORKSPACE` to point at the temp dirs.

---

### `dca_ready_deployment` (used by R5)

**What it contains**: a fully-seeded DB ready for plan generation. Import produces no
state change — all prerequisite state is pre-seeded.

**Seed steps** (in order, using real tools to build valid state):
1. `migrations.run()` on a temp DB.
2. Import `tests/fixtures/fidelity_positions_sample.csv` with known snapshot_id
   `snap_r5_fixture` by patching the UUID generator before calling the tool.
   Override `as_of` to `"2026-06-20T16:00:00+00:00"`.
3. Register instruments via `finance.map_instruments`:
   - VTI: etf, broad_market_etf; theme_r5 watching
   - QQQ: etf, broad_market_etf; theme_r5 watching
   - AAPL: stock, single_stock; theme_r5 watching
4. Set instrument statuses to approved in theme_r5 (conviction + notes).
5. Upsert ≥2 sources and link each instrument (scope=instrument).
6. Write workspace/research/instruments/AAPL.md (stub thesis).
7. Set note_path via `finance.set_research_note` for AAPL.
8. Promote strategy: `finance.promote_to_strategy` with version_id=`strat_r5_v1`,
   sleeves [broad_market: 70%, single_stock: 30%], instruments as above.
   Activate: `finance.activate_strategy`.
9. Seed price bars (60 days, up to 2026-06-20) for VTI, AAPL, QQQ using a
   fixture PriceProvider (same pattern as `tests/test_e2e_chain.py`).
10. Run `finance.research_priorities` to confirm no blocking gaps remain before
    saving the fixture.

---

### `chain_quickstart` (used by R7)

**What it contains**: minimal DB with research pre-seeded but no snapshot or strategy yet.
The chain begins with CSV import.

**Seed steps**:
1. `migrations.run()` on a temp DB.
2. Register theme_chain (status=exploring) and map VTI, QQQ, AAPL as candidates.
3. Set note_path for AAPL; write stub workspace/research/instruments/AAPL.md.
4. Upsert ≥2 sources per instrument; link them.
5. Seed price bars (60 days) for VTI, AAPL, QQQ via fixture provider.
6. Place `tests/fixtures/fidelity_positions_sample.csv` at `fixture/fidelity_sample.csv`.
(NO portfolio snapshot, NO strategy version, NO reviews yet — those are chain steps.)

---

### `instrument_candidate_aapl` (used by R3)

**What it contains**: AAPL registered as a candidate instrument, no thesis yet.

**Seed steps**:
1. `migrations.run()` on a temp DB.
2. Register theme_r3 (status=watching, display_name="Quality Growth").
3. `finance.map_instruments` for AAPL (stock/single_stock, status=candidate) in theme_r3.
4. Ensure workspace/research/instruments/ directory exists and is empty.
(No note_path, no sources, no thesis — those are the actions under test.)

---

### `plan_with_block_warning` (used by R10)

**What it contains**: a proposed plan with a block-severity warning pre-seeded.

**Seed steps**:
1. `migrations.run()` on a temp DB.
2. Seed snapshot `snap_r10_fixture` (as_of=2026-06-20T16:00:00+00:00) with the sample CSV.
3. Register VTI (broad_market_etf) and AAPL (single_stock); seed price bars.
4. Promote strategy `strat_r10_v1` with only VTI+AAPL (NOT QQQ) — sleeves 70%/30%.
   Activate it.
5. Call `finance.generate_deployment_plan` with snapshot=snap_r10_fixture,
   strategy=strat_r10_v1, dca_budget=$1,000.
   The QQQ position in the snapshot has no mapped sleeve → produces UNKNOWN_SLEEVE_EXPOSURE
   block warning when unknown_sleeve_pct ≥ 15%. Verify the engine generates the block row.
6. Confirm the generated plan_id matches `plan_r10_fixture` by patching the UUID generator.
   The plan status should be proposed_with_warnings with the block warning in
   fin_deployment_plan_warnings.

**Verification**: after seeding, assert that `finance.plan_readiness_check(plan_id='plan_r10_fixture')`
returns `approvable=false` and `readiness_status='approval_blocked'`.

---

### `dividend_growth_empty` (used by R2)

**What it contains**: an empty, freshly-migrated DB. No themes or instruments pre-seeded —
all research state is created by the agent during the trial.

**Seed steps**:
1. `migrations.run()` on a temp DB.
Set `FINANCE_HUB_DB`, `FINANCE_HUB_WORKSPACE`, and `FINANCE_HUB_NOW=2026-07-01T12:00:00+00:00`.

---

### `approved_candidates_ready_for_promotion` (used by R4)

**What it contains**: three approved research candidates (VTI, QQQ, AAPL) in theme_r4,
ready to be promoted. No strategy version exists yet.

**Seed steps**:
1. `migrations.run()` on a temp DB; set `FINANCE_HUB_NOW=2026-07-01T12:00:00+00:00`.
2. `finance.set_theme(key='theme_r4', display_name='Core Equities', status='watching')`.
3. `finance.map_instruments(theme_key='theme_r4', instruments=[VTI (etf/broad_market_etf),
   QQQ (etf/broad_market_etf), AAPL (stock/single_stock)])`.
4. `finance.review_instrument` × 3 — approve all with conviction + note:
   - VTI: conviction 5, note "Total market at lowest cost — essential DCA backbone"
   - QQQ: conviction 3, note "Acceptable tech tilt; diversification at 30% of broad sleeve"
   - AAPL: conviction 3, note "Services growth offsets hardware saturation risk"
5. `finance.set_research_note(scope='instrument', key='AAPL', body='# AAPL Thesis\n...')` —
   stub thesis required for single_stock at plan generation time.
(NO strategy version — promotion is the action under test.)

---

### `proposed_plan_ready_for_approval` (used by R6)

**What it contains**: a proposed deployment plan (plan_r6_fixture) with no block warnings,
ready to be approved. This is structurally identical to `dca_ready_deployment` (R5) plus
a generated plan.

**Seed steps** (extend `dca_ready_deployment` seed):
1–10. Same as `dca_ready_deployment` (using strat_r6_v1 and snap_r6_fixture as IDs).
11. `finance.generate_deployment_plan(portfolio_snapshot_id='snap_r6_fixture',
    strategy_version_id='strat_r6_v1', deployable_cash='1000', dca_budget='1000')`,
    patching UUID generator to produce `plan_r6_fixture`.
12. `finance.plan_readiness_check(plan_id='plan_r6_fixture')` — assert `approvable=True`
    before saving the fixture.
(workspace/approved/ must be empty — the approval is the action under test.)

---

### `plan_ready_no_price_data` (used by R8)

**What it contains**: a strategy and portfolio snapshot, but NO price bars in fin_price_bars.
Simulates the price provider being unavailable at plan-generation time.

**Seed steps**:
1. `migrations.run()` on a temp DB; set `FINANCE_HUB_NOW=2026-06-23T12:00:00+00:00`.
2. Set up research: `finance.set_theme(key='theme_r8', ...)`.
   `finance.map_instruments` for VTI (etf/broad_market_etf) and AAPL (stock/single_stock).
   Approve both with conviction + note.
   `finance.set_research_note` for AAPL; link ≥2 sources.
3. `finance.promote_to_strategy(version_id='strat_r8_v1', sleeves=[broad_market 70%, single_stock 30%],
   instruments=[VTI→broad_market, AAPL→single_stock], confirm=True)`.
4. `finance.activate_strategy(version_id='strat_r8_v1', confirm=True)`.
5. Import `snap_r8_fixture` from fidelity_positions_sample.csv at `as_of='2026-06-20T16:00:00+00:00'`.
6. **Do NOT call `snapshot()` or insert any price bars.** fin_price_bars must remain empty.
7. Verify: `prices(['VTI', 'AAPL'])` raises PriceFetchError (confirms no bars stored).

---

### `stale_portfolio_snapshot` (used by R9)

**What it contains**: a fully-seeded DB with a portfolio snapshot that is 20 days old
relative to `FINANCE_HUB_NOW=2026-07-10T12:00:00+00:00`. Falls in the "stale" band (15-30 days).
Price bars and metrics are up-to-date (seeded up to 2026-07-10).

**Seed steps**:
1. `migrations.run()` on a temp DB; set `FINANCE_HUB_NOW=2026-07-10T12:00:00+00:00`.
2. Set up research + strategy (VTI, QQQ, AAPL; same pattern as `dca_ready_deployment`),
   using strat_r9_v1 and theme_r9 as IDs.
3. Import `snap_r9_fixture` from fidelity_positions_sample.csv at
   `as_of='2026-06-20T16:00:00+00:00'` (20 days before now).
4. Seed 60 days of price bars up to 2026-07-10 for VTI, AAPL, QQQ, SPY via fixture provider.
5. Compute and store metrics for VTI, AAPL, QQQ.
6. Verify: `validate_snapshot_freshness(snapshot_as_of='2026-06-20T16:00:00+00:00',
   as_of='2026-07-10')` returns `band='stale'`, `days_old=20`.

---

### `theme_with_candidate_msft` (used by R11)

**What it contains**: a theme (theme_r11) with MSFT as a candidate instrument not yet reviewed.

**Seed steps**:
1. `migrations.run()` on a temp DB; set `FINANCE_HUB_NOW=2026-07-01T12:00:00+00:00`.
2. `finance.set_theme(key='theme_r11', display_name='Cloud Growth', status='watching')`.
3. `finance.map_instruments(theme_key='theme_r11', instruments=[
     {'ticker': 'MSFT', 'type': 'stock', 'instrument_role': 'single_stock',
      'display_name': 'Microsoft Corp'}
   ])`.
(No conviction, no review yet — MSFT is status=candidate.)

---

### `active_strategy_with_research_candidates` (used by R12)

**What it contains**: an active strategy with VTI only, plus a research theme (theme_r12_core)
with VTI already approved. The agent will add NVDA as a new research candidate.

**Seed steps**:
1. `migrations.run()` on a temp DB; set `FINANCE_HUB_NOW=2026-07-01T12:00:00+00:00`.
2. `finance.set_theme(key='theme_r12_core', display_name='Core Holdings', status='watching')`.
3. `finance.map_instruments(theme_key='theme_r12_core', instruments=[VTI (etf/broad_market_etf)])`.
4. `finance.review_instrument(theme_key='theme_r12_core', ticker='VTI', status='approved',
   rationale='Core holding', conviction=5, conviction_note='Total market at lowest cost')`.
5. `finance.promote_to_strategy(version_id='strat_r12_v1', label='Established Core',
   sleeves=[{sleeve_key='broad_market', target_weight_pct=100}],
   instruments=[{ticker='VTI', primary_sleeve_key='broad_market', source_theme_key='theme_r12_core'}],
   confirm=True)`.
6. `finance.activate_strategy(version_id='strat_r12_v1', confirm=True)`.
**Verify**: fin_strategy_instruments has exactly 1 row (VTI); NVDA is NOT mapped yet.
