import re
"""FastAPI routes for the app. The agent only suggests; cart and order changes happen here, by rules."""
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import community, events, rules, store
from .agent import run_agent

app = FastAPI(title="HuddleCart agent")


@app.middleware("http")
async def fresh_state_per_request(request: Request, call_next):
    store.forget()
    return await call_next(request)


@app.exception_handler(HTTPException)
def explain_error(_: Request, error: HTTPException):
    return JSONResponse({"ok": False, "error": error.detail, "reason": error.detail}, status_code=error.status_code)

ORDER_STEPS = {  # action: (allowed current statuses, next status)
    "lock": (["open"], "locked"),
    "ordered": (["locked"], "ordered"),
    "arrived": (["ordered"], "arrived"),
    "close": (["arrived"], "closed"),
}


def find_pod_or_404(pod_id: str) -> dict:
    pod = store.get_pod(pod_id)
    if pod is None:
        raise HTTPException(404, "Unknown pod")
    return pod


def chat_message(pod_id: str, author_id: str, role: str, blocks: list[dict]) -> dict:
    return {"id": store.new_id(), "podId": pod_id, "authorId": author_id, "role": role, "blocks": blocks, "createdAt": store.iso()}


def text_of(message: dict) -> str:
    return " ".join(b["text"] for b in message["blocks"] if b["type"] == "text")


@app.get("/api/pods")
def list_pods(podId: str | None = None):
    data = store.db()
    pods = [{**pod, "totals": rules.cart_totals(pod, data["cart"])} for pod in data["pods"]]
    if podId is None:
        return {"pods": pods, "members": data["members"]}
    pod = next((p for p in pods if p["id"] == podId), None)
    if pod is None:
        raise HTTPException(404, "Unknown pod")
    return {
        "pod": pod,
        "members": data["members"],
        "cart": [line for line in data["cart"] if line["podId"] == podId],
        "messages": [m for m in data["messages"] if m["podId"] == podId],
        "pickups": data["pickups"],
    }


class JoinPod(BaseModel):
    podId: str
    memberId: str


@app.post("/api/pods/join")
def join_pod(body: JoinPod):
    pod = find_pod_or_404(body.podId)
    member = store.get_member(body.memberId)
    if member is None:
        raise HTTPException(404, "Unknown neighbor")
    if body.memberId in pod["memberIds"]:
        return {"ok": True, "alreadyMember": True}
    if pod["status"] != "open":
        raise HTTPException(409, f"This pod is {pod['status']}, so it can't take new neighbors.")
    pod["memberIds"].append(body.memberId)
    store.db()["messages"].append(chat_message(pod["id"], "huddlecart", "system", [{"type": "text", "text": f"{member['name']} joined the pod. Welcome!"}]))
    store.save()
    return {"ok": True}


class StartPod(BaseModel):
    memberId: str
    name: str
    marketplace: str
    building: str
    pickupSpot: str
    closesInHours: float = 24
    deliveryHoursAfterClose: float = 18


@app.post("/api/pods")
def start_pod(body: StartPod):
    """Any neighbor can lead a pod: they place the one group order, receive the bags and hand them out."""
    member = store.get_member(body.memberId)
    if member is None:
        raise HTTPException(404, "Unknown neighbor")
    if body.marketplace not in rules.MARKETPLACE_NAMES:
        raise HTTPException(400, "Pick Weee! or Amazon Fresh")
    if not body.name.strip() or not body.pickupSpot.strip():
        raise HTTPException(400, "Give the pod a name and a pickup spot")
    if not 1 <= body.closesInHours <= 168:
        raise HTTPException(400, "The pod should close within a week")
    slug = re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")[:24] or "pod"
    pod_id = f"{slug}-{store.new_id()[:4]}"
    pod = store._pod(pod_id, body.name.strip(), body.memberId, [body.memberId], body.marketplace, 49 if body.marketplace == "weee" else 35,
                     body.closesInHours, body.closesInHours + body.deliveryHoursAfterClose, body.pickupSpot.strip(), body.building)
    store.db()["pods"].append(pod)
    store.db()["messages"].append(chat_message(pod_id, "huddlecart", "system", [{"type": "text", "text": f"{member['name']} started this pod and is leading it 👑"}]))
    store.save()
    return {"ok": True, "pod": pod}


class ChatRequest(BaseModel):
    podId: str
    memberId: str
    text: str
    tier: str = "fast"


