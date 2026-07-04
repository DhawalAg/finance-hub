"""Live fundamentals HTTP transport (EODHD / Alpha Vantage).

Deterministic suite: the network client is injected as a ``(status, body)``
stub so the fetch → quota-mapping → normalization contract is exercised without
a socket. Reuses the recorded provider fixtures the normalizers are already
tested against.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from finance_hub.market_data.fundamentals import QuotaExhausted, SpilloverFundamentalsProvider
from finance_hub.market_data.fundamentals_http import (
    LiveAlphaVantageProvider,
    LiveEODHDProvider,
)

FIXTURES = Path(__file__).parent / "fixtures" / "fundamentals"


def _body(name: str) -> str:
    return (FIXTURES / f"{name}.json").read_text()


def _stub(status: int, body: str, sink: list | None = None):
    """A ``http_get`` returning a fixed ``(status, body)``; records URLs seen."""

    def _get(url: str) -> tuple[int, str]:
        if sink is not None:
            sink.append(url)
        return status, body

    return _get


class TestEODHDTransport:
    def test_normalizes_recorded_body(self):
        provider = LiveEODHDProvider(api_key="k", http_get=_stub(200, _body("eodhd_aapl")))
        fields = {f.field: f for f in provider.fetch_fundamentals("AAPL")}
        assert fields, "expected normalized fundamentals from a 200 body"
        assert all(f.grade == "screening" for f in fields.values())
        assert all(f.source == "eodhd" for f in fields.values())

    def test_defaults_us_exchange_suffix(self):
        seen: list[str] = []
        provider = LiveEODHDProvider(api_key="k", http_get=_stub(200, "{}", seen))
        provider.fetch_fundamentals("AAPL")
        assert "AAPL.US" in seen[0]
        assert "api_token=k" in seen[0]

    def test_passes_through_explicit_exchange(self):
        seen: list[str] = []
        provider = LiveEODHDProvider(api_key="k", http_get=_stub(200, "{}", seen))
        provider.fetch_fundamentals("ASML.AS")
        assert "ASML.AS" in seen[0] and "ASML.AS.US" not in seen[0]

    @pytest.mark.parametrize("status", [402, 403, 429])
    def test_quota_status_raises_quota_exhausted(self, status):
        provider = LiveEODHDProvider(api_key="k", http_get=_stub(status, ""))
        with pytest.raises(QuotaExhausted):
            provider.fetch_fundamentals("AAPL")

    def test_other_error_status_raises_runtime(self):
        provider = LiveEODHDProvider(api_key="k", http_get=_stub(500, "boom"))
        with pytest.raises(RuntimeError):
            provider.fetch_fundamentals("AAPL")

    def test_empty_body_returns_no_records(self):
        provider = LiveEODHDProvider(api_key="k", http_get=_stub(200, ""))
        assert provider.fetch_fundamentals("AAPL") == []


class TestAlphaVantageTransport:
    def test_normalizes_recorded_body(self):
        provider = LiveAlphaVantageProvider(
            api_key="k", http_get=_stub(200, _body("alpha_vantage_aapl"))
        )
        fields = {f.field: f for f in provider.fetch_fundamentals("AAPL")}
        assert fields
        assert all(f.source == "alpha_vantage" for f in fields.values())

    @pytest.mark.parametrize("key", ["Note", "Information"])
    def test_rate_limit_advisory_raises_quota_exhausted(self, key):
        provider = LiveAlphaVantageProvider(
            api_key="k", http_get=_stub(200, json.dumps({key: "throttled"}))
        )
        with pytest.raises(QuotaExhausted):
            provider.fetch_fundamentals("AAPL")

    def test_empty_object_returns_no_records(self):
        provider = LiveAlphaVantageProvider(api_key="k", http_get=_stub(200, "{}"))
        assert provider.fetch_fundamentals("AAPL") == []


class TestSpillover:
    def test_eodhd_quota_falls_through_to_alpha_vantage(self):
        primary = LiveEODHDProvider(api_key="k", http_get=_stub(429, ""))
        fallback = LiveAlphaVantageProvider(
            api_key="k", http_get=_stub(200, _body("alpha_vantage_aapl"))
        )
        provider = SpilloverFundamentalsProvider(primary=primary, fallback=fallback)
        records = provider.fetch_fundamentals("AAPL")
        assert records and all(f.source == "alpha_vantage" for f in records)


class TestFetchFundamentalsTool:
    """finance.fetch_fundamentals: fetch → store → read-back as citable evidence."""

    @pytest.fixture
    def db_path(self, tmp_path, monkeypatch):
        from finance_hub.store import connection, migrations

        p = tmp_path / "test.db"
        monkeypatch.setattr(connection, "DB_PATH", p)
        migrations.run()
        return p

    def test_stores_and_reads_back_screening_evidence(self, db_path, monkeypatch):
        from finance_hub import factories
        from finance_hub.market_data import fundamentals_tools

        factories.reset()
        factories.set_fundamentals_provider(
            LiveEODHDProvider(api_key="k", http_get=_stub(200, _body("eodhd_aapl")))
        )
        try:
            result = fundamentals_tools.fetch_fundamentals(ticker="AAPL")
        finally:
            factories.reset()

        assert result["ticker"] == "AAPL"
        assert result["source"] == "eodhd"
        assert result["stored"] >= 1
        # Every rendered field is screening-grade evidence, never a verdict.
        for cell in result["fields"].values():
            assert cell["availability"] in ("available", "missing", "stale", "not_configured")
            if cell["availability"] == "available":
                assert cell["grade"] == "screening"

    def test_requested_missing_field_is_absent_not_zero(self, db_path):
        from finance_hub import factories
        from finance_hub.market_data import fundamentals_tools

        factories.reset()
        factories.set_fundamentals_provider(
            LiveEODHDProvider(api_key="k", http_get=_stub(200, "{}"))
        )
        try:
            result = fundamentals_tools.fetch_fundamentals(ticker="AAPL", fields=["ps"])
        finally:
            factories.reset()

        assert result["stored"] == 0
        assert result["fields"]["ps"]["availability"] == "missing"
        assert result["fields"]["ps"]["value"] is None
