"""Independent pricing oracle used by the verification engine."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import yaml


def load_config(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("pricing config must be a mapping")
    return value


def reference_quote(cart: list[dict[str, Any]], config_path: Path) -> dict[str, int]:
    config = load_config(config_path)
    subtotal = sum(
        int(item["unit_price_cents"]) * int(item["quantity"]) for item in cart
    )
    discount = 0
    for promo in config.get("promos") or []:
        if not isinstance(promo, dict):
            continue
        if subtotal < int(promo.get("min_subtotal_cents", 0)):
            continue
        if promo.get("type") == "fixed":
            discount += int(promo.get("discount_cents", 0))
        elif promo.get("type") == "percentage":
            percent = Decimal(str(promo.get("percent", "0")))
            discount += int(
                (Decimal(subtotal) * percent / Decimal(100)).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )
    discount = min(subtotal, discount)
    taxable = subtotal - discount
    tax = int(
        (Decimal(taxable) * Decimal(str(config.get("tax_rate", "0")))).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    shipping = int(config.get("shipping_cents", 0))
    if any(
        isinstance(promo, dict)
        and promo.get("type") == "free_shipping"
        and subtotal >= int(promo.get("min_subtotal_cents", 0))
        for promo in config.get("promos") or []
    ):
        shipping = 0
    return {
        "subtotal_cents": subtotal,
        "discount_cents": discount,
        "tax_cents": tax,
        "shipping_cents": shipping,
        "total_cents": subtotal - discount + tax + shipping,
    }


def promo_threshold(config_path: Path) -> int:
    config = load_config(config_path)
    thresholds = [
        int(promo["min_subtotal_cents"])
        for promo in config.get("promos") or []
        if isinstance(promo, dict)
        and promo.get("type") == "free_shipping"
        and "min_subtotal_cents" in promo
    ]
    if not thresholds:
        raise ValueError("pricing config has no free-shipping promo threshold")
    return min(thresholds)
