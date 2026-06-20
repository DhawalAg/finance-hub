"""Finance-owned migration runner.

The detailed finance migrations are specified under docs/requests/finance and will be
implemented as each slice lands.
"""
from __future__ import annotations

from finance_hub.store import connection


def ensure_schema() -> None:
    """Create the baseline finance migration table."""
    connection.init()
