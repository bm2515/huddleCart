"""Community and game layer. Plain counting over order history, no AI."""
from collections import Counter

from . import events

XP_PER_ITEM = 10
XP_PER_ORDER = 50
XP_PER_ORDER_LED = 100
SHIPPING_SAVED_PER_ORDER = 3  # $5 solo shipping minus the $2 pod fee
LEVEL_TITLES = ["New neighbor", "Regular", "Snack scout", "Pod pro", "Building legend"]

BADGES = [  # (badge id, label, emoji, test on a member's stats)
    ("ramen", "Ramen royalty", "🍜", lambda s: s["by_category"]["ramen"] >= 10),
    ("snacks", "Snack scout", "🍘", lambda s: s["by_category"]["snack"] >= 8),
    ("captain", "Pod captain", "🧑‍✈️", lambda s: s["orders_led"] >= 2),
    ("streak", "On a roll", "🔥", lambda s: s["streak_weeks"] >= 3),
    ("saver", "Shipping saver", "💸", lambda s: s["shipping_saved"] >= 9),
    ("fresh", "Fresh picker", "🥬", lambda s: s["by_category"]["fresh"] >= 5),
]


def level_for(xp: int) -> dict:
    level = min(len(LEVEL_TITLES), 1 + xp // 300)
    next_at = level * 300
    return {"level": level, "title": LEVEL_TITLES[level - 1], "xp": xp, "nextLevelXp": next_at, "progress": min(1, (xp % 300) / 300)}


def streak_weeks(weeks: set[int], current_week: int) -> int:
    streak = 0
    while (current_week - streak) in weeks:
        streak += 1
    return streak


def member_stats(member_id: str, history: list[dict], current_week: int, bonus_xp: int = 0) -> dict:
    lines = [h for h in history if h["memberId"] == member_id]
    orders = {(h["week"], h["podId"]) for h in lines}
    led = {(h["week"], h["podId"]) for h in history if h.get("leaderId") == member_id}
    by_category = Counter()
    for line in lines:
        by_category[line["category"]] += line["qty"]
    items = sum(line["qty"] for line in lines)
    stats = {
        "items": items,
        "orders": len(orders),
        "orders_led": len(led),
        "streak_weeks": streak_weeks({week for week, _ in orders}, current_week),
        "shipping_saved": SHIPPING_SAVED_PER_ORDER * len(orders),
        "by_category": by_category,
    }
    xp = XP_PER_ITEM * items + XP_PER_ORDER * len(orders) + XP_PER_ORDER_LED * len(led) + bonus_xp
    stats["badges"] = [{"id": b, "label": label, "emoji": emoji} for b, label, emoji, earned in BADGES if earned(stats)]
    stats["level"] = level_for(xp)
    return stats


def fun_facts(history: list[dict], names: dict[str, str], week: int) -> list[str]:
    """Lines like 'Jason ate 12 ramens last week'."""
    last_week = [h for h in history if h["week"] == week]
    totals = Counter()
    for line in last_week:
        totals[(line["memberId"], line["category"])] += line["qty"]
    words = {"ramen": "ramen packs", "snack": "snacks", "fresh": "fresh picks", "dairy": "dairy items", "pantry": "pantry staples"}
    facts = []
    for (member_id, category), qty in totals.most_common(3):
        facts.append(f"{names[member_id]} grabbed {qty} {words.get(category, category)} last week")
    return facts


def past_orders(history: list[dict], member_id: str, pod_names: dict[str, str]) -> list[dict]:
    """One entry per (week, pod) the neighbor bought in, newest first."""
    orders: dict[tuple[int, str], dict] = {}
    for line in (h for h in history if h["memberId"] == member_id):
        order = orders.setdefault((line["week"], line["podId"]), {
            "week": line["week"], "podId": line["podId"], "podName": pod_names.get(line["podId"], line["podId"]),
            "items": [], "saved": SHIPPING_SAVED_PER_ORDER,
        })
        order["items"].append({"title": line["title"], "qty": line["qty"]})
    return sorted(orders.values(), key=lambda o: -o["week"])


def community_summary(data: dict) -> dict:
    history = data.get("history", [])
    current_week = max((h["week"] for h in history), default=0)
    names = {m["id"]: m["name"] for m in data["members"]}
    members = []
    for member in data["members"]:
        stats = member_stats(member["id"], history, current_week, events.event_xp(data.get("events", []), member["id"]))
        stats["by_category"] = dict(stats["by_category"])
        members.append({"memberId": member["id"], "name": member["name"], **stats})
    leaderboard = sorted(members, key=lambda m: -m["level"]["xp"])
    return {
        "members": {m["memberId"]: m for m in members},
        "leaderboard": [{"memberId": m["memberId"], "name": m["name"], "xp": m["level"]["xp"], "level": m["level"]["level"]} for m in leaderboard],
        "funFacts": fun_facts(history, names, current_week),
        "buildingSavings": sum(m["shipping_saved"] for m in members),
        "questRewardXp": 50,
    }
