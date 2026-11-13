"""The HuddleCart agent as a LangGraph graph.

load_pod -> understand -> search_catalog -> rank -> compose
AI is used only in `understand` (read messy words) and `rank` (pick the best match).
Everything else is a tool call or plain rules.
"""
import os
from typing import Literal, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from . import store
from .tools import find_open_pods, get_pod_details, search_products

PROVIDER = os.getenv("HUDDLECART_PROVIDER", "google" if os.getenv("GOOGLE_API_KEY") else "openai")
DEFAULT_MODELS = {
    "google": {"fast": "gemini-3.5-flash-lite", "strong": "gemini-3-flash-preview"},
    "openai": {"fast": "gpt-5.4-mini", "strong": "gpt-5.5"},
}
MODELS = {
    "fast": os.getenv("HUDDLECART_FAST_MODEL", DEFAULT_MODELS[PROVIDER]["fast"]),
    "strong": os.getenv("HUDDLECART_STRONG_MODEL", DEFAULT_MODELS[PROVIDER]["strong"]),
}

HOUSE_RULES = """You are HuddleCart, the grocery helper inside a neighborhood pod chat.
House rules (true for every pod):
- A pod is one shared grocery order for one building, run by a leader neighbor.
- Allowed marketplaces: Weee! (weee) and Amazon Fresh (amazon_fresh). Each pod orders from exactly one.
- Each buyer pays their items plus the pod's flat fee (usually $2). Payment goes to the leader by Venmo or Zelle.
- Items are picked up at the pod's pickup spot.
- Nothing is added to a cart until the neighbor taps Add. You only suggest.
- Never invent prices or stock. Only use products returned by search.
- If a request is vague, show options instead of guessing. If an item is out of stock, say so and offer alternatives.
- Alcohol, tobacco and prescription items are not allowed.
Write short, friendly, plain sentences. No em dashes."""


class ItemRequest(BaseModel):
    query: str = Field(description="Short product search query, e.g. 'shrimp chips'")
    qty: int = Field(default=1, ge=1, le=20)
    notes: str | None = Field(default=None, description="Size, flavor or brand preferences")


class Understanding(BaseModel):
    intent: Literal["add_items", "find_pod", "cart_status", "chit_chat", "not_allowed"] = Field(
        description="add_items: wants groceries in this pod. find_pod: needs it by a deadline or asks which pod/store. "
        "cart_status: asks about the cart. not_allowed: alcohol, tobacco, prescriptions."
    )
    items: list[ItemRequest] = Field(default_factory=list, description="Every grocery mentioned, for add_items and find_pod")
    deadline_hours: float | None = Field(default=None, description="Hours from now the user needs it by, if stated")
    reply: str = Field(description="One short sentence to the neighbor. Don't name a store or state prices, stock or delivery times; the cards show those.")


class Pick(BaseModel):
    query: str
    recommended_id: str | None = Field(description="Best matching product id, or null if nothing fits")
    is_ambiguous: bool = Field(description="True if several products fit equally and the neighbor should choose")
    reason: str = Field(description="Why this pick, in under 15 words")


class Ranking(BaseModel):
    picks: list[Pick]


class AgentState(TypedDict, total=False):
    pod_id: str
    member_id: str
    message: str
    history: list[dict]
    tier: str
    pod: dict
    understanding: Understanding
    candidates: list[list[dict]]
    ranking: Ranking
    blocks: list[dict]


def chat_model(name: str) -> BaseChatModel:
    if name.startswith(("gemini", "gemma")):
        return ChatGoogleGenerativeAI(model=name, temperature=0)
    return ChatOpenAI(model=name, temperature=0)


def model(state: AgentState) -> BaseChatModel:
    return chat_model(MODELS[state.get("tier", "fast")])


def pod_summary(pod: dict) -> str:
    totals = pod["totals"]
    return (
        f"Now: {store.iso()}. Current pod: {pod['name']} ({pod['id']}), orders from {pod['marketplaceName']}, leader {pod['leaderName']}. "
        f"Status {pod['status']}. Cutoff {pod['cutoff']}. Delivery around {pod['deliveryEta']}. Pickup at {pod['pickupSpot']}. "
        f"Cart ${totals['subtotal']} of ${pod['minimumForFreeShipping']} for free shipping."
    )


def chat_history(history: list[dict]) -> list:
    turns = []
    for message in history[-6:]:
        text = message.get("text") or ""
        turns.append(AIMessage(text) if message["role"] == "agent" else HumanMessage(text))
    return turns


# ---------- nodes ----------

def load_pod(state: AgentState) -> AgentState:
    return {"pod": get_pod_details.invoke({"pod_id": state["pod_id"]})}


def understand(state: AgentState) -> AgentState:
    prompt = [
        SystemMessage(f"{HOUSE_RULES}\n\n{pod_summary(state['pod'])}"),
        *chat_history(state.get("history", [])),
        HumanMessage(state["message"]),
    ]
    understanding = model(state).with_structured_output(Understanding).invoke(prompt)
    if understanding.deadline_hours and understanding.intent == "add_items":
        understanding.intent = "find_pod"  # rule: a deadline means we must check which pod delivers in time
    return {"understanding": understanding}


def search_catalog(state: AgentState) -> AgentState:
    understanding = state["understanding"]
    if understanding.intent == "add_items":
        marketplaces = [state["pod"]["marketplace"]]
    else:
        marketplaces = ["weee", "amazon_fresh"]
    candidates = [
        [product for marketplace in marketplaces for product in search_products.invoke({"query": item.query, "marketplace": marketplace})]
        for item in understanding.items
    ]
    return {"candidates": candidates}


