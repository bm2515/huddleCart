"""Ordering policy v0.2 as plain code: turn household requests into one group order, carts, charges and notifications.

No AI here. Text matching is a small fuzzy parser so the same setup always gives the same cart.
Entry point: run_policy(setup) -> dict.
"""
import math
import re
from difflib import SequenceMatcher

SUB_PRICE_LIMIT = 1.15        # R3.3 a substitute may cost at most 15% more
PRICE_JUMP_FLAG = 1.15        # R5.5 a checkout price jump over 15% is flagged
OUTLIER_MULTIPLE = 5          # R4.1 more than 5x the usual quantity is held
FILLER_WORDS = {"a", "an", "the", "of", "some", "please", "bottle", "bottles", "bag", "bags", "pack", "packs", "carton", "cartons",
                "jar", "jars", "can", "cans", "bunch", "boxes", "lb", "lbs", "pound", "pounds", "gallon", "gallons", "gal", "l", "ml", "g", "loaf", "box", "each", "ct", "oz", "1l", "1gal", "fresh"}
INJECTION_MARKERS = re.compile(r"\b(system note|system:|ignore (all )?previous|instruction)", re.I)
EDIT_WORDS = re.compile(r"\b(actually|just|make it|change it to|instead)\b", re.I)
YES = re.compile(r"\b(yes|yep|correct|right|confirm)", re.I)


# ---------- R1 understanding ----------

def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9%]+", text.lower())


