"""Slice 5 — market data metrics evidence pack (fin_metrics).

Covers the acceptance criteria:
- migration creates `fin_metrics` (`scope ∈ ticker|sleeve|portfolio`; carries
  `source`/`grade`/`as_of`);
- returns / volatility / drawdown / 52-week position computed correctly from a
  fixed `adj_close` series (pure-helper unit tests, no DB);
- benchmark-relative values carry the benchmark ticker;
- metrics are appended by `as_of` (re-computing a later date adds rows, does
  not overwrite history).
"""
from __future__ import annotations

import math
import sqlite3
from datetime import date

import pytest

from finance_hub.envelope import SCREENING
from finance_hub.market_data import metrics as M
from finance_hub.market_data.metrics import PricePoint
from finance_hub.store import connection, migrations


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "test.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    migrations.run()
    return p


def _pp(d: str, price: float) -> PricePoint:
    return PricePoint(date.fromisoformat(d), price)


# --- migration -----------------------------------------------------------


class TestMigration:
    def test_table_exists_with_envelope_columns(self, db_path):
        with connection.connect() as conn:
            cols = {c["name"]: c for c in conn.execute("PRAGMA table_info(fin_metrics)")}
        for required in ("scope", "key", "metric", "window", "as_of", "value",
                         "source", "grade", "benchmark_ticker"):
            assert required in cols, f"missing column {required}"
        for required in ("scope", "key", "metric", "window", "as_of"):
            assert cols[required]["notnull"] == 1

    def test_primary_key_includes_as_of(self, db_path):
        with connection.connect() as conn:
            cols = conn.execute("PRAGMA table_info(fin_metrics)").fetchall()
        pk = {c["name"] for c in cols if c["pk"] > 0}
        assert pk == {"scope", "key", "metric", "window", "as_of"}

    def test_scope_check_constraint(self, db_path):
        with connection.connect() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_metrics (scope, key, metric, window, as_of, value) "
                    "VALUES ('bogus','AAPL','ret','1y','2026-06-22',0.5)"
                )

    def test_grade_check_constraint(self, db_path):
        with connection.connect() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO fin_metrics (scope, key, metric, window, as_of, grade) "
                    "VALUES ('ticker','AAPL','ret','1y','2026-06-22','bogus')"
                )


# --- pure metric math ----------------------------------------------------


class TestReturns:
    def test_simple_return_over_window(self):
        series = [_pp("2025-06-20", 100.0), _pp("2026-06-22", 150.0)]
        r = M.simple_return(series, date(2026, 6, 22), M.WINDOW_DAYS["1y"])
        assert r == pytest.approx(0.5)

    def test_picks_latest_bar_on_or_before_target(self):
        # 1m lookback -> target 2026-05-23; the 2026-05-22 bar (price 140) wins.
        series = [
            _pp("2026-03-22", 130.0),
            _pp("2026-05-22", 140.0),
            _pp("2026-06-22", 150.0),
        ]
        r = M.simple_return(series, date(2026, 6, 22), M.WINDOW_DAYS["1m"])
        assert r == pytest.approx(150.0 / 140.0 - 1.0)

    def test_insufficient_history_returns_none_not_zero(self):
        # Series only reaches back ~1m; a 1y return cannot be computed.
        series = [_pp("2026-05-22", 140.0), _pp("2026-06-22", 150.0)]
        assert M.simple_return(series, date(2026, 6, 22), M.WINDOW_DAYS["1y"]) is None


class TestVolatility:
    def test_annualized_realized_volatility(self):
        # Daily returns: +0.10, -0.10 -> sample stdev 0.141421, ×√252.
        series = [_pp("2026-06-20", 100.0), _pp("2026-06-21", 110.0), _pp("2026-06-22", 99.0)]
        vol = M.realized_volatility(series)
        expected = math.sqrt(0.02) * math.sqrt(252)
        assert vol == pytest.approx(expected)

    def test_needs_two_returns(self):
        assert M.realized_volatility([_pp("2026-06-22", 100.0)]) is None


