from datetime import timedelta
from huddlecart import rules, store
from evals.run_evals import score_case

CHIPS = {"id": "w-shrimp-chips", "marketplace": "weee", "title": "Calbee Shrimp Chips", "price": 1.99, "inStock": True}


def test_cart_totals_and_free_shipping_progress():
    pod = store.seed()["pods"][0]
    cart = [{"podId": pod["id"], "memberId": "dua", "product": CHIPS, "qty": 3}]
    totals = rules.cart_totals(pod, cart)
    assert totals["subtotal"] == 5.97 and totals["remaining"] == 43.03 and totals["buyers"] == 1


def test_add_is_blocked_for_out_of_stock_wrong_store_and_closed_pod():
    pod = store.seed()["pods"][0]
    assert rules.why_cannot_add(pod, CHIPS, 2) is None
    assert rules.why_cannot_add(pod, {**CHIPS, "inStock": False}, 1) == "That item is out of stock."
    assert "orders from Weee" in rules.why_cannot_add(pod, {**CHIPS, "marketplace": "amazon_fresh"}, 1)
    assert rules.why_cannot_add({**pod, "status": "locked"}, CHIPS, 1).startswith("This pod is locked")
    assert rules.why_cannot_add(pod, {**CHIPS, "price": None}, 1)


def test_bag_list_adds_flat_fee_per_buyer():
    pod = store.seed()["pods"][0]
    cart = [{"podId": pod["id"], "memberId": "dua", "product": CHIPS, "qty": 2}]
    bag = rules.bag_list(pod, cart, store.seed()["members"])[0]
    assert bag["bag"] == 1 and bag["amountDue"] == 5.98


def test_deadline_filters_pods():
    pods = store.seed()["pods"]
    tomorrow = [p["id"] for p in rules.pods_delivering_by(pods, store.now() + timedelta(hours=24))]
    assert tomorrow == ["fresh-basics", "asian-snacks"]


def test_scorer_accepts_out_of_stock_flag():
    case = {"expected": {"intent": "add_items", "items": [{"out_of_stock": "w-paneer"}]}}
    run = {"understanding": {"intent": "add_items"}, "blocks": [{"type": "out_of_stock", "product": {"id": "w-paneer"}, "alternatives": []}]}
    assert score_case(case, run)["passed"]