@app.post("/api/chat")
def chat(body: ChatRequest):
    find_pod_or_404(body.podId)
    data = store.db()
    history = [
        {"role": m["role"], "text": text_of(m)}
        for m in data["messages"]
        if m["podId"] == body.podId and m["authorId"] in (body.memberId, "huddlecart") and m["role"] != "system"
    ]
    user_message = chat_message(body.podId, body.memberId, "user", [{"type": "text", "text": body.text}])
    data["messages"].append(user_message)
    store.save()
    try:
        blocks = run_agent(body.podId, body.memberId, body.text, history, body.tier)["blocks"]
        error = None
    except Exception as exc:
        print(f"agent failed: {exc}")
        blocks = [{"type": "text", "text": "Sorry, I couldn't reach the grocery search just now. Try again in a moment."}]
        error = str(exc)
    agent_message = chat_message(body.podId, "huddlecart", "agent", blocks)
    store.forget()  # others may have changed the cart while the agent was thinking
    store.db()["messages"].append(agent_message)
    store.save()
    return {"messages": [user_message, agent_message], "error": error}


class AddToCart(BaseModel):
    podId: str
    memberId: str
    product: dict
    qty: int
    requestId: str | None = None


@app.post("/api/cart")
def add_to_cart(body: AddToCart):
    pod = find_pod_or_404(body.podId)
    data = store.db()
    if body.memberId not in pod["memberIds"]:
        raise HTTPException(403, "Not a member of this pod")
    if body.requestId and any(line["id"] == body.requestId for line in data["cart"]):
        return {"ok": True, "duplicate": True, "totals": rules.cart_totals(pod, data["cart"])}
    reason = rules.why_cannot_add(pod, body.product, body.qty)
    if reason:
        raise HTTPException(409, reason)
    same_line = next(
        (l for l in data["cart"] if l["podId"] == pod["id"] and l["memberId"] == body.memberId and l["product"]["id"] == body.product["id"]),
        None,
    )
    if same_line:
        same_line["qty"] = min(20, same_line["qty"] + body.qty)
    else:
        data["cart"].append({
            "id": body.requestId or store.new_id(), "podId": pod["id"], "memberId": body.memberId,
            "product": body.product, "qty": body.qty, "addedAt": store.iso(),
        })
    store.save()
    return {"ok": True, "totals": rules.cart_totals(pod, data["cart"])}


class RemoveFromCart(BaseModel):
    lineId: str
    memberId: str


@app.delete("/api/cart")
def remove_from_cart(body: RemoveFromCart):
    data = store.db()
    line = next((l for l in data["cart"] if l["id"] == body.lineId), None)
    if line is None:
        raise HTTPException(404, "Not found")
    pod = find_pod_or_404(line["podId"])
    if body.memberId not in (line["memberId"], pod["leaderId"]):
        raise HTTPException(403, "Not allowed")
    if pod["status"] != "open":
        raise HTTPException(409, "Cart is locked")
    if line.get("orderId"):
        raise HTTPException(409, "That item is already in a placed order")
    data["cart"].remove(line)
    store.save()
    return {"ok": True}


def bags_with_pickup(pod: dict, data: dict) -> list[dict]:
    """Each neighbor's bag plus how to pay the leader, the pickup code, and paid/collected state."""
    leader = store.get_member(pod["leaderId"])
    bags = []
    for bag in rules.bag_list(pod, data["cart"], data["members"]):
        pickup = data["pickups"].get(f"{pod['id']}:{bag['memberId']}", {"paid": False, "collected": False})
        venmo = rules.venmo_link(leader["venmo"], bag["amountDue"], f"HuddleCart {pod['name']} bag #{bag['bag']}") if leader.get("venmo") else None
        code = rules.pickup_code(pod["id"], bag["bag"])
        token = rules.pickup_token(pod["id"], bag["memberId"])
        bags.append({**bag, "venmo": venmo, "zelle": leader.get("zelle"), "pickupCode": code, "pickupToken": token, **pickup})
    return bags


def find_bag_by_token(token: str) -> tuple[dict, dict]:
    data = store.db()
    for pod in data["pods"]:
        for bag in bags_with_pickup(pod, data):
            if bag["pickupToken"] == token:
                return pod, bag
    raise HTTPException(404, "This pickup pass isn't valid")


@app.get("/api/pickup/{token}")
def pickup_pass(token: str):
    pod, bag = find_bag_by_token(token)
    return {"pod": pod, "bag": bag, "hostName": member_name(pod["leaderId"])}


