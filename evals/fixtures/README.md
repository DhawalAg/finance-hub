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
