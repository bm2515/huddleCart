"""Policy v0.2 checks written from policy.md, not from the eval dataset."""
from huddlecart.policy import fair_substitute_price, run_policy, split_cents


def product(sku, price, unit=1, category="milk", stock=10, **extra):
    return {"sku": sku, "name": f"{sku} milk", "price": price, "unit": unit, "category": category, "stock": stock, **extra}


def test_leftover_cents_all_go_to_largest_subtotal():  # R5.3
    shares = split_cents(100, {"a": 1, "b": 1, "c": 1})
    assert sorted(shares.values()) == [33, 33, 34]
    shares = split_cents(101, {"a": 500, "b": 300, "c": 200})
    assert shares == {"a": 51, "b": 30, "c": 20}


def test_service_fee_is_proportional_and_charges_add_up():  # R5.2, R5.4
    setup = {
        "cutoff": 100, "delivery_fee": 5.0, "service_fee_pct": 10,
        "catalog": [product("whole", 3.0), product("oat", 6.0, category="oat")],
        "households": [
            {"id": "ana", "requests": [{"text": "1 whole milk", "added_at": 1}]},
            {"id": "ben", "requests": [{"text": "1 oat milk", "added_at": 2}]},
            {"id": "cy", "requests": [{"text": "1 whole milk", "added_at": 3}]},
        ],
    }
    out = run_policy(setup)
    charges = out["charges"]
    assert charges["ben"]["service"] == 0.6 and charges["ana"]["service"] == 0.3
    assert charges["ben"]["delivery"] == 1.68 and charges["ana"]["delivery"] == 1.66
    assert round(sum(c["total"] for c in charges.values()), 2) == out["order_total"] == 12.0 + 1.2 + 5.0


def test_substitute_uses_price_per_unit():  # R3.1
    small = product("small", 2.0, unit="1L")
    big = product("big", 3.6, unit="2L")
    assert fair_substitute_price(big, small)
    assert not fair_substitute_price(product("pricey", 2.4, unit="1L"), small)