class ConfirmHandoff(BaseModel):
    memberId: str
    collectedBy: str | None = None


@app.post("/api/pickup/{token}/confirm")
def confirm_handoff(token: str, body: ConfirmHandoff):
    """The host scanned the pass and handed over the bag. Saves who confirmed it and when, as proof."""
    pod, bag = find_bag_by_token(token)
    if body.memberId != pod["leaderId"]:
        raise HTTPException(403, "Only the pod host can confirm a handoff")
    if pod["status"] not in ("arrived", "closed"):
        raise HTTPException(409, "The order hasn't arrived yet")
    if bag["collected"]:
        return {"ok": True, "alreadyCollected": True}
    data = store.db()
    collected_by = (body.collectedBy or "").strip() or bag["name"]
    key = f"{pod['id']}:{bag['memberId']}"
    data["pickups"][key] = {
        **data["pickups"].get(key, {"paid": False}), "collected": True,
        "collectedAt": store.iso(), "confirmedBy": body.memberId, "collectedBy": collected_by,
    }
    on_behalf = "" if collected_by == bag["name"] else f" for {bag['name']}"
    data["messages"].append(chat_message(pod["id"], "huddlecart", "system", [
        {"type": "text", "text": f"Bag #{bag['bag']} handed to {collected_by}{on_behalf} ✓ Confirmed by {member_name(pod['leaderId'])}."}
    ]))
    store.save()
    return {"ok": True}


@app.get("/api/delivery")
def delivery(podId: str):
    pod = find_pod_or_404(podId)
    data = store.db()
    return {"pod": pod, "order": rules.combined_order(pod, data["cart"]), "bags": bags_with_pickup(pod, data)}


@app.get("/api/orders")
def my_orders(memberId: str):
    """Everything one neighbor has ordered: bags in pods running now, plus past pod orders."""
    data = store.db()
    current = [
        {"pod": pod, **bag}
        for pod in data["pods"]
        for bag in bags_with_pickup(pod, data)
        if bag["memberId"] == memberId
    ]
    past = community.past_orders(data.get("history", []), memberId, {p["id"]: p["name"] for p in data["pods"]})
    checkouts = [c for c in data["checkouts"] if c["memberId"] == memberId]
    return {"current": current, "past": past, "checkouts": checkouts, "lifetimeSavings": community.SHIPPING_SAVED_PER_ORDER * len(past)}


class DeliveryAction(BaseModel):
    podId: str
    memberId: str
    action: str
    targetId: str | None = None


def status_announcement(action: str, pod: dict, bags: list[dict]) -> str:
    if action == "lock":
        item_count = sum(len(b["items"]) for b in bags)
        neighbors = "neighbor" if len(bags) == 1 else "neighbors"
        items = "item" if item_count == 1 else "items"
        return f"Cart locked. {len(bags)} {neighbors}, {item_count} {items}. The leader is placing the order now."
    if action == "ordered":
        return "Order placed. We'll post here when it arrives."
    if action == "arrived":
        return f"It's here! Pick up at {pod['pickupSpot']}. Your bag number and amount are below."
    return "Pod closed. Thanks, neighbors!"


@app.post("/api/delivery")
def update_delivery(body: DeliveryAction):
    pod = find_pod_or_404(body.podId)
    data = store.db()
    if body.action in ("paid", "collected"):
        who = body.targetId or body.memberId
        if who != body.memberId and pod["leaderId"] != body.memberId:
            raise HTTPException(403, "Not allowed")
        key = f"{pod['id']}:{who}"
        data["pickups"][key] = {**data["pickups"].get(key, {"paid": False, "collected": False}), body.action: True}
        store.save()
        return {"ok": True}
    if pod["leaderId"] != body.memberId:
        raise HTTPException(403, "Only the pod leader can do that")
    allowed_from, next_status = ORDER_STEPS.get(body.action, ([], None))
    if pod["status"] not in allowed_from:
        raise HTTPException(409, f"Can't {body.action} a pod that is {pod['status']}")
    pod["status"] = next_status
    bags = rules.bag_list(pod, data["cart"], data["members"])
    data["messages"].append(chat_message(pod["id"], "huddlecart", "system", [{"type": "text", "text": status_announcement(body.action, pod, bags)}]))
    store.save()
    return {"ok": True, "status": pod["status"]}


# ---------- checkout: a neighbor places their part of the group order from the chat ----------

class Checkout(BaseModel):
    podId: str
    memberId: str


