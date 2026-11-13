"""LangChain tools the agent uses: pod lookup (database) and product search (retrieval)."""
import json
import os
import re
from datetime import timedelta
from pathlib import Path

from langchain_core.tools import tool
from langsmith import traceable

from . import rules, store

CATALOG = json.loads((Path(__file__).parent / "catalog.json").read_text())
DOMAINS = {"weee": "sayweee.com", "amazon_fresh": "amazon.com"}
PRODUCT_URL = {"weee": re.compile(r"/product/"), "amazon_fresh": re.compile(r"/dp/")}
PRICE = re.compile(r"\$\s?\.?\s?(\d{1,3})\s?\.\s?(\d{2})")
OUT_OF_STOCK = re.compile(r"out of stock|currently unavailable|sold out|not available", re.I)


def live_search_enabled() -> bool:
    return os.getenv("HUDDLECART_SEARCH") == "live" and bool(os.getenv("TAVILY_API_KEY"))


def search_snapshot(query: str, marketplace: str, limit: int = 6) -> list[dict]:
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 1]

    def score(product: dict) -> int:
        text = f"{product['title']} {product.get('brand', '')} {' '.join(product.get('tags', []))}".lower()
        return sum(word in text for word in words)

    matches = [p for p in CATALOG if p["marketplace"] == marketplace and score(p) > 0]
    matches.sort(key=lambda p: (-score(p), p["price"] or 999))
    return [{**p, "source": "snapshot", "checkedAt": store.iso()} for p in matches[:limit]]


def search_live(query: str, marketplace: str, limit: int = 6) -> list[dict]:
    from langchain_tavily import TavilySearch

    tavily = TavilySearch(max_results=limit + 4, include_domains=[DOMAINS[marketplace]], include_images=True)
    response = tavily.invoke({"query": f"{query} grocery"})
    products = []
    for index, result in enumerate(response.get("results", [])):
        if not PRODUCT_URL[marketplace].search(result["url"]):
            continue
        text = f"{result['title']} {result.get('content', '')}"
        price = PRICE.search(text)
        title = re.sub(r"^Amazon\.com:\s*", "", result["title"])
        title = re.sub(r"\s*[|:-]\s*(Weee!?|Grocery & Gourmet Food|Amazon\.com).*$", "", title, flags=re.I)
        title = re.sub(r"\s+:\s+\w+$", "", title)
        products.append({
            "id": f"live-{marketplace}-{index}-{abs(hash(result['url'])) % 10**8}",
            "marketplace": marketplace,
            "title": title.strip(),
            "price": float(f"{price[1]}.{price[2]}") if price else None,
            "inStock": False if OUT_OF_STOCK.search(text) else None,
            "url": result["url"],
            "source": "live",
            "checkedAt": store.iso(),
        })
    return products[:limit]


@tool
@traceable(run_type="retriever", name="search_products")
def search_products(query: str, marketplace: str) -> list[dict]:
    """Search one marketplace ("weee" or "amazon_fresh") for grocery products matching the query."""
    if live_search_enabled():
        try:
            priced = [p for p in search_live(query, marketplace) if p["price"] is not None]
            if priced:
                return priced
        except Exception as error:  # live web search is best effort; the snapshot keeps the demo working
            print(f"live search failed, using snapshot: {error}")
    return search_snapshot(query, marketplace)


@tool
def get_pod_details(pod_id: str) -> dict:
    """Look up one pod: leader, members, marketplace, cutoff, delivery time, pickup spot and cart totals."""
    data = store.db()
    pod = store.get_pod(pod_id)
    if pod is None:
        return {"error": f"No pod called {pod_id}"}
    return {
        **pod,
        "marketplaceName": rules.MARKETPLACE_NAMES[pod["marketplace"]],
        "leaderName": store.get_member(pod["leaderId"])["name"],
        "totals": rules.cart_totals(pod, data["cart"]),
    }


@tool
def find_open_pods(deliver_within_hours: float | None = None) -> list[dict]:
    """List open pods that can deliver within the given number of hours (or all open pods)."""
    deadline = store.now() + timedelta(hours=deliver_within_hours) if deliver_within_hours else None
    return rules.pods_delivering_by(store.db()["pods"], deadline)
