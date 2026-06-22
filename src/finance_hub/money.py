"""Money helpers: parse decimal strings into integer cents / micro-dollars.

Bare floats are rejected — float arithmetic on money is silently wrong.
Strings with more than two fractional digits are rejected because we never
record sub-cent precision from a user-facing input.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

CENTS_SCALE = 100
MICRO_DOLLARS_SCALE = 1_000_000
_MAX_FRACTIONAL_DIGITS = 2


def _parse(value: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(f"money inputs must be strings, got {type(value).__name__}")
    try:
        d = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"not a valid decimal string: {value!r}") from exc
    exponent = d.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -_MAX_FRACTIONAL_DIGITS:
        raise ValueError(
            f"too many fractional digits in {value!r}; max {_MAX_FRACTIONAL_DIGITS}"
        )
    return d


def to_cents(value: str) -> int:
    """Convert a decimal-string dollar amount to integer cents."""
    return int(_parse(value) * CENTS_SCALE)


def to_micro_dollars(value: str) -> int:
    """Convert a decimal-string dollar amount to integer micro-dollars."""
    return int(_parse(value) * MICRO_DOLLARS_SCALE)