@app.post("/api/checkout")
def checkout(body: Checkout):
    pod = find_pod_or_404(body.podId)
    data = store.db()
    if body.memberId not in pod["memberIds"]:
        raise HTTPException(403, "Join the pod first")
    if pod["status"] != "open":
        raise HTTPException(409, f"This pod is {pod['status']}, so new orders are closed.")
    basket = [l for l in data["cart"] if l["podId"] == pod["id"] and l["memberId"] == body.memberId and not l.get("orderId")]
    if not basket:
        raise HTTPException(409, "Your basket is empty")
    already_paid_fee = any(c["podId"] == pod["id"] and c["memberId"] == body.memberId for c in data["checkouts"])
    items_total = round(sum(rules.line_total(l) for l in basket), 2)
    fee = 0 if already_paid_fee else pod["feePerPerson"]
    order = {
        "id": store.new_id(), "number": f"HC-{len(data['checkouts']) + 1042}", "podId": pod["id"], "memberId": body.memberId,
        "items": [{"title": l["product"]["title"], "qty": l["qty"], "total": rules.line_total(l)} for l in basket],
        "itemsTotal": items_total, "fee": fee, "total": round(items_total + fee, 2), "placedAt": store.iso(),
    }
    for line in basket:
        line["orderId"] = order["id"]
    data["checkouts"].append(order)
    leader = store.get_member(pod["leaderId"])
    data["messages"].append(chat_message(pod["id"], "huddlecart", "agent", [
        {"type": "text", "text": f"Done! Order {order['number']} is placed. It ships with the group order, so you pay {leader['name']} after pickup."},
        {"type": "order_placed", "order": order, "pickupSpot": pod["pickupSpot"], "deliveryEta": pod["deliveryEta"]},
    ]))
    store.save()
    return {"ok": True, "order": order}


# ---------- community events ----------

def find_event_or_404(event_id: str) -> dict:
    event = next((e for e in store.db()["events"] if e["id"] == event_id), None)
    if event is None:
        raise HTTPException(404, "Unknown event")
    return event


def find_dish_or_404(event: dict, dish_id: str) -> dict:
    dish = next((d for d in event["dishes"] if d["id"] == dish_id), None)
    if dish is None:
        raise HTTPException(404, "Unknown dish")
    return dish


def join_if_needed(pod: dict, member_id: str) -> None:
    if member_id not in pod["memberIds"]:
        pod["memberIds"].append(member_id)


def add_ingredients(pod: dict, member_id: str, dish: dict) -> None:
    for product in dish["ingredients"]:
        reason = rules.why_cannot_add(pod, product, 1)
        if reason:
            raise HTTPException(409, reason)
    for product in dish["ingredients"]:
        store.db()["cart"].append({
            "id": store.new_id(), "podId": pod["id"], "memberId": member_id, "product": product, "qty": 1,
            "addedAt": store.iso(), "dishId": dish["id"],
        })


def post_to_pod(pod_id: str, text: str, blocks: list[dict] | None = None, role: str = "system") -> None:
    store.db()["messages"].append(chat_message(pod_id, "huddlecart", role, [{"type": "text", "text": text}, *(blocks or [])]))


def member_name(member_id: str) -> str:
    member = store.get_member(member_id)
    return member["name"] if member else member_id


@app.get("/api/events")
def list_events(eventId: str | None = None):
    data = store.db()
    summaries = [events.event_summary(e, store.get_pod(e["podId"])) for e in data["events"]]
    if eventId is None:
        return {"events": summaries, "menus": events.MENUS}
    summary = next((e for e in summaries if e["id"] == eventId), None)
    if summary is None:
        raise HTTPException(404, "Unknown event")
    return {"event": summary, "members": data["members"]}


class HostEvent(BaseModel):
    hostId: str
    podId: str
    occasion: str
    title: str = ""
    date: str
    guests: int = 8
    avoid: str | None = None
    cooking: list[str] = []


@app.post("/api/events")
def host_event(body: HostEvent):
    pod = find_pod_or_404(body.podId)
    if body.occasion not in events.MENUS:
        raise HTTPException(400, "Unknown occasion")
    if pod["status"] != "open":
        raise HTTPException(409, "Pick a pod that is still open, so ingredients can join its order.")
    join_if_needed(pod, body.hostId)
    event = events.new_event(body.hostId, pod, body.occasion, body.title.strip(), body.date, max(2, min(body.guests, 50)), body.avoid, set(body.cooking))
    for dish in event["dishes"]:
        if dish["cookId"] == body.hostId:
            add_ingredients(pod, body.hostId, dish)
    store.db()["events"].append(event)
    names = {m["id"]: m["name"] for m in store.db()["members"]}
    post_to_pod(pod["id"], events.invite_text(event, names), [{"type": "event_invite", "eventId": event["id"]}], role="agent")
    store.save()
    return {"ok": True, "event": event}


