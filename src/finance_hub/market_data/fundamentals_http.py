"""Live fundamentals HTTP transport (EODHD / Alpha Vantage).

The missing "go fetch it from the internet" half of the fundamentals slice.
The normalizers, storage, and read side already exist in
:mod:`finance_hub.market_data.fundamentals`; the fixture-backed adapters there
serve recorded payloads. This module is the real-network sibling of
``yfinance_provider`` — it turns a ticker into the *same* raw provider dict the
normalizers already consume, so nothing downstream changes.

Design mirrors ``YFinanceProvider``:

- The actual network client is injected (``http_get``) so the fetch + quota +
  normalization contract is testable from a recorded response with no network
  round-trip. When it is ``None`` a stdlib ``urllib`` GET is used (no new
  dependency).
- Free-tier exhaustion is surfaced as :class:`~finance_hub.market_data.
  fundamentals.QuotaExhausted` so :class:`SpilloverFundamentalsProvider` can
  fall through EODHD → Alpha Vantage exactly as it does for the fixture adapters.

This module is transport only. It fetches, normalizes, and grades (``screening``,
never ``decision`` — that stays the normalizers' job). It contains no judgement
about whether a fundamental is "good" — screening philosophy is deliberately out
of scope (see ADR-0005).
"""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Optional

from finance_hub.market_data.fundamentals import (
    Fundamental,
    QuotaExhausted,
    normalize_alpha_vantage,
    normalize_eodhd,
)

# (status_code, body_text) — the minimal transport seam. Injecting this makes a
# provider testable from a recorded (status, body) pair without a socket.
HttpGet = Callable[[str], "tuple[int, str]"]

DEFAULT_TIMEOUT_SECONDS = 20

# HTTP statuses EODHD returns once the free daily request budget is spent (402
# payment required / 429 too-many-requests) or the key is not entitled (403).
_EODHD_QUOTA_STATUSES = frozenset({402, 403, 429})

# Alpha Vantage answers 200 with an advisory body instead of an HTTP error when
# the 25-request/day free tier is spent; these keys flag that case.
_ALPHA_VANTAGE_LIMIT_KEYS = ("Note", "Information")


@lru_cache(maxsize=1)
def _ssl_context() -> ssl.SSLContext:
    """A verifying TLS context, preferring certifi's CA bundle.

    Framework/standalone CPython installs (common on macOS) ship without a
    usable system trust store, so ``create_default_context()`` alone fails cert
    verification. certifi is already present (a yfinance dependency); when it is
    missing we fall back to the default context rather than disabling verify.
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001 — certifi absent; use the default store
        return ssl.create_default_context()


def _urllib_get(url: str) -> tuple[int, str]:
    """Default transport: a plain GET returning ``(status, body_text)``.

    An HTTP error status is returned rather than raised so provider code can
    map quota statuses to :class:`QuotaExhausted` uniformly.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "finance-hub/0.1"})
    try:
        with urllib.request.urlopen(
            req, timeout=DEFAULT_TIMEOUT_SECONDS, context=_ssl_context()
        ) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:  # 4xx/5xx still carry a body
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return exc.code, body


def _eodhd_symbol(ticker: str) -> str:
    """EODHD keys instruments by ``TICKER.EXCHANGE``; default US listings.

    A ticker that already carries an exchange suffix (``VTI.US``, ``ASML.AS``)
    is passed through untouched.
    """
    return ticker if "." in ticker else f"{ticker}.US"


@dataclass
class LiveEODHDProvider:
    """EODHD fundamentals over HTTP — the *paid* upgrade runner.

    EODHD's free tier excludes fundamentals (paid Fundamentals Data Feed), so
    this runs only when a paid ``EODHD_API_KEY`` is configured, where it serves
    a richer pack than Alpha Vantage free and spills to Alpha Vantage on quota.

    ``fetch_fundamentals(ticker)`` GETs the EODHD fundamentals endpoint and
    returns normalized :class:`Fundamental` envelopes. On a quota/entitlement
    status it raises :class:`QuotaExhausted` so a spillover provider can fall
    back to Alpha Vantage.
    """

    api_key: str
    http_get: Optional[HttpGet] = None
    source: str = "eodhd"
    base_url: str = "https://eodhd.com/api/fundamentals"

    def _get(self, url: str) -> tuple[int, str]:
        return (self.http_get or _urllib_get)(url)

    def fetch_fundamentals(self, ticker: str) -> list[Fundamental]:
        symbol = _eodhd_symbol(ticker)
        query = urllib.parse.urlencode({"api_token": self.api_key, "fmt": "json"})
        url = f"{self.base_url}/{urllib.parse.quote(symbol)}?{query}"
        status, body = self._get(url)
        if status in _EODHD_QUOTA_STATUSES:
            raise QuotaExhausted(
                f"{self.source} returned HTTP {status} for {symbol} "
                "(free-tier quota spent or key not entitled)"
            )
        if status != 200:
            raise RuntimeError(f"{self.source} HTTP {status} for {symbol}: {body[:200]}")
        raw = _parse_json_object(body, self.source, symbol)
        if not raw:
            return []
        return normalize_eodhd(raw, source=self.source)


@dataclass
class LiveAlphaVantageProvider:
    """Alpha Vantage ``OVERVIEW`` over HTTP — the free fundamentals runner (default).

    Alpha Vantage's free tier (25 calls/day) is the default free source of the
    compact stock screening pack (revenue growth, margin, P/S, EV/EBITDA). It is
    also the spillover target when a paid EODHD key is configured.

    Alpha Vantage answers 200 with a ``Note``/``Information`` advisory (or an
    empty body) when the free daily budget is spent; that is mapped to
    :class:`QuotaExhausted` so the same spillover logic applies.
    """

    api_key: str
    http_get: Optional[HttpGet] = None
    source: str = "alpha_vantage"
    base_url: str = "https://www.alphavantage.co/query"
    function: str = "OVERVIEW"

    def _get(self, url: str) -> tuple[int, str]:
        return (self.http_get or _urllib_get)(url)

    def fetch_fundamentals(self, ticker: str) -> list[Fundamental]:
        query = urllib.parse.urlencode(
            {"function": self.function, "symbol": ticker, "apikey": self.api_key}
        )
        url = f"{self.base_url}?{query}"
        status, body = self._get(url)
        if status != 200:
            raise RuntimeError(f"{self.source} HTTP {status} for {ticker}: {body[:200]}")
        raw = _parse_json_object(body, self.source, ticker)
        if any(k in raw for k in _ALPHA_VANTAGE_LIMIT_KEYS):
            raise QuotaExhausted(
                f"{self.source} rate-limited for {ticker}: "
                f"{raw.get('Note') or raw.get('Information')}"
            )
        if not raw:  # empty {} → symbol unknown to the free tier
            return []
        return normalize_alpha_vantage(raw, source=self.source)


def _parse_json_object(body: str, source: str, symbol: str) -> dict[str, Any]:
    """Decode a provider body to a dict, tolerating an empty response.

    A non-dict JSON payload (e.g. a bare error string) raises so the caller sees
    a loud failure rather than a silent empty result.
    """
    text = body.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{source} returned non-JSON for {symbol}: {text[:200]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{source} returned unexpected shape for {symbol}: {text[:200]}")
    return parsed
