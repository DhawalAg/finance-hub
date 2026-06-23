"""Finance-owned migration runner.

Finance owns its own migration state in ``fin_schema_migrations`` — *not*
the database-global ``PRAGMA user_version`` — because ``hub.db`` may be
shared with non-finance state in the future.

The version column is INTEGER (an ordered version model), aligning with
the specs. Each entry in ``MIGRATIONS`` is ``(version, sql)`` and is
applied in version order, inside a transaction, and recorded only on
success. Re-running ``run()`` is a no-op: already-applied versions are
skipped.
"""
from __future__ import annotations

from datetime import datetime, timezone

from finance_hub.store import connection

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS fin_schema_migrations (
            version    INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );
        """,
    ),
    (
        2,
        """
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
          CHECK (conviction IS NULL OR
                 (conviction_note IS NOT NULL AND length(trim(conviction_note)) > 0))
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
        """,
    ),
    (
        3,
        """
        CREATE TABLE IF NOT EXISTS fin_price_bars (
            ticker            TEXT NOT NULL,
            session_date      TEXT NOT NULL,
            open_micros       INTEGER,
            high_micros       INTEGER,
            low_micros        INTEGER,
            close_micros      INTEGER NOT NULL,
            adj_close_micros  INTEGER,
            volume            INTEGER,
            currency          TEXT NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
            source            TEXT NOT NULL,
            first_fetched_at  TEXT NOT NULL,
            last_refreshed_at TEXT NOT NULL,
            PRIMARY KEY (ticker, session_date, source)
        );
        CREATE INDEX IF NOT EXISTS ix_fin_price_bars_ticker_session
            ON fin_price_bars (ticker, session_date DESC);
        """,
    ),
    (
        4,
        """
        CREATE TABLE IF NOT EXISTS fin_fundamentals (
            ticker      TEXT NOT NULL,
            field       TEXT NOT NULL,
            as_of       TEXT NOT NULL,
            value       TEXT,
            unit        TEXT,
            source      TEXT NOT NULL,
            grade       TEXT NOT NULL CHECK (grade IN ('decision', 'screening')),
            fetched_at  TEXT NOT NULL,
            source_ref  TEXT,
            PRIMARY KEY (ticker, field, as_of, source)
        );
        CREATE INDEX IF NOT EXISTS ix_fin_fundamentals_ticker_field
            ON fin_fundamentals (ticker, field);
        """,
    ),
    (
        5,
        """
        CREATE TABLE fin_portfolio_snapshots (
            snapshot_id    TEXT PRIMARY KEY,
            as_of          TEXT NOT NULL,
            source_adapter TEXT NOT NULL,
            source_file    TEXT NOT NULL,
            created_at     TEXT NOT NULL
        );

        CREATE TABLE fin_portfolio_positions (
            position_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id          TEXT NOT NULL REFERENCES fin_portfolio_snapshots(snapshot_id),
            account_name         TEXT NOT NULL,
            account_type         TEXT NOT NULL,
            ticker               TEXT,
            name                 TEXT,
            asset_type           TEXT NOT NULL,
            quantity             TEXT,
            market_value_micros  INTEGER,
            cost_basis_micros    INTEGER,
            cash_value_micros    INTEGER,
            currency             TEXT NOT NULL,
            is_supported         INTEGER NOT NULL CHECK (is_supported IN (0, 1)),
            source_row_hash      TEXT NOT NULL,
            UNIQUE (snapshot_id, source_row_hash)
        );

        CREATE INDEX idx_fin_portfolio_positions_snapshot
            ON fin_portfolio_positions(snapshot_id);
        """,
    ),
    (
        6,
        """
        CREATE TABLE IF NOT EXISTS fin_fetch_log (
            id           INTEGER PRIMARY KEY,
            ticker       TEXT,
            attempted_at TEXT NOT NULL,
            source       TEXT,
            ok           INTEGER NOT NULL CHECK (ok IN (0, 1)),
            error        TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_fin_fetch_log_attempted
            ON fin_fetch_log (attempted_at);
        """,
    ),
    (
        7,
        """
        CREATE TABLE IF NOT EXISTS fin_metrics (
            scope            TEXT NOT NULL,
            key              TEXT NOT NULL,
            metric           TEXT NOT NULL,
            window           TEXT NOT NULL,
            as_of            TEXT NOT NULL,
            value            REAL,
            source           TEXT,
            grade            TEXT,
            benchmark_ticker TEXT,
            PRIMARY KEY (scope, key, metric, window, as_of),
            CHECK (scope IN ('ticker', 'sleeve', 'portfolio')),
            CHECK (grade IS NULL OR grade IN ('decision', 'screening'))
        );
        CREATE INDEX IF NOT EXISTS ix_fin_metrics_scope_key
            ON fin_metrics (scope, key);
        """,
    ),
    (
        8,
        """
        CREATE TABLE fin_strategy_versions (
            version_id TEXT PRIMARY KEY,
            label      TEXT,
            status     TEXT NOT NULL DEFAULT 'draft',
            notes      TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (status IN ('draft', 'active', 'archived'))
        );

        CREATE UNIQUE INDEX ux_fin_strategy_versions_active
            ON fin_strategy_versions(status) WHERE status = 'active';

        CREATE TABLE fin_strategy_sleeves (
            version_id        TEXT NOT NULL REFERENCES fin_strategy_versions(version_id),
            sleeve_key        TEXT NOT NULL,
            display_name      TEXT,
            target_weight_bps INTEGER NOT NULL,
            hard_cap_bps      INTEGER,
            created_at        TEXT NOT NULL,
            PRIMARY KEY (version_id, sleeve_key),
            CHECK (target_weight_bps >= 0),
            CHECK (hard_cap_bps IS NULL OR hard_cap_bps >= 0)
        );

        CREATE TABLE fin_strategy_instruments (
            version_id         TEXT NOT NULL REFERENCES fin_strategy_versions(version_id),
            ticker             TEXT NOT NULL,
            primary_sleeve_key TEXT NOT NULL,
            instrument_role    TEXT,
            conviction         INTEGER,
            source_theme_key   TEXT,
            hard_cap_bps       INTEGER,
            note               TEXT,
            created_at         TEXT NOT NULL,
            PRIMARY KEY (version_id, ticker),
            FOREIGN KEY (version_id, primary_sleeve_key)
                REFERENCES fin_strategy_sleeves(version_id, sleeve_key),
            CHECK (hard_cap_bps IS NULL OR hard_cap_bps >= 0)
        );
        """,
    ),
    (
        9,
        """
        CREATE TABLE fin_deployment_plans (
            plan_id                    TEXT PRIMARY KEY,
            output_mode                TEXT NOT NULL,
            status                     TEXT NOT NULL,
            portfolio_snapshot_id      TEXT NOT NULL,
            strategy_version_id        TEXT NOT NULL,
            benchmark_ticker           TEXT NOT NULL,
            risk_mode                  TEXT NOT NULL,
            dca_cadence                TEXT,
            deployable_cash_micros     INTEGER NOT NULL,
            dca_budget_micros          INTEGER NOT NULL,
            one_time_buy_budget_micros INTEGER NOT NULL,
            dca_unallocated_micros     INTEGER NOT NULL DEFAULT 0,
            one_time_unallocated_micros INTEGER NOT NULL DEFAULT 0,
            total_unallocated_micros   INTEGER NOT NULL DEFAULT 0,
            effective_policy           TEXT NOT NULL,
            supersedes_plan_id         TEXT,
            created_at                 TEXT NOT NULL,
            FOREIGN KEY (portfolio_snapshot_id)
                REFERENCES fin_portfolio_snapshots(snapshot_id),
            FOREIGN KEY (strategy_version_id)
                REFERENCES fin_strategy_versions(version_id),
            CHECK (output_mode IN ('deployment_draft')),
            CHECK (status IN ('proposed', 'proposed_with_warnings'))
        );

        CREATE TABLE fin_deployment_plan_lines (
            line_id        TEXT PRIMARY KEY,
            plan_id        TEXT NOT NULL REFERENCES fin_deployment_plans(plan_id),
            bucket         TEXT NOT NULL,
            ticker         TEXT NOT NULL,
            sleeve_key     TEXT,
            amount_micros  INTEGER NOT NULL,
            rank           INTEGER NOT NULL,
            ranked_factors TEXT NOT NULL,
            rationale      TEXT,
            created_at     TEXT NOT NULL,
            CHECK (bucket IN ('dca', 'one_time')),
            CHECK (amount_micros > 0)
        );

        CREATE INDEX idx_fin_deployment_plan_lines_plan
            ON fin_deployment_plan_lines(plan_id);

        CREATE TABLE fin_deployment_plan_warnings (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id   TEXT NOT NULL REFERENCES fin_deployment_plans(plan_id),
            code      TEXT NOT NULL,
            severity  TEXT NOT NULL,
            ticker    TEXT,
            message   TEXT NOT NULL,
            CHECK (severity IN ('warning', 'block'))
        );

        CREATE INDEX idx_fin_deployment_plan_warnings_plan
            ON fin_deployment_plan_warnings(plan_id);

        CREATE TABLE fin_deployment_plan_evidence (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id       TEXT NOT NULL REFERENCES fin_deployment_plans(plan_id),
            line_id       TEXT REFERENCES fin_deployment_plan_lines(line_id),
            evidence_type TEXT NOT NULL,
            ref_table     TEXT NOT NULL,
            ref_key       TEXT NOT NULL,
            summary       TEXT,
            CHECK (evidence_type IN
                ('price', 'metric', 'fundamental', 'research_note', 'research_source'))
        );

        CREATE INDEX idx_fin_deployment_plan_evidence_plan
            ON fin_deployment_plan_evidence(plan_id);
        """,
    ),
]


def _applied_versions(conn) -> set[int]:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fin_schema_migrations'"
    ).fetchone()
    if row is None:
        return set()
    return {r[0] for r in conn.execute("SELECT version FROM fin_schema_migrations")}


def run() -> None:
    """Apply every pending migration in order. Idempotent."""
    with connection.connect() as conn:
        for version, sql in sorted(MIGRATIONS, key=lambda m: m[0]):
            applied = _applied_versions(conn)
            if version in applied:
                continue
            try:
                conn.execute("BEGIN")
                conn.executescript(sql)
                # Migration 1 creates the table; only record once it exists.
                if _table_exists(conn, "fin_schema_migrations"):
                    conn.execute(
                        "INSERT INTO fin_schema_migrations (version, applied_at) VALUES (?, ?)",
                        (version, datetime.now(timezone.utc).isoformat()),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise


def _table_exists(conn, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def ensure_schema() -> None:
    """Backwards-compatible alias for ``run()``."""
    run()
