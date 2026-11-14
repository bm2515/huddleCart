"""The building order engine for policy v0.2 (evals/new_evals/policy.md).

Code decides: stock, first come first served, substitutes and the 15% limit, allergens and halal, holds,
fee splits, cutoff and retries. A "brain" only does three things, and code checks what it returns:
  - read_request(text, catalog) -> [{"item", "skus", "qty", "pieces"}]   turn request text into catalog matches
  - read_choice(reply, options) -> sku | None, read_yes(reply) -> bool   read a household's reply
  - write(kind, facts) -> str                                            word a message from facts code settled

RuleBrain (below) is deterministic and needs no API key; LLMBrain in order_ai.py uses a model.
Entry point: run_scenario(setup, defaults, brain) -> dict, the shape evals/new_evals/run.py scores.
"""
import math
import re
from datetime import datetime

from .policy import (FILLER_WORDS, OUTLIER_MULTIPLE, YES, allocate, apply_edits, charge, parse_quantity, similar,
                     split_items, usual_qty, words)

DIET_WORDS = {"halal", "kosher", "vegan", "vegetarian"}  # hard constraints only; "organic" is a preference


# ---------- the rule-based brain ----------

class RuleBrain:
    """A small fuzzy parser and fixed wording. Same input, same output."""

    model_name = "rules"

    def read_request(self, text: str, catalog: list[dict]) -> list[dict]:
        reads = []
        for item in split_items(text):  # R8.1 split_items drops anything after "SYSTEM NOTE" and the like
            number, dozen, query = parse_quantity(item)
            products = matching(query, catalog)
            if dozen and (twelve := [p for p in products if p.get("unit") == 12]):
                reads.append({"item": item, "skus": [twelve[0]["sku"]], "qty": number or 1, "pieces": None})
            elif number and products and all(isinstance(p.get("unit"), int) for p in products) and number < max(p["unit"] for p in products):
                reads.append({"item": item, "skus": [p["sku"] for p in products], "qty": None, "pieces": number})
            else:
                reads.append({"item": item, "skus": [p["sku"] for p in products], "qty": number or 1, "pieces": None})
        return reads

    def read_choice(self, reply: str, options: list[dict]) -> str | None:
        said = [w for w in words(reply) if w not in FILLER_WORDS and w != "none"]
        return next((o["sku"] for o in options if any(similar(w, n) for w in said for n in words(o["name"]))), None)

    def read_yes(self, reply: str) -> bool:
        return bool(YES.search(reply or ""))

    def write(self, kind: str, facts: dict) -> str:
        return facts["draft"]


def matching(query: str, catalog: list[dict]) -> list[dict]:
    """Products whose name covers every word asked for, fewest extra words first.
    A diet label isn't counted as an extra word, so "chicken thighs" returns the halal and regular thighs
    and code picks by the household's profile (R1.4)."""
    asked = [w for w in words(query) if w not in FILLER_WORDS and not w.isdigit()]
    if not asked:
        return []
    scored = []
    for product in catalog:
        name = [w for w in words(product["name"]) if not re.fullmatch(r"\d+(lb|oz|ct|ml|l|g|gal|pk)?", w)]
        if all(any(similar(a, n) for n in name) for a in asked):
            extra = [n for n in name if n not in FILLER_WORDS | DIET_WORDS | {"dozen", "half"} and not any(similar(a, n) for a in asked)]
            scored.append((len(extra), product))
    fewest = min((s for s, _ in scored), default=0)
    return [p for s, p in scored if s == fewest]


# ---------- rules code owns ----------

def allowed_for(product: dict, household: dict, catalog: dict) -> bool:
    """Hard constraints. A diet label only counts in categories where some product carries it (eggs needn't say halal)."""
    profile = household.get("profile", {})
    if set(product.get("allergens", []) + product.get("contains", [])) & set(profile.get("allergens", [])):
        return False
    for diet in profile.get("dietary", []):
        labelled = any(diet in p.get("tags", []) for p in catalog.values() if p["category"] == product["category"])
        if labelled and diet not in product.get("tags", []):
            return False
    return True


def conflict_with(product: dict, household: dict) -> str:
    profile = household.get("profile", {})
    clash = set(product.get("allergens", []) + product.get("contains", [])) & set(profile.get("allergens", []))
    return f"{', '.join(sorted(clash))} allergy" if clash else f"{', '.join(profile.get('dietary', []))} profile"


def when(iso) -> str:
    try:
        return datetime.fromisoformat(str(iso)).strftime("%-I:%M %p on %b %-d")
    except ValueError:
        return str(iso)


def no_answer(reply) -> bool:
    return reply is None or str(reply).strip().lower() in ("", "none")


# ---------- the run ----------