class TestDrawdown:
    def test_max_drawdown(self):
        series = [_pp(f"2026-06-{d:02d}", p) for d, p in
                  zip(range(10, 16), [100.0, 120.0, 90.0, 110.0, 60.0, 130.0])]
        # Running peak 120 -> trough 60 = -0.5.
        assert M.max_drawdown(series) == pytest.approx(-0.5)

    def test_current_drawdown_off_the_high(self):
        series = [_pp("2026-06-10", 100.0), _pp("2026-06-11", 120.0), _pp("2026-06-12", 60.0)]
        assert M.current_drawdown(series) == pytest.approx(-0.5)

    def test_current_drawdown_at_high_is_zero(self):
        series = [_pp("2026-06-10", 100.0), _pp("2026-06-11", 120.0)]
        assert M.current_drawdown(series) == pytest.approx(0.0)


class TestPosition52w:
    def test_position_in_range(self):
        # high 200, low 100, last 150 -> (150-100)/(200-100) = 0.5.
        series = [_pp("2026-01-02", 100.0), _pp("2026-03-02", 200.0), _pp("2026-06-22", 150.0)]
        assert M.position_52w(series, date(2026, 6, 22)) == pytest.approx(0.5)

    def test_flat_range_has_no_position(self):
        series = [_pp("2026-01-02", 100.0), _pp("2026-06-22", 100.0)]
        assert M.position_52w(series, date(2026, 6, 22)) is None


# --- evidence-pack assembly ----------------------------------------------


def _year_series():
    return [
        _pp("2025-06-10", 100.0),
        _pp("2025-06-20", 100.0),
        _pp("2025-12-21", 125.0),
        _pp("2026-03-22", 130.0),
        _pp("2026-05-22", 140.0),
        _pp("2026-06-19", 145.0),
        _pp("2026-06-22", 150.0),
    ]


class TestEvidencePack:
    def test_produces_returns_vol_drawdown_position(self):
        got = {(m.metric, m.window): m for m in M.compute_ticker_metrics(
            _year_series(), ticker="AAPL", as_of=date(2026, 6, 22), source="yfinance")}
        assert (M.RET, "1y") in got
        assert (M.RET, "1m") in got
        assert (M.VOL, "1y") in got
        assert (M.MAX_DRAWDOWN, "1y") in got
        assert (M.CURRENT_DRAWDOWN, "1y") in got
        assert (M.POS_52W, "1y") in got
        # All price-derived metrics are screening-grade, sourced and dated.
        for m in got.values():
            assert m.grade == SCREENING
            assert m.source == "yfinance"
            assert m.as_of == "2026-06-22"

    def test_ret_1y_value(self):
        got = {(m.metric, m.window): m for m in M.compute_ticker_metrics(
            _year_series(), ticker="AAPL", as_of=date(2026, 6, 22), source="yfinance")}
        assert got[(M.RET, "1y")].value == pytest.approx(0.5)

    def test_omits_metrics_that_cannot_be_computed(self):
        # A short series: 1y/6m/3m returns have no anchor and are dropped.
        short = [_pp("2026-06-19", 145.0), _pp("2026-06-22", 150.0)]
        windows = {(m.metric, m.window) for m in M.compute_ticker_metrics(
            short, ticker="NEW", as_of=date(2026, 6, 22), source="yfinance")}
        assert (M.RET, "1y") not in windows
        assert (M.RET, "6m") not in windows


class TestBenchmarkRelative:
    def test_relative_return_carries_benchmark_ticker(self):
        ticker = _year_series()  # ret_1y = 0.5
        bench = [_pp("2025-06-20", 100.0), _pp("2026-06-22", 120.0)]  # ret_1y = 0.2
        got = {(m.metric, m.window): m for m in M.compute_ticker_metrics(
            ticker, ticker="AAPL", as_of=date(2026, 6, 22), source="yfinance",
            benchmark_series=bench)}
        rel = got[(M.RET_VS_BENCHMARK, "1y")]
        assert rel.value == pytest.approx(0.3)
        assert rel.benchmark_ticker == "SPY"

    def test_benchmark_ticker_overridable(self):
        ticker = _year_series()
        bench = [_pp("2025-06-20", 100.0), _pp("2026-06-22", 120.0)]
        got = {(m.metric, m.window): m for m in M.compute_ticker_metrics(
            ticker, ticker="AAPL", as_of=date(2026, 6, 22), source="yfinance",
            benchmark_series=bench, benchmark_ticker="QQQ")}
        assert got[(M.RET_VS_BENCHMARK, "1y")].benchmark_ticker == "QQQ"

    def test_absolute_metrics_have_no_benchmark_ticker(self):
        got = {(m.metric, m.window): m for m in M.compute_ticker_metrics(
            _year_series(), ticker="AAPL", as_of=date(2026, 6, 22), source="yfinance")}
        assert got[(M.RET, "1y")].benchmark_ticker is None


