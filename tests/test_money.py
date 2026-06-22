"""Money/cents helpers: decimal-string -> integer micro-dollars/cents.

Rejects floats and decimals with >2 fractional digits.
"""
from __future__ import annotations

import pytest

from finance_hub.money import to_cents, to_micro_dollars


class TestToCents:
    def test_simple_dollar_amount(self):
        assert to_cents("12.34") == 1234

    def test_integer_string(self):
        assert to_cents("100") == 10000

    def test_one_fractional_digit(self):
        assert to_cents("12.3") == 1230

    def test_zero(self):
        assert to_cents("0") == 0
        assert to_cents("0.00") == 0

    def test_negative(self):
        assert to_cents("-5.25") == -525

    def test_rejects_float_input(self):
        with pytest.raises(TypeError):
            to_cents(12.34)

    def test_rejects_three_fractional_digits(self):
        with pytest.raises(ValueError):
            to_cents("12.345")

    def test_rejects_nonnumeric_string(self):
        with pytest.raises(ValueError):
            to_cents("abc")


class TestToMicroDollars:
    def test_simple_amount(self):
        # $12.34 -> 12_340_000 micro-dollars
        assert to_micro_dollars("12.34") == 12_340_000

    def test_integer(self):
        assert to_micro_dollars("1") == 1_000_000

    def test_zero(self):
        assert to_micro_dollars("0") == 0

    def test_two_fractional_digits_allowed(self):
        assert to_micro_dollars("0.05") == 50_000

    def test_rejects_float_input(self):
        with pytest.raises(TypeError):
            to_micro_dollars(0.1)

    def test_rejects_three_fractional_digits(self):
        with pytest.raises(ValueError):
            to_micro_dollars("12.345")

    def test_rejects_garbage(self):
        with pytest.raises(ValueError):
            to_micro_dollars("not a number")
