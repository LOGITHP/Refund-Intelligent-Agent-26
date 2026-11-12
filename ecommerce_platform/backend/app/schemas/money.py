"""Shared Pydantic v2 monetary types backed by exact Python Decimal with numeric JSON serialization."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Annotated, Any, Optional
from pydantic import BeforeValidator, PlainSerializer


def _parse_decimal_money(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("Monetary amount cannot be a boolean")
    try:
        dec = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Invalid monetary amount") from exc
    if not dec.is_finite():
        raise ValueError("Monetary amount must be finite")
    return dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _parse_optional_decimal_money(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    return _parse_decimal_money(value)


MoneyField = Annotated[
    Decimal,
    BeforeValidator(_parse_decimal_money),
    PlainSerializer(lambda v: float(v), return_type=float, when_used="json"),
]

OptionalMoneyField = Annotated[
    Optional[Decimal],
    BeforeValidator(_parse_optional_decimal_money),
    PlainSerializer(
        lambda v: float(v) if v is not None else None,
        return_type=Optional[float],
        when_used="json",
    ),
]