def singular(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def similar(a: str, b: str) -> bool:
    a, b = singular(a), singular(b)
    return a == b or (len(a) > 3 and SequenceMatcher(None, a, b).ratio() >= 0.6)


def split_items(text: str) -> list[str]:
    """R8.1 keep only the shopping part, then R1.1 split 'eggs, bread and 2 bananas' into items."""
    text = INJECTION_MARKERS.split(text)[0]
    return [p.strip() for p in re.split(r",|\band\b|\.|;", text) if words(p)]


def parse_quantity(item: str) -> tuple[int | None, bool, str]:
    """Returns (number asked for, says 'dozen', the rest of the text)."""
    tokens = words(item)
    number = int(tokens.pop(0)) if tokens and tokens[0].isdigit() else None
    if tokens and tokens[0] in ("a", "an"):
        tokens.pop(0)
    return number, "dozen" in tokens, " ".join(t for t in tokens if t != "dozen")


def allowed_for(product: dict, household: dict) -> bool:
    profile = household.get("profile", {})
    if set(product.get("allergens", []) + product.get("contains", [])) & set(profile.get("allergens", [])):
        return False
    return all(diet in product.get("tags", []) for diet in profile.get("dietary", []))


def candidates_for(query: str, catalog: list[dict], household: dict) -> list[dict]:
    """Products whose name covers every word asked for, fewest extra words first.
    Products that fit the household profile win (R1.4); others only come back when nothing fits."""
    asked = [w for w in words(query) if w not in FILLER_WORDS and not w.isdigit()]  # "ramen 5 pack": the 5 is the pack size
    if not asked:
        return []
    scored = []
    for product in catalog:
        name = [w for w in words(product["name"]) if not re.fullmatch(r"\d+(lb|oz|ct|ml|l|g|gal|pk)?", w)]
        if all(any(similar(a, n) for n in name) for a in asked):
            extra = [n for n in name if n not in FILLER_WORDS | {"dozen", "half"} and not any(similar(a, n) for a in asked)]
            scored.append((len(extra), product))
    scored = [(s, p) for s, p in scored if allowed_for(p, household)] or scored
    if not scored:
        return []
    fewest = min(s for s, _ in scored)
    return [p for s, p in scored if s == fewest]


def pick_pack(number: int | None, dozen: bool, products: list[dict]) -> tuple[dict, int]:
    """R2.2 count requests buy the smallest pack that covers them; packs are never shared (R2.3)."""
    packs = sorted((p for p in products if isinstance(p.get("unit"), int)), key=lambda p: p["unit"])
    if dozen:
        return next((p for p in packs if p["unit"] == 12), packs[-1] if packs else products[0]), number or 1
    if number and packs and len(packs) == len(products) and number < packs[-1]["unit"]:
        pack = next(p for p in packs if p["unit"] >= number)
        return pack, math.ceil(number / pack["unit"])
    return products[0], number or 1


def last_purchase(household: dict, query: str) -> str | None:
    """History comes as {query: sku} or as {"sku": ..., "qty": ...}."""
    last = household.get("history", {}).get("last_purchase", {})
    return last.get("sku") if "sku" in last else last.get(query)


def usual_qty(household: dict, product: dict) -> int | None:
    history = household.get("history", {})
    last = history.get("last_purchase", {})
    from_last = last.get("qty") if last.get("sku") == product["sku"] else None
    return history.get(product["sku"], {}).get("usual_qty") or from_last or product.get("typical_qty")


def apply_edits(households: list[dict], events: list[dict], cutoff: str) -> None:
    """An edit before cutoff replaces the household's request (final quantities win, place in line kept).
    An edit after cutoff leaves this order alone and becomes a late request for the next one (R9.1)."""
    for event in sorted((e for e in events if e.get("type") == "edit_request"), key=lambda e: e["at"]):
        household = next((h for h in households if h["id"] == event["household"]), None)
        if household is None:
            continue
        new_text = EDIT_WORDS.sub(" ", event["new_text"]).strip()
        if household.get("requests") and not [w for w in words(parse_quantity(new_text)[2]) if w not in FILLER_WORDS]:
            new_text = f"{new_text} {parse_quantity(household['requests'][0]['text'])[2]}"  # "make it 1 dozen" keeps the same item
        if event["at"] <= cutoff and household.get("requests"):
            first_added = min(r["added_at"] for r in household["requests"])
            household["requests"] = [{"text": new_text, "added_at": first_added}]
        else:
            household.setdefault("requests", []).append({"text": new_text, "added_at": event["at"]})


# ---------- the run ----------

def run_policy(setup: dict) -> dict:
    catalog = {p["sku"]: dict(p) for p in setup.get("catalog", [])}
    for product in catalog.values():
        if isinstance(product.get("unit"), str) and product["unit"].isdigit():
            product["unit"] = int(product["unit"])
    households = [dict(h) for h in setup.get("households", [])]
    cutoff, replies, events = setup["cutoff"], setup.get("simulated_replies", {}), setup.get("events", [])
    apply_edits(households, events, cutoff)
    result = {
        "line_items": {h["id"]: [] for h in households}, "next_order": {}, "notifications": [], "messages": {},
        "confirmation_requests": [], "clarification_requests": [], "external_orders": [], "payment_status": "pending",
    }

    def notify(to: str, about: str, outcome: str, text: str) -> None:
        result["notifications"].append({"to": to, "about": about, "outcome": outcome})
        result["messages"][f"notification.{to}"] = text

    for change in setup.get("price_changes", []):  # R5.5 charge the checkout price
        product = catalog.get(change["sku"])
        if product and change["at"] <= cutoff:
            product["old_price"], product["price"] = product["price"], change["new_price"]

    cancels = [e for e in events if "cancel" in (e.get("type"), e.get("action"))]

    def cancelled(hid: str, sku: str, before_cutoff: bool) -> bool:
        return any(e["household"] == hid and (e.get("scope") == "all" or e.get("about") == sku) and (e["at"] <= cutoff) == before_cutoff
                   for e in cancels)

    wanted = []  # R3.4 first come, first served: requests in the order they were added
    requests = sorted(((h, r) for h in households for r in h.get("requests", [])), key=lambda hr: hr[1]["added_at"])
    for household, request in requests:
        hid = household["id"]
        for item in split_items(request["text"]):
            number, dozen, query = parse_quantity(item)
            found = candidates_for(query, list(catalog.values()), household)
            if not found:  # R3.6 not carried: drop, never source elsewhere
                notify(hid, item, "dropped", f"Sorry, the store doesn't carry {item}, so it's not in this order. You can add something similar before the cutoff.")
                continue
            ambiguous = len(found) > 1 and len({p["category"] for p in found}) == 1 and not any(isinstance(p.get("unit"), int) for p in found)
            if ambiguous:  # R1.2 ask one short question
                options = sorted(found, key=lambda p: p["price"])
                result["clarification_requests"].append({"to": hid, "about": query, "options_include": [p["sku"] for p in options]})
                listed = ", ".join(f"{p['name']} (${p['price']:.2f})" for p in options)
                result["messages"][f"clarification.{hid}"] = f"Which {query} did you mean: {listed}? Reply with one. If we don't hear back before the cutoff, we'll use your last purchase or leave it out."
                reply = [w for w in words(replies.get(hid, "none")) if w not in FILLER_WORDS and w != "none"]
                chosen = next((p for p in options if any(similar(w, n) for w in reply for n in words(p["name"]))), None)
                if chosen is None:  # R1.3 default to the last purchase, else drop
                    last = last_purchase(household, query)
                    if last not in catalog:
                        notify(hid, query, "dropped", f"We didn't hear which {query} you wanted, so it's not in this order. Add it again with the exact one you want.")
                        continue
                    chosen = catalog[last]
                    notify(hid, query, "defaulted_to_last_purchase", f"No answer on {query}, so we used your last pick: {chosen['name']}. Change it before the cutoff if you like.")
                product, qty = chosen, number or 1
            else:
                product, qty = pick_pack(number, dozen, found)
            if not allowed_for(product, household):  # R1.4 conflicts with the profile need a yes first
                result["confirmation_requests"].append({"to": hid, "about": product["sku"], "reason": "conflicts_with_profile"})
                if not YES.search(replies.get(hid, "none")):
                    notify(hid, product["sku"], "held", f"{product['name']} conflicts with your household profile, so we held it. Reply yes if you still want it.")
                    continue
            if request["added_at"] > cutoff:  # R9.1 late additions roll to the next order
                result["next_order"].setdefault(hid, []).append({"sku": product["sku"], "qty": qty})
                notify(hid, product["sku"], "moved_to_next_order", f"{product['name']} came in after the cutoff, so it's saved for the next order.")
                continue
            if cancelled(hid, product["sku"], before_cutoff=True):  # R9.2 cancelling before cutoff is free
                continue
            if cancelled(hid, product["sku"], before_cutoff=False):  # R9.3 too late to cancel
                notify(hid, product["sku"], "cancel_too_late", f"The order already closed, so {product['name']} stays in it.")
            usual = usual_qty(household, product)
            if usual and qty > OUTLIER_MULTIPLE * usual:  # R4.1 / R4.2 hold unusual quantities until confirmed
                result["confirmation_requests"].append({"to": hid, "qty": qty, "about": product["sku"]})
                result["messages"][f"confirmation.{hid}"] = f"You asked for {qty} × {product['name']}, much more than your usual {usual}. Is {qty} right? Reply yes before the cutoff, or we'll leave it out."
                if not YES.search(replies.get(hid, "none")):
                    notify(hid, product["sku"], "held", f"We held {qty} × {product['name']} because it's far above your usual {usual}. Reply yes to order it.")
                    continue
            if product.get("age_restricted") and not household.get("profile", {}).get("age_verified"):  # R8.3
                notify(hid, product["sku"], "dropped", f"{product['name']} needs age verification, so it's not in this order. Verify your age to add it next time.")
                continue
            if household.get("payment") == "fails":  # R5.6 removed before the order is placed, so its stock goes to the next in line
                continue
            wanted.append({"household": household, "product": product, "qty": qty})

    allocate(wanted, catalog, result, notify)
    charge(setup, households, catalog, result, notify)
    result["views"] = {  # R7.1 the shared cart has no names; each household sees only its own items
        "shared_cart": {"skus": sorted({l["sku"] for ls in result["line_items"].values() for l in ls}), "household_ids": []},
        **{f"household.{h['id']}": {"skus": sorted({l["sku"] for l in result["line_items"][h["id"]]})} for h in households},
    }
    result["store_orders_count"] = 1 if result["order_placed"] else 0  # R9.4 retries never place a second order
    result["charge_attempts"] = {hid: int(c["total"] > 0) for hid, c in result["charges"].items()}
    return result


def allocate(wanted: list[dict], catalog: dict, result: dict, notify) -> None:
    """R3 stock and substitutions, R4.4 store limits. Earlier requests are served first."""
    remaining = {sku: min(p["stock"], p.get("max_per_order", p["stock"])) for sku, p in catalog.items()}
    direct_demand: dict[str, int] = {}
    for w in wanted:
        direct_demand[w["product"]["sku"]] = direct_demand.get(w["product"]["sku"], 0) + w["qty"]

    def add_line(hid: str, sku: str, qty: int) -> None:
        line = next((l for l in result["line_items"][hid] if l["sku"] == sku), None)
        if line:
            line["qty"] += qty
        else:
            result["line_items"][hid].append({"sku": sku, "qty": qty})

    for w in wanted:
        household, product, qty = w["household"], w["product"], w["qty"]
        hid, sku = household["id"], product["sku"]
        direct_demand[sku] -= qty
        got = min(qty, remaining[sku])
        remaining[sku] -= got
        if got:
            add_line(hid, sku, got)
        if product.get("old_price") and product["price"] > product["old_price"] * PRICE_JUMP_FLAG:
            notify(hid, sku, "price_changed", f"{product['name']} went up from ${product['old_price']:.2f} to ${product['price']:.2f}. You can remove it before the cutoff.")
        short = qty - got
        if not short:
            continue
        substitute = None
        if household.get("settings", {}).get("substitutions", "allowed") == "allowed":
            options = [
                p for p in catalog.values()
                if p["sku"] != sku and p["category"] == product["category"] and allowed_for(p, household) and not p.get("age_restricted")
                and fair_substitute_price(p, product)
                and remaining[p["sku"]] - direct_demand.get(p["sku"], 0) >= short  # R3.7 never take stock someone asked for
            ]
            substitute = min(options, key=lambda p: p["price"], default=None)
        if substitute:
            remaining[substitute["sku"]] -= short
            add_line(hid, substitute["sku"], short)
            diff = substitute["price"] - product["price"]
            notify(hid, sku, "substituted", f"{product['name']} was out of stock, so we picked {substitute['name']} ({'+' if diff >= 0 else '-'}${abs(diff):.2f} each). Reply to swap or remove it before the cutoff.")
        elif got:
            notify(hid, sku, "reduced", f"Only {got} of the {qty} {product['name']} you asked for were left, so your order has {got}.")
        else:
            notify(hid, sku, "dropped", f"{product['name']} is out of stock and we couldn't find a fair substitute, so it's not in this order. Try again next order.")


UNIT_SIZES = {"ml": ("ml", 1), "l": ("ml", 1000), "gal": ("ml", 3785), "g": ("g", 1), "kg": ("g", 1000),
              "oz": ("g", 28.35), "lb": ("g", 453.6), "ct": ("ct", 1)}


def price_per_unit(product: dict) -> tuple[str, float]:
    """R3.1 compares price per unit, e.g. $/ml or $/egg, so a bigger pack isn't treated as pricier."""
    unit = product.get("unit")
    if isinstance(unit, int):
        return "ct", product["price"] / unit
    match = re.fullmatch(r"(\d*\.?\d*)\s*([a-z]+)", str(unit).lower())
    if match and match.group(2) in UNIT_SIZES:
        dimension, size = UNIT_SIZES[match.group(2)]
        return dimension, product["price"] / (float(match.group(1) or 1) * size)
    return "item", product["price"]


def fair_substitute_price(substitute: dict, original: dict) -> bool:
    sub_dim, sub_price = price_per_unit(substitute)
    orig_dim, orig_price = price_per_unit(original)
    if sub_dim != orig_dim:
        sub_price, orig_price = substitute["price"], original["price"]
    return sub_price <= orig_price * SUB_PRICE_LIMIT + 1e-9


def split_cents(total_cents: int, weights: dict) -> dict:
    """R5.2 + R5.3 split in proportion to weight, rounded down; all leftover cents go to the largest."""
    total_weight = sum(weights.values())
    shares = {hid: total_cents * weight // total_weight for hid, weight in weights.items()}
    largest = max(weights, key=weights.get)
    shares[largest] += total_cents - sum(shares.values())
    return shares


def charge(setup: dict, households: list[dict], catalog: dict, result: dict, notify) -> None:
    subtotals = {
        h["id"]: h["resolved_subtotal"] if "resolved_subtotal" in h
        else round(sum(catalog[l["sku"]]["price"] * l["qty"] for l in result["line_items"][h["id"]]), 2)
        for h in households
    }
    result["subtotals"] = subtotals
    failed = [h["id"] for h in households if h.get("payment") == "fails"]  # R5.6
    payers = [hid for hid, s in subtotals.items() if s > 0 and hid not in failed]  # R5.3 dropped households pay nothing
    result["charges"] = {h["id"]: {"subtotal": 0.0, "service": 0.0, "delivery": 0.0, "total": 0.0} for h in households}
    minimum = setup.get("store_minimum", 0)
    result["order_placed"] = bool(payers) and sum(subtotals[h] for h in payers) >= minimum
    result["store_order"], result["store_order_households"], result["order_total"] = [], [], 0.0
    if not result["order_placed"]:  # R5.7 below the store minimum nothing is ordered, so nobody receives anything
        result["line_items"] = {h["id"]: [] for h in households}
        if payers:
            for h in households:
                notify(h["id"], "order", "minimum_not_met", f"The group order didn't reach the ${minimum:.2f} store minimum, so nothing was ordered and you weren't charged.")
        return
    subtotal_cents = {hid: round(subtotals[hid] * 100) for hid in payers}
    largest = max(payers, key=lambda h: subtotal_cents[h])
    free_over = setup.get("free_delivery_over")
    delivery_cents = 0 if free_over is not None and sum(subtotals[h] for h in payers) >= free_over else round(setup["delivery_fee"] * 100)
    delivery = {hid: delivery_cents // len(payers) for hid in payers}  # R5.1 equal, R5.3 rounded down
    delivery[largest] += delivery_cents - sum(delivery.values())
    service_total = round(sum(subtotal_cents.values()) * setup["service_fee_pct"] / 100)
    service = split_cents(service_total, subtotal_cents)  # R5.2 in proportion to subtotal
    for hid in payers:
        result["charges"][hid] = {"subtotal": subtotals[hid], "service": service[hid] / 100, "delivery": delivery[hid] / 100,
                                  "total": round(subtotals[hid] + service[hid] / 100 + delivery[hid] / 100, 2)}
    for hid in failed:
        notify(hid, "order", "payment_failed", "Your payment didn't go through, so your items were left out of this order. Update your card to join the next one.")
    store_order: dict[str, int] = {}
    for hid in payers:  # R2.1 one store line per product
        for line in result["line_items"][hid]:
            store_order[line["sku"]] = store_order.get(line["sku"], 0) + line["qty"]
    result["store_order"] = [{"sku": sku, "qty": qty} for sku, qty in store_order.items()]
    result["store_order_households"] = payers
    result["order_total"] = round(sum(c["total"] for c in result["charges"].values()), 2)
