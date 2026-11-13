"""FastAPI routes for the app. The agent only suggests; cart and order changes happen here, by rules."""
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import community, rules, store
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
    data["cart"].remove(line)
    store.save()
    return {"ok": True}


@app.get("/api/delivery")
def delivery(podId: str):
    pod = find_pod_or_404(podId)
    data = store.db()
    leader = store.get_member(pod["leaderId"])
    bags = []
    for bag in rules.bag_list(pod, data["cart"], data["members"]):
        pickup = data["pickups"].get(f"{pod['id']}:{bag['memberId']}", {"paid": False, "collected": False})
        venmo = rules.venmo_link(leader["venmo"], bag["amountDue"], f"HuddleCart {pod['name']} bag #{bag['bag']}") if leader.get("venmo") else None
        bags.append({**bag, "venmo": venmo, "zelle": leader.get("zelle"), **pickup})
    return {"pod": pod, "order": rules.combined_order(pod, data["cart"]), "bags": bags}


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


@app.get("/api/community")
def community_stats():
    return community.community_summary(store.db())


@app.post("/api/reset")
def reset():
    store.reset()
    return {"ok": True}
