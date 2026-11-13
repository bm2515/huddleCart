"""Tiny JSON-file database: members, pods, cart lines, chat messages, pickups."""
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(os.getenv("HUDDLECART_DB", Path(__file__).parent.parent / ".data" / "db.json"))
DATABASE_URL = os.getenv("DATABASE_URL")
_db: dict | None = None

if DATABASE_URL:
    import psycopg
    from psycopg.types.json import Jsonb


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(hours_from_now: float = 0) -> str:
    return (now() + timedelta(hours=hours_from_now)).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex[:10]


def _pod(pod_id, name, leader, members, marketplace, minimum, cutoff_h, eta_h, pickup, building, interest=None):
    return {
        "id": pod_id, "name": name, "building": building, "interest": interest,
        "leaderId": leader, "memberIds": members, "marketplace": marketplace,
        "minimumForFreeShipping": minimum, "feePerPerson": 2,
        "cutoff": iso(cutoff_h), "deliveryEta": iso(eta_h), "pickupSpot": pickup, "status": "open",
    }


def seed() -> dict:
    members = [
        {"id": "bisma", "name": "Bisma", "venmo": "bisma-m", "zelle": "bisma@example.com"},
        {"id": "dua", "name": "Dua"},
        {"id": "uj", "name": "Umar"},
        {"id": "jason", "name": "Jason"},
        {"id": "mei", "name": "Mei"},
    ]
    everyone = [m["id"] for m in members]
    pods = [
        _pod("the-house", "The House weekly", "bisma", everyone, "weee", 49, 20, 40, "The House reception", "The House, Roosevelt Island"),
        _pod("asian-snacks", "Asian snack lovers", "mei", ["mei", "jason", "bisma"], "weee", 49, 4, 22, "The House reception", "The House, Roosevelt Island", "Asian snacks"),
        _pod("fresh-basics", "Fresh basics", "uj", ["uj", "dua", "bisma"], "amazon_fresh", 35, 6, 18, "Tata front desk", "Tata Innovation Center"),
    ]
    from .events import seed_events

    events = seed_events({p["id"]: p for p in pods})
    return {"members": members, "pods": pods, "cart": [], "messages": [], "pickups": {}, "history": seed_history(), "events": events, "checkouts": []}


def seed_history() -> list[dict]:
    """Four past weeks of orders so levels, streaks and badges have something to show."""
    past_orders = [  # week, pod, leader, buyer, item, category, qty
        (1, "the-house", "bisma", "jason", "Buldak Ramen", "ramen", 5), (1, "the-house", "bisma", "mei", "Pocky", "snack", 3),
        (1, "the-house", "bisma", "dua", "Shrimp Chips", "snack", 2), (1, "fresh-basics", "uj", "uj", "Bananas", "fresh", 2),
        (2, "the-house", "bisma", "jason", "Shin Ramyun", "ramen", 4), (2, "the-house", "bisma", "bisma", "Kimchi", "pantry", 1),
        (2, "asian-snacks", "mei", "mei", "Mango Mochi", "snack", 2), (2, "asian-snacks", "mei", "dua", "Hello Panda", "snack", 3),
        (3, "the-house", "bisma", "jason", "Buldak Ramen", "ramen", 6), (3, "the-house", "bisma", "dua", "Tofu", "fresh", 2),
        (3, "fresh-basics", "uj", "uj", "Spinach", "fresh", 3), (3, "fresh-basics", "uj", "bisma", "Greek Yogurt", "dairy", 2),
        (4, "the-house", "bisma", "jason", "Indomie", "ramen", 6), (4, "the-house", "bisma", "jason", "Seaweed", "snack", 2),
        (4, "asian-snacks", "mei", "mei", "Pocky", "snack", 4), (4, "the-house", "bisma", "dua", "Bok Choy", "fresh", 2),
        (4, "the-house", "bisma", "bisma", "Jasmine Rice", "pantry", 1), (4, "fresh-basics", "uj", "uj", "Eggs", "fresh", 1),
    ]
    return [
        {"week": week, "podId": pod, "leaderId": leader, "memberId": buyer, "title": item, "category": category, "qty": qty}
        for week, pod, leader, buyer, item, category, qty in past_orders
    ]


def db() -> dict:
    global _db
    if _db is None:
        _db = _load()
        if _db is None:
            _db = seed()
            save()
        _db.setdefault("events", [])
        _db.setdefault("checkouts", [])
    return _db


def forget() -> None:
    """Drop the in-memory copy so the next db() call reads fresh data (one call per request)."""
    global _db
    _db = None


def _load() -> dict | None:
    if DATABASE_URL:
        with _postgres() as conn:
            row = conn.execute("SELECT data FROM huddlecart_state WHERE id = 1").fetchone()
        return row[0] if row else None
    return json.loads(DB_PATH.read_text()) if DB_PATH.exists() else None


def save() -> None:
    if DATABASE_URL:
        with _postgres() as conn:
            conn.execute(
                "INSERT INTO huddlecart_state (id, data) VALUES (1, %s) "
                "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
                [Jsonb(_db)],
            )
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = DB_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(_db, indent=1))
    temp_path.replace(DB_PATH)


def _postgres():
    """Hosted Postgres (Neon on Vercel). The whole app state is one JSON row."""
    conn = psycopg.connect(DATABASE_URL, autocommit=True)
    conn.execute("CREATE TABLE IF NOT EXISTS huddlecart_state (id int PRIMARY KEY, data jsonb NOT NULL)")
    return conn


def reset() -> None:
    global _db
    _db = seed()
    save()


def get_pod(pod_id: str) -> dict | None:
    return next((p for p in db()["pods"] if p["id"] == pod_id), None)


def get_member(member_id: str) -> dict | None:
    return next((m for m in db()["members"] if m["id"] == member_id), None)
