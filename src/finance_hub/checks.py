"""Read-only setup diagnostic for finance-hub.

run_checks(env, *, live=False) returns a list of CheckResult, each with a
severity (green/yellow/red) and an optional remediation hint. Never mutates
state. Network-free by default; --live adds a real price fetch.
"""
from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping

Severity = Literal["green", "yellow", "red"]


@dataclass
class CheckResult:
    name: str
    severity: Severity
    message: str
    fix: str | None = None


def run_checks(env: Mapping[str, str], *, live: bool = False) -> list[CheckResult]:
    """Return structured check results for this install.

    env: a dict-like mapping of environment variables (inject os.environ or
         a test stub). Checks read only from this mapping — never os.environ.
    live: if True, adds a real price fetch (network required).
    """
    results: list[CheckResult] = []
    _check_python_version(results)
    _check_store(results, env)
    _check_workspace(results, env)
    _check_price_provider(results, env)
    if live:
        _check_price_live(results)
    _check_fundamentals(results, env)
    _check_anthropic_key(results, env)
    _check_env_vars(results, env)
    return results


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_python_version(results: list[CheckResult]) -> None:
    vi = sys.version_info
    version_str = f"{vi.major}.{vi.minor}.{vi.micro}"
    if (vi.major, vi.minor) >= (3, 10):
        results.append(CheckResult(
            name="python_version",
            severity="green",
            message=f"Python {version_str}",
        ))
    else:
        results.append(CheckResult(
            name="python_version",
            severity="red",
            message=f"Python {version_str} is too old (requires >= 3.10)",
            fix="Install Python 3.10 or newer: https://python.org/downloads",
        ))


def _check_store(results: list[CheckResult], env: Mapping[str, str]) -> None:
    db_path = Path(env.get("FINANCE_HUB_DB", Path.cwd() / "finance-hub.db"))
    if not db_path.exists():
        results.append(CheckResult(
            name="store",
            severity="yellow",
            message=f"SQLite DB not found at {db_path}; will be created on first tool use",
            fix="Run any finance tool — migrations apply automatically on first connect",
        ))
        return
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='fin_schema_migrations'"
            ).fetchone()
            if row is None:
                results.append(CheckResult(
                    name="store",
                    severity="yellow",
                    message=f"SQLite DB at {db_path} exists but schema not initialized",
                    fix="Run any finance tool — migrations apply automatically on first connect",
                ))
                return
            migrations = conn.execute(
                "SELECT version FROM fin_schema_migrations ORDER BY version"
            ).fetchall()
            count = len(migrations)
            latest = migrations[-1][0] if migrations else 0
            results.append(CheckResult(
                name="store",
                severity="green",
                message=f"SQLite store at {db_path}: {count} migration(s) applied, latest schema v{latest}",
            ))
    except Exception as exc:
        results.append(CheckResult(
            name="store",
            severity="red",
            message=f"SQLite store error at {db_path}: {exc}",
            fix=f"Check that {db_path} is readable, or set FINANCE_HUB_DB to a valid path",
        ))


def _check_workspace(results: list[CheckResult], env: Mapping[str, str]) -> None:
    workspace = Path(env.get("FINANCE_HUB_WORKSPACE", Path.cwd() / "workspace"))
    if workspace.exists() and workspace.is_dir():
        results.append(CheckResult(
            name="workspace",
            severity="green",
            message=f"Workspace directory exists: {workspace}",
        ))
    elif workspace.exists():
        results.append(CheckResult(
            name="workspace",
            severity="red",
            message=f"Workspace path exists but is not a directory: {workspace}",
            fix=f"Remove the file at {workspace} or set FINANCE_HUB_WORKSPACE to a directory path",
        ))
    else:
        results.append(CheckResult(
            name="workspace",
            severity="yellow",
            message=f"Workspace directory not found: {workspace} (will be created on first write)",
            fix=f"mkdir -p {workspace}  # or leave it — tools create it automatically",
        ))