class DishAction(BaseModel):
    eventId: str
    memberId: str
    dishId: str | None = None
    addIngredients: bool = True
    name: str | None = None
    course: str = "side"
    note: str | None = None


@app.post("/api/events/claim")
def claim_dish(body: DishAction):
    event = find_event_or_404(body.eventId)
    dish = find_dish_or_404(event, body.dishId or "")
    pod = find_pod_or_404(event["podId"])
    if dish["cookId"] and dish["cookId"] != body.memberId:
        raise HTTPException(409, f"{member_name(dish['cookId'])} already claimed {dish['name']}")
    join_if_needed(pod, body.memberId)
    dish["cookId"] = body.memberId
    if body.addIngredients:
        add_ingredients(pod, body.memberId, dish)
    if body.memberId in event["vibes"]:
        event["vibes"].remove(body.memberId)
    post_to_pod(pod["id"], f"{member_name(body.memberId)} is bringing {dish['name']} to {event['title']} 🎉")
    store.save()
    return {"ok": True}


@app.post("/api/events/unclaim")
def unclaim_dishes(body: DishAction):
    """Change my pick: drop my dishes and vibes, and take back ingredients that aren't ordered yet."""
    event = find_event_or_404(body.eventId)
    data = store.db()
    my_dish_ids = {d["id"] for d in event["dishes"] if d["cookId"] == body.memberId}
    data["cart"] = [l for l in data["cart"] if not (l.get("dishId") in my_dish_ids and l["memberId"] == body.memberId and not l.get("orderId"))]
    event["dishes"] = [d for d in event["dishes"] if not (d["cookId"] == body.memberId and not d["ingredients"] and not d["wished"])]
    for dish in event["dishes"]:
        if dish["cookId"] == body.memberId:
            dish["cookId"] = None
            dish["wished"] = True
    if body.memberId in event["vibes"]:
        event["vibes"].remove(body.memberId)
    store.save()
    return {"ok": True}


@app.post("/api/events/dish")
def add_own_dish(body: DishAction):
    event = find_event_or_404(body.eventId)
    if not (body.name or "").strip():
        raise HTTPException(400, "Name your dish")
    pod = find_pod_or_404(event["podId"])
    join_if_needed(pod, body.memberId)
    course = body.course if body.course in events.COURSE_ORDER else "side"
    event["dishes"].append({
        "id": store.new_id(), "name": body.name.strip(), "course": course, "veg": False, "recipe": None,
        "note": (body.note or "").strip() or None, "cookId": body.memberId, "wished": False, "ingredients": [],
    })
    post_to_pod(pod["id"], f"{member_name(body.memberId)} is bringing {body.name.strip()} to {event['title']} 🎉")
    store.save()
    return {"ok": True}


@app.post("/api/events/vibes")
def bring_vibes(body: DishAction):
    event = find_event_or_404(body.eventId)
    if body.memberId not in event["vibes"] and not any(d["cookId"] == body.memberId for d in event["dishes"]):
        event["vibes"].append(body.memberId)
        post_to_pod(event["podId"], f"{member_name(body.memberId)} is coming to {event['title']} to bring the vibes ✨")
        store.save()
    return {"ok": True}


@app.post("/api/events/nudge")
def nudge(body: DishAction):
    event = find_event_or_404(body.eventId)
    if body.memberId != event["hostId"]:
        raise HTTPException(403, "Only the host can nudge")
    open_dishes = [d["name"] for d in event["dishes"] if not d["cookId"]]
    text = f"Still up for grabs at {event['title']}: {', '.join(open_dishes)}. Tap to claim one!" if open_dishes else f"Every dish for {event['title']} is claimed. See you there!"
    post_to_pod(event["podId"], text, [{"type": "event_invite", "eventId": event["id"]}], role="agent")
    store.save()
    return {"ok": True}


@app.get("/api/community")
def community_stats():
    return community.community_summary(store.db())


@app.post("/api/reset")
def reset():
    store.reset()
    return {"ok": True}
