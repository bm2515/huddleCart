"""Deterministic rules. No AI here: money, stock, cutoffs and permissions are plain code."""
from datetime import datetime
from urllib.parse import quote, urlencode

from .store import now

MARKETPLACE_NAMES = {"weee": "Weee!", "amazon_fresh": "Amazon Fresh"}


def line_total(line: dict) -> float:
    return round((line["product"]["price"] or 0) * line["qty"], 2)


def cart_totals(pod: dict, cart: list[dict]) -> dict:
    lines = [l for l in cart if l["podId"] == pod["id"]]
    subtotal = round(sum(line_total(l) for l in lines), 2)
    remaining = round(max(0, pod["minimumForFreeShipping"] - subtotal), 2)
    return {
        "subtotal": subtotal,
        "remaining": remaining,
        "progress": min(1, subtotal / pod["minimumForFreeShipping"]),
        "freeShipping": remaining == 0,
        "itemCount": sum(l["qty"] for l in lines),
        "buyers": len({l["memberId"] for l in lines}),
    }


def why_cannot_add(pod: dict, product: dict, qty: int) -> str | None:
    """Return a reason the item can't be added, or None if it's fine."""
    if pod["status"] != "open":
        return f"This pod is {pod['status']}, so the cart is closed."
    if now() > datetime.fromisoformat(pod["cutoff"]):
        return "The cutoff for this pod has passed."
    if product["marketplace"] != pod["marketplace"]:
        return f"This pod orders from {MARKETPLACE_NAMES[pod['marketplace']]} only."
    if product.get("inStock") is False:
        return "That item is out of stock."
    if product.get("price") is None:
        return "We couldn't confirm a price for that item."
    if not 1 <= qty <= 20:
        return "Quantity must be 1 to 20."
    return None


def pods_delivering_by(pods: list[dict], deadline: datetime | None) -> list[dict]:
    open_pods = [p for p in pods if p["status"] == "open" and datetime.fromisoformat(p["cutoff"]) > now()]
    in_time = [p for p in open_pods if deadline is None or datetime.fromisoformat(p["deliveryEta"]) <= deadline]
    return sorted(in_time, key=lambda p: p["deliveryEta"])


def bag_list(pod: dict, cart: list[dict], members: list[dict]) -> list[dict]:
    names = {m["id"]: m["name"] for m in members}
    by_member: dict[str, list[dict]] = {}
    for line in (l for l in cart if l["podId"] == pod["id"]):
        by_member.setdefault(line["memberId"], []).append(line)
    bags = []
    for bag_number, (member_id, lines) in enumerate(by_member.items(), start=1):
        items_total = round(sum(line_total(l) for l in lines), 2)
        bags.append({
            "bag": bag_number,
            "memberId": member_id,
            "name": names.get(member_id, member_id),
            "items": [{"title": l["product"]["title"], "qty": l["qty"], "total": line_total(l)} for l in lines],
            "itemsTotal": items_total,
            "fee": pod["feePerPerson"],
            "amountDue": round(items_total + pod["feePerPerson"], 2),
        })
    return bags


def combined_order(pod: dict, cart: list[dict]) -> list[dict]:
    combined: dict[str, dict] = {}
    for line in (l for l in cart if l["podId"] == pod["id"]):
        entry = combined.setdefault(line["product"]["id"], {"product": line["product"], "qty": 0})
        entry["qty"] += line["qty"]
    return list(combined.values())


def venmo_link(handle: str, amount: float, note: str) -> str:
    query = urlencode({"txn": "pay", "amount": f"{amount:.2f}", "note": note})
    return f"https://venmo.com/{quote(handle)}?{query}"