# --- storage: append-by-as_of --------------------------------------------


class TestStorage:
    def test_append_by_as_of_keeps_history(self, db_path):
        s1 = _year_series()
        with connection.connect() as conn:
            M.store_metrics(conn, M.compute_ticker_metrics(
                s1, ticker="AAPL", as_of=date(2026, 6, 19), source="yfinance"))
            M.store_metrics(conn, M.compute_ticker_metrics(
                s1, ticker="AAPL", as_of=date(2026, 6, 22), source="yfinance"))
            as_ofs = {r[0] for r in conn.execute(
                "SELECT DISTINCT as_of FROM fin_metrics "
                "WHERE scope='ticker' AND key='AAPL' AND metric='ret' AND window='1y'"
            )}
        # Recomputing a later date appended a new row; history was not overwritten.
        assert as_ofs == {"2026-06-19", "2026-06-22"}

    def test_same_as_of_recompute_is_idempotent(self, db_path):
        with connection.connect() as conn:
            M.store_metrics(conn, M.compute_ticker_metrics(
                _year_series(), ticker="AAPL", as_of=date(2026, 6, 22), source="yfinance"))
            M.store_metrics(conn, M.compute_ticker_metrics(
                _year_series(), ticker="AAPL", as_of=date(2026, 6, 22), source="yfinance"))
            n = conn.execute(
                "SELECT COUNT(*) FROM fin_metrics "
                "WHERE scope='ticker' AND key='AAPL' AND metric='ret' AND window='1y' "
                "AND as_of='2026-06-22'"
            ).fetchone()[0]
        assert n == 1

    def test_benchmark_ticker_persisted(self, db_path):
        ticker = _year_series()
        bench = [_pp("2025-06-20", 100.0), _pp("2026-06-22", 120.0)]
        with connection.connect() as conn:
            M.store_metrics(conn, M.compute_ticker_metrics(
                ticker, ticker="AAPL", as_of=date(2026, 6, 22), source="yfinance",
                benchmark_series=bench))
            row = conn.execute(
                "SELECT benchmark_ticker, grade FROM fin_metrics "
                "WHERE metric='ret_vs_benchmark' AND window='1y' AND key='AAPL'"
            ).fetchone()
        assert row["benchmark_ticker"] == "SPY"
        assert row["grade"] == "screening"


# --- bars -> series ------------------------------------------------------


class TestSeriesFromBars:
    def test_reads_adj_close_and_excludes_future_bars(self, db_path):
        with connection.connect() as conn:
            for d, adj in [("2026-06-20", 100_000_000), ("2026-06-22", 150_000_000),
                           ("2026-06-25", 999_000_000)]:
                conn.execute(
                    "INSERT INTO fin_price_bars "
                    "(ticker, session_date, close_micros, adj_close_micros, currency, "
                    " source, first_fetched_at, last_refreshed_at) "
                    "VALUES ('AAPL', ?, ?, ?, 'USD', 'yfinance', "
                    "'2026-06-22T00:00:00Z', '2026-06-22T00:00:00Z')",
                    (d, adj, adj),
                )
            conn.commit()
            series = M.series_from_bars(conn, "AAPL", "yfinance", date(2026, 6, 22))
        assert [p.session_date.isoformat() for p in series] == ["2026-06-20", "2026-06-22"]
        assert series[-1].price == pytest.approx(150.0)

    def test_falls_back_to_close_when_adj_close_null(self, db_path):
        with connection.connect() as conn:
            conn.execute(
                "INSERT INTO fin_price_bars "
                "(ticker, session_date, close_micros, adj_close_micros, currency, "
                " source, first_fetched_at, last_refreshed_at) "
                "VALUES ('AAPL', '2026-06-22', 120000000, NULL, 'USD', 'yfinance', "
                "'2026-06-22T00:00:00Z', '2026-06-22T00:00:00Z')"
            )
            conn.commit()
            series = M.series_from_bars(conn, "AAPL", "yfinance", date(2026, 6, 22))
        assert series[0].price == pytest.approx(120.0)
