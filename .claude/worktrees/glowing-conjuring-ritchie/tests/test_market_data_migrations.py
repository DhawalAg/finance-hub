"""Schema migration for ``fin_price_bars``.

Slice 3 (PRD #1, issue #5) adds the bars table behind the
``PriceProvider`` seam. Acceptance criteria pinned here:

- PK is ``(ticker, session_date, source)`` so re-fetching the same key is
  an idempotent no-op (via upsert) and vendors are never mixed in one
  series.
- Prices are integer micro-dollars; floats are never persisted.
- USD-only is enforced at the database boundary (``CHECK currency =
  'USD'``).
- ``close_micros`` is NOT NULL — the raw, unadjusted close is the
  planner/valuation anchor.
- ``adj_close_micros`` is nullable and refreshable; ``last_refreshed_at``
  records the latest adjustment refresh.
"""
from __future__ import annotations

import sqlite3

import pytest

from finance_hub.store import connection, migrations


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "test.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    return p


def _insert_bar(conn, **overrides):
    row = {
        "ticker": "AAPL",
        "session_date": "2026-06-20",
        "open_micros": 149_500_000,
        "high_micros": 151_000_000,
        "low_micros": 149_000_000,
        "close_micros": 150_000_000,
        "adj_close_micros": 150_000_000,
        "volume": 1_000_000,
        "currency": "USD",
        "source": "yfinance",
        "first_fetched_at": "2026-06-21T10:00:00Z",
        "last_refreshed_at": "2026-06-21T10:00:00Z",
    }
    row.update(overrides)
    cols = ", ".join(row.keys())
    placeholders = ", ".join("?" for _ in row)
    conn.execute(
        f"INSERT INTO fin_price_bars ({cols}) VALUES ({placeholders})",
        tuple(row.values()),
    )


class TestFinPriceBarsSchema:
    def test_table_exists(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='fin_price_bars'"
            ).fetchall()
        assert len(rows) == 1

    def test_primary_key_is_ticker_session_source(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            cols = conn.execute("PRAGMA table_info(fin_price_bars)").fetchall()
        pk = {c["name"] for c in cols if c["pk"] > 0}
        assert pk == {"ticker", "session_date", "source"}

    def test_close_micros_not_null(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            close = next(
                c for c in conn.execute("PRAGMA table_info(fin_price_bars)")
                if c["name"] == "close_micros"
            )
        assert close["notnull"] == 1
        assert close["type"].upper() == "INTEGER"

    def test_adj_close_micros_is_nullable(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            col = next(
                c for c in conn.execute("PRAGMA table_info(fin_price_bars)")
                if c["name"] == "adj_close_micros"
            )
        assert col["notnull"] == 0


class TestFinPriceBarsConstraints:
    def test_duplicate_pk_rejected(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            _insert_bar(conn)
            with pytest.raises(sqlite3.IntegrityError):
                _insert_bar(conn, close_micros=999_000_000)

    def test_different_source_is_allowed(self, db_path):
        """``source`` in the key keeps two vendors from being mixed in one series."""
        migrations.run()
        with connection.connect() as conn:
            _insert_bar(conn, source="yfinance")
            _insert_bar(conn, source="polygon", close_micros=150_100_000)
            n = conn.execute(
                "SELECT COUNT(*) FROM fin_price_bars WHERE ticker = 'AAPL' AND session_date = '2026-06-20'"
            ).fetchone()[0]
        assert n == 2

    def test_non_usd_currency_rejected(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                _insert_bar(conn, currency="GBP")

    def test_fin_fetch_log_table_and_shape(self, db_path):
        """Slice 4 (issue #6): the snapshot reliability trip-wire log."""
        migrations.run()
        with connection.connect() as conn:
            assert conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='fin_fetch_log'"
            ).fetchone() is not None
            cols = {c["name"]: c for c in conn.execute("PRAGMA table_info(fin_fetch_log)")}
        assert set(cols) == {"id", "ticker", "attempted_at", "source", "ok", "error"}
        assert cols["ok"]["notnull"] == 1
        assert cols["attempted_at"]["notnull"] == 1

    def test_fin_fetch_log_rejects_non_binary_ok(self, db_path):
        migrations.run()
        with connection.connect() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_fetch_log (attempted_at, ok) VALUES ('2026-06-22T00:00:00Z', 2)"
                )

    def test_upsert_refreshes_adj_close(self, db_path):
        """Same-key re-fetch is idempotent and may refresh adj_close + last_refreshed_at."""
        migrations.run()
        with connection.connect() as conn:
            _insert_bar(conn, adj_close_micros=150_000_000)
            conn.execute(
                """
                INSERT INTO fin_price_bars
                    (ticker, session_date, open_micros, high_micros, low_micros,
                     close_micros, adj_close_micros, volume, currency, source,
                     first_fetched_at, last_refreshed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, session_date, source) DO UPDATE SET
                    adj_close_micros = excluded.adj_close_micros,
                    last_refreshed_at = excluded.last_refreshed_at
                """,
                (
                    "AAPL", "2026-06-20",
                    149_500_000, 151_000_000, 149_000_000,
                    150_000_000, 151_000_000, 1_000_000, "USD", "yfinance",
                    "2026-06-21T10:00:00Z", "2026-06-22T10:00:00Z",
                ),
            )
            row = conn.execute(
                "SELECT adj_close_micros, first_fetched_at, last_refreshed_at "
                "FROM fin_price_bars WHERE ticker='AAPL' AND session_date='2026-06-20' AND source='yfinance'"
            ).fetchone()
        assert row["adj_close_micros"] == 151_000_000
        assert row["first_fetched_at"] == "2026-06-21T10:00:00Z"
        assert row["last_refreshed_at"] == "2026-06-22T10:00:00Z"
