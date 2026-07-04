"""Registered fetch tool: ``finance.fetch_fundamentals``.

The consumer seam that stitches the three plumbing pieces together — fetch
(live HTTP provider) → store (``fin_fundamentals``) → read back as citable
evidence. It is the fundamentals analogue of ``finance.prices`` / the price
``snapshot``: the agent and CLI call one entry point and never touch a vendor
API or a bare number directly.

It deliberately stops at *availability + value + provenance*. It does not decide
whether a fundamental is attractive, cheap, or eligible — that screening
philosophy is out of scope (ADR-0005). Every value is surfaced with its grade
(``screening``), source, and ``as_of`` so a plan or memo can cite it.
"""
from __future__ import annotations

from typing import Optional

from finance_hub import factories
from finance_hub.market_data.fundamentals import (
    screen_fundamentals,
    store_fundamentals,
)
from finance_hub.runtime.registry import tool
from finance_hub.store import connection


@tool(
    name="finance.fetch_fundamentals",
    description=(
        "Fetch a ticker's fundamentals from the live provider, store them, and "
        "return each field as citable evidence (availability + value + source + grade)."
    ),
)
def fetch_fundamentals(*, ticker: str, fields: Optional[list[str]] = None) -> dict:
    """Fetch → store → read back one ticker's fundamentals.

    Calls the configured ``FundamentalsProvider`` (Alpha Vantage free by
    default, or paid EODHD spilling to Alpha Vantage), upserts the normalized
    envelopes into ``fin_fundamentals``, and
    renders the stored fields through :func:`screen_fundamentals` so the caller
    sees an explicit availability per field rather than a raw payload. ``fields``
    restricts the read-back; omitted, it reports every field the fetch returned.
    """
    provider = factories.get_fundamentals_provider()
    now = factories.get_clock().now()
    fetched_at = now.isoformat()

    records = provider.fetch_fundamentals(ticker)
    source = records[0].source if records else None
    render_fields = fields if fields is not None else sorted({r.field for r in records})

    with connection.connect() as conn:
        stored = store_fundamentals(conn, ticker, records, fetched_at=fetched_at)
        cells = screen_fundamentals(conn, ticker, render_fields, now=now.date())

    return {
        "ticker": ticker,
        "source": source,
        "fetched_at": fetched_at,
        "stored": stored,
        "fields": {
            field: {
                "availability": cell.availability,
                "value": cell.value,
                "unit": cell.unit,
                "grade": cell.envelope.grade if cell.envelope else None,
                "source": cell.envelope.source if cell.envelope else None,
                "as_of": cell.envelope.as_of if cell.envelope else None,
            }
            for field, cell in cells.items()
        },
    }