def rank(state: AgentState) -> AgentState:
    lines = []
    for item, products in zip(state["understanding"].items, state["candidates"]):
        lines.append(f"Request: {item.qty} x {item.query} ({item.notes or 'no notes'})")
        for p in products:
            stock = {True: "in stock", False: "OUT OF STOCK", None: "stock unknown"}[p.get("inStock")]
            lines.append(f"  - id={p['id']} | {p['title']} | ${p['price']} | {stock}")
    prompt = [
        SystemMessage(HOUSE_RULES + "\nPick the best product for each request: the closest match to what was asked (flavor, size, brand), then cheaper. "
                      "If the exact item asked for is out of stock, still pick it so we can flag it. Never swap in a different flavor or product."),
        HumanMessage("\n".join(lines)),
    ]
    return {"ranking": model(state).with_structured_output(Ranking).invoke(prompt)}


def compose(state: AgentState) -> AgentState:
    understanding = state["understanding"]
    blocks = [{"type": "text", "text": understanding.reply}]
    if understanding.intent == "add_items":
        blocks += item_blocks(state)
    elif understanding.intent == "find_pod":
        blocks += pod_blocks(state)
    elif understanding.intent == "cart_status":
        blocks.append({"type": "cart_summary", "podId": state["pod_id"]})
    return {"blocks": blocks}


# ---------- deterministic block builders ----------

def in_stock_first(products: list[dict]) -> list[dict]:
    return sorted(products, key=lambda p: (p.get("inStock") is False, p["price"] or 999))


def exact_title_match(query: str, products: list[dict]) -> dict | None:
    words = query.lower().split()
    return next((p for p in products if all(word in p["title"].lower() for word in words)), None)


def item_blocks(state: AgentState) -> list[dict]:
    picks = {pick.query: pick for pick in state["ranking"].picks}
    blocks = []
    for item, products in zip(state["understanding"].items, state["candidates"]):
        request = item.model_dump()
        if not products:
            blocks.append({"type": "text", "text": f"I couldn't find {item.query} in this pod's store."})
            continue
        pick = picks.get(item.query)
        chosen = next((p for p in products if pick and p["id"] == pick.recommended_id), None)
        exact_match = exact_title_match(item.query, products)
        if exact_match and exact_match.get("inStock") is False:
            chosen = exact_match  # rule: never quietly swap an out-of-stock item for a different one
        alternatives = [p for p in in_stock_first(products) if p.get("inStock") is not False and p is not chosen][:4]
        if chosen and chosen.get("inStock") is False:
            blocks.append({"type": "out_of_stock", "request": request, "product": chosen, "alternatives": alternatives})
            continue
        blocks.append({
            "type": "product_choices",
            "request": request,
            "products": in_stock_first(products)[:4],
            "recommendedId": None if (pick is None or pick.is_ambiguous) else pick.recommended_id,
            "reason": pick.reason if pick else None,
        })
    return blocks


def pod_blocks(state: AgentState) -> list[dict]:
    """Cheapest in-stock match per marketplace, then open pods on that marketplace that deliver in time."""
    understanding = state["understanding"]
    pods = find_open_pods.invoke({"deliver_within_hours": understanding.deadline_hours})
    blocks = []
    for item, products in zip(understanding.items, state.get("candidates", [])):
        available = [p for p in products if p.get("inStock") is not False and p["price"] is not None]
        reachable = [p for p in available if any(pod["marketplace"] == p["marketplace"] for pod in pods)]
        if not reachable:
            blocks.append({"type": "text", "text": f"No open pod can get {item.query} to you in time."})
            continue
        cheapest = min(reachable, key=lambda p: p["price"])
        matching_pods = [pod["id"] for pod in pods if pod["marketplace"] == cheapest["marketplace"]]
        blocks.append({"type": "product_choices", "request": item.model_dump(), "products": [cheapest], "recommendedId": cheapest["id"], "reason": "Cheapest in-stock option"})
        blocks.append({"type": "pod_suggestions", "podIds": matching_pods, "reason": "These pods deliver in time"})
    if not understanding.items:
        blocks.append({"type": "pod_suggestions", "podIds": [pod["id"] for pod in pods], "reason": "Open pods that deliver in time"})
    return blocks


# ---------- routing ----------

def after_understand(state: AgentState) -> str:
    understanding = state["understanding"]
    needs_search = understanding.intent in ("add_items", "find_pod") and understanding.items
    return "search_catalog" if needs_search else "compose"


def after_search(state: AgentState) -> str:
    return "rank" if state["understanding"].intent == "add_items" else "compose"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("load_pod", load_pod)
    graph.add_node("understand", understand)
    graph.add_node("search_catalog", search_catalog)
    graph.add_node("rank", rank)
    graph.add_node("compose", compose)
    graph.add_edge(START, "load_pod")
    graph.add_edge("load_pod", "understand")
    graph.add_conditional_edges("understand", after_understand, ["search_catalog", "compose"])
    graph.add_conditional_edges("search_catalog", after_search, ["rank", "compose"])
    graph.add_edge("rank", "compose")
    graph.add_edge("compose", END)
    return graph.compile()


agent_graph = build_graph()


def run_agent(pod_id: str, member_id: str, message: str, history: list[dict] | None = None, tier: str = "fast", callbacks: list | None = None) -> dict:
    state = {"pod_id": pod_id, "member_id": member_id, "message": message, "history": history or [], "tier": tier}
    config = {"run_name": "huddlecart_agent", "tags": [tier, MODELS[tier]], "metadata": {"pod_id": pod_id, "tier": tier}, "callbacks": callbacks or []}
    result = agent_graph.invoke(state, config=config)
    return {"blocks": result["blocks"], "understanding": result["understanding"].model_dump()}
