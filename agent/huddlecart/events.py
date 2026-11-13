"""Community events: a host shares an occasion, neighbors claim dishes, and the ingredients ride the pod's group order.

Plain rules only. Ingredients come from fixed menus (menus.json), so prices never come from the AI.
"""
import json
from pathlib import Path

from . import store

MENUS = json.loads((Path(__file__).parent / "menus.json").read_text())
COURSE_ORDER = ["starter", "main", "side", "dessert", "drink"]
SEARCH_URLS = {"weee": "https://www.sayweee.com/en/search?keyword=", "amazon_fresh": "https://www.amazon.com/s?i=amazonfresh&k="}
XP_PER_DISH_CLAIMED = 30
XP_PER_EVENT_HOSTED = 100


def product_for(ingredient: list, marketplace: str) -> dict:
    title, price = ingredient
    slug = "".join(c if c.isalnum() else "-" for c in title.lower()).strip("-")
    return {
        "id": f"menu-{slug}"[:60], "marketplace": marketplace, "title": title, "price": price, "inStock": True,
        "url": SEARCH_URLS[marketplace] + title.replace(" ", "+"),
        "checkedAt": store.iso(), "source": "snapshot",
    }


def dish_from_menu(menu_dish: dict, marketplace: str, cook_id: str | None = None, wished: bool = True) -> dict:
    return {
        "id": store.new_id(), "name": menu_dish["name"], "course": menu_dish["course"], "veg": menu_dish["veg"],
        "recipe": menu_dish.get("recipe"), "note": None, "cookId": cook_id, "wished": wished and cook_id is None,
        "ingredients": [product_for(i, marketplace) for i in menu_dish["ingredients"]],
    }


def new_event(host_id: str, pod: dict, occasion: str, title: str, date: str, guests: int, avoid: str | None, cooking: set[str]) -> dict:
    menu = MENUS[occasion]
    dishes = [dish_from_menu(d, pod["marketplace"], host_id if d["name"] in cooking else None) for d in menu["dishes"]]
    return {
        "id": store.new_id(), "podId": pod["id"], "hostId": host_id, "occasion": occasion, "emoji": menu["emoji"],
        "title": title or menu["title"], "date": date, "guests": guests, "avoid": avoid, "dishes": dishes, "vibes": [],
    }


def seed_events(pods: dict[str, dict]) -> list[dict]:
    """Two events so the community tab has something happening."""
    def seeded(host_id, pod_id, occasion, hours_away, guests, avoid, cooks: dict[str, str], notes: dict[str, str]):
        event = new_event(host_id, pods[pod_id], occasion, "", store.iso(hours_away), guests, avoid, set())
        for dish in event["dishes"]:
            dish["cookId"] = cooks.get(dish["name"])
            dish["wished"] = dish["cookId"] is None
            dish["note"] = notes.get(dish["name"])
        return event

    return [
        seeded("bisma", "the-house", "holiday", 64, 12, "No pork · 1 vegetarian",
               {"Chicken biryani": "bisma", "Gulab jamun": "bisma", "Paneer tikka masala": "jason", "Vegetable samosas": "mei", "Mango lassi": "uj"},
               {"Mango lassi": "Extra sweet, promise."}),
        seeded("jason", "asian-snacks", "game_night", 40, 6, None,
               {"Spicy shrimp chips": "jason", "Pocky bar": "mei"}, {}),
    ]


def event_summary(event: dict, pod: dict) -> dict:
    cooks = {d["cookId"] for d in event["dishes"] if d["cookId"]}
    coming = cooks | set(event["vibes"]) | {event["hostId"]}
    claimed = [d for d in event["dishes"] if d["cookId"]]
    course_counts = {course: sum(1 for d in claimed if d["course"] == course) for course in COURSE_ORDER}
    return {
        **event,
        "dishes": [{**d, "ingredientsTotal": round(sum(i["price"] for i in d["ingredients"]), 2)} for d in event["dishes"]],
        "podName": pod["name"], "podStatus": pod["status"], "closesAt": pod["cutoff"], "pickupAt": pod["deliveryEta"],
        "pickupSpot": pod["pickupSpot"], "building": pod["building"], "marketplace": pod["marketplace"],
        "claimedCount": len(claimed), "dishCount": len(event["dishes"]), "comingCount": len(coming),
        "cookingCount": len(cooks), "vibesCount": len(event["vibes"]), "courseCounts": course_counts,
        "upForGrabs": [d["name"] for d in event["dishes"] if not d["cookId"]],
    }


def event_xp(events: list[dict], member_id: str) -> int:
    hosted = sum(1 for e in events if e["hostId"] == member_id)
    claimed = sum(1 for e in events for d in e["dishes"] if d["cookId"] == member_id and e["hostId"] != member_id)
    return XP_PER_EVENT_HOSTED * hosted + XP_PER_DISH_CLAIMED * claimed


def invite_text(event: dict, names: dict[str, str]) -> str:
    host = names.get(event["hostId"], event["hostId"])
    open_dishes = [d["name"].lower() for d in event["dishes"] if not d["cookId"]]
    wish = f" and would love someone to bring {', '.join(open_dishes)}" if open_dishes else ""
    return f"{host} is hosting {event['title']}{wish}. Claim a dish, add your own, or just bring the vibes."