def _check_price_provider(results: list[CheckResult], env: Mapping[str, str]) -> None:
    provider_name = env.get("FINANCE_HUB_PRICE_PROVIDER")
    if provider_name == "none":
        results.append(CheckResult(
            name="price_provider",
            severity="yellow",
            message="Price fetching disabled (FINANCE_HUB_PRICE_PROVIDER=none)",
            fix="export FINANCE_HUB_PRICE_PROVIDER=yfinance",
        ))
        return
    if provider_name in (None, "yfinance"):
        try:
            import yfinance  # noqa: F401
            results.append(CheckResult(
                name="price_provider",
                severity="green",
                message="yfinance installed and wired (default provider)",
            ))
        except ImportError:
            results.append(CheckResult(
                name="price_provider",
                severity="red",
                message="yfinance is not installed",
                fix="pip install 'finance-hub[market-data]'",
            ))
        return
    results.append(CheckResult(
        name="price_provider",
        severity="red",
        message=f"Unknown price provider: FINANCE_HUB_PRICE_PROVIDER={provider_name!r}",
        fix="export FINANCE_HUB_PRICE_PROVIDER=yfinance  # or 'none' to disable",
    ))


def _check_price_live(results: list[CheckResult]) -> None:
    try:
        from finance_hub import factories
        provider = factories.get_price_provider()
        bars = provider.fetch_daily_bars(["SPY"], start="2026-06-01", end="2026-06-05")
        if bars:
            results.append(CheckResult(
                name="price_live",
                severity="green",
                message=f"Live price fetch: {len(bars)} bar(s) returned for SPY",
            ))
        else:
            results.append(CheckResult(
                name="price_live",
                severity="yellow",
                message="Live price fetch: no bars returned for SPY (market may be closed or data unavailable)",
                fix="Check network connectivity and try again during market hours",
            ))
    except Exception as exc:
        results.append(CheckResult(
            name="price_live",
            severity="red",
            message=f"Live price fetch failed: {exc}",
            fix="Check network connectivity or FINANCE_HUB_PRICE_PROVIDER setting",
        ))


def _check_fundamentals(results: list[CheckResult], env: Mapping[str, str]) -> None:
    eodhd = bool((env.get("EODHD_API_KEY") or "").strip())
    alpha = bool((env.get("ALPHA_VANTAGE_API_KEY") or "").strip())
    if eodhd or alpha:
        wired = " → ".join(
            name for name, on in (("EODHD", eodhd), ("Alpha Vantage", alpha)) if on
        )
        results.append(CheckResult(
            name="fundamentals",
            severity="green",
            message=f"Fundamentals provider configured ({wired})",
        ))
        return
    results.append(CheckResult(
        name="fundamentals",
        severity="yellow",
        message=(
            "Fundamentals provider not configured: "
            "DCA works; one-time buys need fundamentals evidence"
        ),
        fix="export EODHD_API_KEY=...  # free tier; or ALPHA_VANTAGE_API_KEY=... as the fallback runner",
    ))


def _check_anthropic_key(results: list[CheckResult], env: Mapping[str, str]) -> None:
    if env.get("ANTHROPIC_API_KEY"):
        results.append(CheckResult(
            name="anthropic_api_key",
            severity="green",
            message="ANTHROPIC_API_KEY is set",
        ))
    else:
        results.append(CheckResult(
            name="anthropic_api_key",
            severity="yellow",
            message=(
                "ANTHROPIC_API_KEY not set (optional — only needed for the in-process LLM helper; "
                "irrelevant for deterministic tools and the MCP use case)"
            ),
            fix="export ANTHROPIC_API_KEY=sk-ant-...  # only if using the in-process LLM helper",
        ))


_ENV_VAR_DEFAULTS = {
    "FINANCE_HUB_DB": "finance-hub.db (in cwd)",
    "FINANCE_HUB_WORKSPACE": "workspace/ (in cwd)",
    "FINANCE_HUB_PRICE_PROVIDER": "yfinance",
}


def _check_env_vars(results: list[CheckResult], env: Mapping[str, str]) -> None:
    for var, default in _ENV_VAR_DEFAULTS.items():
        val = env.get(var)
        name = f"env_{var.lower()}"
        if val:
            results.append(CheckResult(
                name=name,
                severity="green",
                message=f"{var}={val!r}",
            ))
        else:
            results.append(CheckResult(
                name=name,
                severity="green",
                message=f"{var} not set (defaulting to {default})",
            ))