def run_scenario(setup: dict, defaults: dict, brain) -> dict:
    setup = {**defaults, **setup}
    catalog = {p["sku"]: dict(p) for p in setup.get("catalog", [])}
    for product in catalog.values():
        if isinstance(product.get("unit"), str) and product["unit"].isdigit():
            product["unit"] = int(product["unit"])
    households = []
    for h in setup.get("households", []):
        h = {**h, "settings": {"substitutions": "not_allowed", **h.get("settings", {})}}  # no setting means no substitutes
        households.append(h)
    cutoff, replies, events = setup["cutoff"], setup.get("simulated_replies", {}), setup.get("events", [])
    deadline = when(cutoff)
    apply_edits(households, events, cutoff)
    for change in setup.get("price_changes", []):  # R5.5 households pay the checkout price
        product = catalog.get(change["sku"])
        if product and change["at"] <= cutoff:
            product["old_price"], product["price"] = product["price"], change["new_price"]

    result = {
        "line_items": {h["id"]: [] for h in households}, "next_order": {}, "notifications": [],
        "clarification_requests": [], "confirmation_requests": [], "external_orders": [],  # R3.6 never another store
        "payment_status": "pending",  # R8.1 no request text can mark anything paid
    }
    to_write: list[tuple[str, dict, dict]] = []  # (kind, record, facts): wording is done last, after every decision
    request_text: dict[tuple[str, str], str] = {}

    def notify(to: str, about: str, outcome: str, draft: str, about_text: str | None = None) -> None:
        record = {"to": to, "about": about, "about_text": about_text or about, "outcome": outcome, "text": ""}
        result["notifications"].append(record)  # R6.1 only the household concerned is told
        to_write.append(("notification", record, {"outcome": outcome, "draft": draft}))

    def ask(kind: str, record: dict, draft: str) -> None:
        result[f"{kind}_requests"].append({**record, "text": ""})
        to_write.append((kind, result[f"{kind}_requests"][-1], {"draft": draft, **{k: v for k, v in record.items() if k != "options"}}))

    def cancelled(hid: str, sku: str, before_cutoff: bool) -> bool:
        return any(e.get("household") == hid and (e.get("scope") == "all" or e.get("about") == sku) and (e["at"] <= cutoff) == before_cutoff
                   for e in events if "cancel" in (e.get("type"), e.get("action")))

    wanted = []
    order = {h["id"]: i for i, h in enumerate(households)}  # R3.4 ties go to whoever joined first
    requests = sorted(((h, r) for h in households for r in h.get("requests", [])), key=lambda hr: (str(hr[1]["added_at"]), order[hr[0]["id"]]))
    for household, request in requests:
        hid, text = household["id"], request["text"]
        for read in brain.read_request(text, list(catalog.values())):  # R8.2 a read only ever touches this household
            item = str(read.get("item") or text)
            products = [catalog[s] for s in dict.fromkeys(read.get("skus") or []) if s in catalog]  # R3.6 never invent a product
            if not products:
                notify(hid, item, "dropped", f"Sorry, the store doesn't carry \"{item}\", so it isn't in this order, and we don't order from other stores. "
                                             "You can add something similar before the cutoff.", text)
                continue
            products = [p for p in products if allowed_for(p, household, catalog)] or products  # R1.4 profile picks among matches
            pieces = read.get("pieces") if isinstance(read.get("pieces"), int) and read["pieces"] > 0 else None
            qty = read.get("qty") if isinstance(read.get("qty"), int) and read["qty"] > 0 else None
            if len(products) > 1 and pieces and all(isinstance(p.get("unit"), int) for p in products):
                products = [min((p for p in products if p["unit"] >= pieces), key=lambda p: p["unit"], default=max(products, key=lambda p: p["unit"]))]
            if len(products) > 1:  # R1.2 ask which one
                options = sorted(products, key=lambda p: p["price"])
                listed = "; ".join(f"{p['name']} (${p['price']:.2f})" for p in options)
                ask("clarification", {"to": hid, "about": item, "about_text": text,
                                      "options": [{k: p.get(k) for k in ("sku", "name", "price", "unit")} for p in options]},
                    f"Which {item} would you like: {listed}? Reply with one. If we don't hear back an hour before the "
                    f"{deadline} cutoff, we'll use what you bought last time, or leave it out if there's nothing to go on.")
                reply = replies.get(hid)
                chosen = None if no_answer(reply) else brain.read_choice(str(reply), options)
                product = next((p for p in options if p["sku"] == chosen), None)
                if product is None:  # R1.3 no usable answer: last purchase, else drop
                    last = household.get("history", {}).get("last_purchase", {})
                    product = next((p for p in options if p["sku"] in last.values()), None)
                    if product is None:
                        notify(hid, item, "dropped", f"We didn't hear which {item} you wanted, so it isn't in this order. "
                                                     "Add it again with the exact one you want.", text)
                        continue
                    notify(hid, item, "defaulted_to_last_purchase", f"We didn't hear which {item} you wanted, so we used your last "
                                                                   f"purchase, {product['name']}. You can change it before the cutoff.", text)
            else:
                product = products[0]
            if pieces and isinstance(product.get("unit"), int):
                qty = math.ceil(pieces / product["unit"])  # R2.2/R2.3 whole packs, never split
            qty = qty or 1
            sku = product["sku"]

            if not allowed_for(product, household, catalog):  # R1.4 asked for something that clashes with the profile
                clash = conflict_with(product, household)
                ask("confirmation", {"to": hid, "about": sku, "about_text": text, "qty": qty, "reason": "conflicts_with_profile"},
                    f"You asked for {product['name']}, which conflicts with your household's {clash}. Do you still want it? Reply yes to add it. "
                    f"It's on hold until you reply, and if we don't hear back by the {deadline} cutoff it won't be ordered.")
                if no_answer(replies.get(hid)) or not brain.read_yes(str(replies[hid])):
                    notify(hid, sku, "held", f"We're holding {product['name']} because it conflicts with your household's {clash}. "
                                             f"Reply yes before the {deadline} cutoff if you still want it; otherwise it won't be in this order.", text)
                    continue
            if str(request["added_at"]) > str(cutoff):  # R9.1 late additions roll to the next order
                result["next_order"].setdefault(hid, []).append({"sku": sku, "qty": qty})
                notify(hid, sku, "moved_to_next_order", f"{product['name']} was added after the {deadline} cutoff, so it's saved for the next order.", text)
                continue
            if cancelled(hid, sku, before_cutoff=True):  # R9.2 free to cancel before cutoff; stock goes to the next in line
                continue
            if cancelled(hid, sku, before_cutoff=False):  # R9.3 too late to cancel
                notify(hid, sku, "cancel_too_late", f"Your order already closed at {deadline}, so {product['name']} stays in it and can't be cancelled.", text)
            usual = usual_qty(household, product)
            if usual and qty > OUTLIER_MULTIPLE * usual:  # R4.1/R4.2 hold an unusual quantity until confirmed
                ask("confirmation", {"to": hid, "about": sku, "about_text": text, "qty": qty, "reason": "outlier"},
                    f"You asked for {qty} × {product['name']}; you usually get {usual}. Did you mean {qty}? Reply yes to keep {qty}, or send the number you want. "
                    f"It's on hold until you reply. If we don't hear back by the {deadline} cutoff it stays out of this order, and the rest of your order goes ahead.")
                if no_answer(replies.get(hid)) or not brain.read_yes(str(replies[hid])):
                    notify(hid, sku, "held", f"We held {qty} × {product['name']} because it's much more than your usual {usual}. "
                                             "Reply yes to order it; if you don't confirm before the cutoff it won't be in this order.", text)
                    continue
            if product.get("age_restricted") and not household.get("profile", {}).get("age_verified"):  # R8.3
                notify(hid, sku, "dropped", f"{product['name']} needs age verification, so it isn't in this order. "
                                            "Verify your age in your profile to order it next time.", text)
                continue
            if household.get("payment") == "fails":  # R5.6 out before the order is placed, so its stock goes to others
                continue
            wanted.append({"household": household, "product": product, "qty": qty})
            request_text[(hid, sku)] = text

    allocate(wanted, catalog, result, lambda hid, sku, outcome, draft: notify(hid, sku, outcome, draft, request_text.get((hid, sku))))

    # R9.4 one store order per cutoff: a retried "place order" finds the order already placed and does nothing.
    placements = [e for e in events if e.get("action") == "place_order"] or [{"action": "place_order"}]
    placed, charge_attempts = False, {h["id"]: 0 for h in households}
    for _ in placements:
        if placed:
            continue
        charge(setup, households, catalog, result, lambda hid, about, outcome, draft: notify(hid, about, outcome, draft, "your order"))
        placed = True
        for hid, c in result["charges"].items():
            charge_attempts[hid] += int(result["order_placed"] and c["total"] > 0)
    result["store_orders_count"] = int(result["order_placed"])
    result["charge_attempts"] = charge_attempts
    result["views"] = {  # R7.1 the shared cart has no names; each household sees only its own lines
        "shared_cart": {"items": [dict(l) for l in result["store_order"]], "household_ids": []},
        **{f"household.{h['id']}": {"items": [dict(l) for l in result["line_items"][h["id"]]]} for h in households},
    }
    for kind, record, facts in to_write:
        record["text"] = brain.write(kind, facts)
    return result
