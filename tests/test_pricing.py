from pathlib import Path

from checkout_svc.gateway import authorize
from checkout_svc.pricing import quote
from payments.authorize_request import build_authorization_request

ROOT = Path(__file__).resolve().parents[1]
HEALTHY = ROOT / "config" / "pricing.yaml"
PROMO = ROOT / "config" / "pricing.promo.yaml"


def cart(*items: tuple[int, int]) -> list[dict[str, int]]:
    prices = {1: 1400, 4: 6800, 7: 12500, 8: 14900}
    return [
        {"product_id": product_id, "unit_price_cents": prices[product_id], "quantity": quantity}
        for product_id, quantity in items
    ]


def test_healthy_money_paths_agree_for_representative_carts() -> None:
    for items in [cart((1, 1)), cart((1, 2), (4, 1)), cart((7, 1)), cart((8, 1), (1, 1))]:
        customer_quote = quote(items, HEALTHY)
        request = build_authorization_request(items, HEALTHY)
        assert request["amount_cents"] == customer_quote.total_cents


def test_promo_causes_exactly_flat_shipping_divergence() -> None:
    items = cart((7, 1))
    customer_quote = quote(items, PROMO)
    request = build_authorization_request(items, PROMO)
    assert customer_quote.subtotal_cents >= 10_000
    assert request["amount_cents"] - customer_quote.total_cents == 999
    assert authorize(request, customer_quote.total_cents)["reason"] == "amount_mismatch"


def test_sub_hundred_cart_succeeds_under_both_configs() -> None:
    items = cart((1, 1), (4, 1))
    assert quote(items, PROMO).total_cents < 10_000
    for config in (HEALTHY, PROMO):
        customer_quote = quote(items, config)
        request = build_authorization_request(items, config)
        assert request["amount_cents"] == customer_quote.total_cents
        assert authorize(request, customer_quote.total_cents)["decision"] == "approved"


def test_gateway_declines_without_raising() -> None:
    result = authorize({"amount_cents": 10_999}, 10_000)
    assert result["decision"] == "declined"
    assert result["reason"] == "amount_mismatch"
