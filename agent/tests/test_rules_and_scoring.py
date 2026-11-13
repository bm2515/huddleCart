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


def test_past_orders_group_by_week_and_pod_newest_first():
    from huddlecart import community
    orders = community.past_orders(store.seed_history(), "dua", {"the-house": "The House weekly"})
    assert [o["week"] for o in orders] == [4, 3, 2, 1]
    assert orders[0]["podName"] == "The House weekly" and orders[0]["saved"] == 3


def test_pickup_code_is_stable_and_unique_per_bag():
    assert rules.pickup_code("the-house", 1) == rules.pickup_code("the-house", 1)
    assert rules.pickup_code("the-house", 1) != rules.pickup_code("the-house", 2)


def test_events_seed_has_open_dishes_and_summary_counts():
    from huddlecart import events
    data = store.seed()
    diwali = data["events"][0]
    summary = events.event_summary(diwali, data["pods"][0])
    assert summary["upForGrabs"] == ["Garlic naan", "Cucumber raita"]
    assert summary["claimedCount"] == 5 and summary["comingCount"] == 4
    raita = next(d for d in summary["dishes"] if d["name"] == "Cucumber raita")
    assert raita["ingredientsTotal"] == 11.20


def test_event_xp_rewards_hosts_and_cooks():
    from huddlecart import events
    seeded = store.seed()["events"]
    assert events.event_xp(seeded, "bisma") == events.XP_PER_EVENT_HOSTED
    assert events.event_xp(seeded, "mei") == 2 * events.XP_PER_DISH_CLAIMED


def test_pickup_token_is_stable_per_bag_and_hard_to_guess():
    token = rules.pickup_token("the-house", "dua")
    assert token == rules.pickup_token("the-house", "dua")
    assert token != rules.pickup_token("the-house", "jason") and len(token) == 16
