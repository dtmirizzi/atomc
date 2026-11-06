"""Strict parsing helpers: vendor responses are validated, never coerced.

Every helper raises :class:`VendorResponseError` with a bounded evidence message when a
documented field is missing or has the wrong type. Adapters build their offer list only after
the whole response has parsed, so malformed data can never leak a partial result.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from .errors import VendorResponseError

__all__ = [
    "as_list",
    "as_mapping",
    "parse_int",
    "parse_lead_time_days",
    "parse_money_minor",
    "parse_stock_text",
    "required",
]


def _fail(context: str) -> VendorResponseError:
    return VendorResponseError(f"malformed vendor response: {context}")


def as_mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _fail(f"{context} must be an object, got {type(value).__name__}")
    return value


def as_list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise _fail(f"{context} must be an array, got {type(value).__name__}")
    return value


def required(mapping: dict[str, Any], key: str, context: str) -> Any:
    if key not in mapping or mapping[key] is None:
        raise _fail(f"{context}.{key} is missing")
    return mapping[key]


def parse_int(value: Any, context: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(f"{context} must be an integer, got {type(value).__name__}")
    if minimum is not None and value < minimum:
        raise _fail(f"{context} must be >= {minimum}, got {value}")
    return value


def parse_money_minor(value: Any, context: str) -> int:
    """Parse a vendor price (number or currency string) into integer minor units."""
    if isinstance(value, bool):
        raise _fail(f"{context} must be a price, got bool")
    if isinstance(value, int):
        decimal = Decimal(value)
    elif isinstance(value, float):
        decimal = Decimal(str(value))
    elif isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        cleaned = re.sub(r"^[^0-9+\-.]*", "", cleaned)
        cleaned = re.sub(r"[^0-9eE+\-.]*$", "", cleaned)
        try:
            decimal = Decimal(cleaned)
        except InvalidOperation as exc:
            raise _fail(f"{context} is not a parseable price: {value!r}") from exc
    else:
        raise _fail(f"{context} must be a price, got {type(value).__name__}")
    if not decimal.is_finite() or decimal < 0:
        raise _fail(f"{context} must be a finite non-negative price, got {value!r}")
    minor = (decimal * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(minor)


def parse_stock_text(value: Any, context: str) -> int:
    """Parse availability text like ``"320 In Stock"`` or a bare integer."""
    if isinstance(value, int) and not isinstance(value, bool):
        return parse_int(value, context, minimum=0)
    if not isinstance(value, str):
        raise _fail(f"{context} must be stock text or an integer, got {type(value).__name__}")
    match = re.search(r"(\d[\d,]*)", value)
    if match is None:
        raise _fail(f"{context} contains no stock quantity: {value!r}")
    return int(match.group(1).replace(",", ""))


def parse_lead_time_days(value: Any, context: str) -> int | None:
    """Parse ``"7 Days"``/``"2 Weeks"``/an integer into days; ``None`` when absent."""
    if value is None or value == "":
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return parse_int(value, context, minimum=0)
    if not isinstance(value, str):
        raise _fail(f"{context} must be lead-time text or an integer")
    match = re.search(r"(\d[\d,]*)", value)
    if match is None:
        raise _fail(f"{context} contains no lead-time quantity: {value!r}")
    days = int(match.group(1).replace(",", ""))
    if re.search(r"\bweek", value, re.IGNORECASE):
        days *= 7
    return days
