"""Eval pack + unit economics for the HuddleCart agent.

  python -m evals.run_evals golden            # 20 golden cases on the fast tier, rule-based scores
  python -m evals.run_evals judge             # Gemma judge on the first 10, agreement with rule scores
  python -m evals.run_evals economics         # same 10 cases on fast and strong tiers

Search runs on the catalog snapshot so expected answers stay stable.
"""
import json
import os
import statistics
import sys
import time
from pathlib import Path

os.environ["HUDDLECART_SEARCH"] = "snapshot"
os.environ["HUDDLECART_DB"] = str(Path(__file__).parent / ".eval_db.json")

from langchain_core.callbacks import UsageMetadataCallbackHandler  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402

from huddlecart import store  # noqa: E402
from huddlecart.agent import MODELS, chat_model, run_agent  # noqa: E402

HERE = Path(__file__).parent
CASES = json.loads((HERE / "golden_cases.json").read_text())
RESULTS = HERE / "results"
# Judge is Gemma, an open model family separate from the Gemini agent tiers.
JUDGE_MODEL = os.getenv("HUDDLECART_JUDGE_MODEL", "gemma-4-31b-it")
# Paid-tier list price, USD per 1M tokens (input, output). Check https://ai.google.dev/pricing before reporting.
PRICES = json.loads(os.getenv("HUDDLECART_PRICES", '{"gemini-3.5-flash-lite": [0.30, 2.50], "gemini-3-flash-preview": [0.50, 3.00]}'))


# ---------- running ----------

def run_case(case: dict, tier: str) -> dict:
    store.reset()
    usage = UsageMetadataCallbackHandler()
    started = time.perf_counter()
    try:
        output = run_agent(case["pod_id"], case["member_id"], case["message"], tier=tier, callbacks=[usage])
        error = None
    except Exception as exc:
        output, error = {"blocks": [], "understanding": {}}, str(exc)
    seconds = round(time.perf_counter() - started, 2)
    tokens_in = sum(u.get("input_tokens", 0) for u in usage.usage_metadata.values())
    tokens_out = sum(u.get("output_tokens", 0) for u in usage.usage_metadata.values())
    price_in, price_out = PRICES.get(MODELS[tier], [0, 0])
    cost = (tokens_in * price_in + tokens_out * price_out) / 1_000_000
    return {"case": case["id"], "tier": tier, "model": MODELS[tier], "seconds": seconds, "tokens_in": tokens_in,
            "tokens_out": tokens_out, "cost_usd": cost, "error": error, **output}


# ---------- rule-based scoring ----------

def score_item(expected: dict, blocks: list[dict]) -> bool:
    if "out_of_stock" in expected:
        return any(b["type"] == "out_of_stock" and b.get("product", {}).get("id") == expected["out_of_stock"] for b in blocks)
    if expected.get("no_pod"):
        return not any(b["type"] == "pod_suggestions" and b["podIds"] for b in blocks)
    for block in (b for b in blocks if b["type"] == "product_choices"):
        shown = [p["id"] for p in block["products"]]
        if block.get("recommendedId") in expected["accept_ids"]:
            return True
        if block.get("recommendedId") is None and set(shown) & set(expected["accept_ids"]):
            return True
    return False


def score_case(case: dict, run: dict) -> dict:
    expected, blocks = case["expected"], run["blocks"]
    checks = {"intent": run["understanding"].get("intent") == expected["intent"]}
    for index, item in enumerate(expected["items"]):
        checks[f"item_{index + 1}"] = score_item(item, blocks)
    if "pods" in expected:
        suggested = {pod for b in blocks if b["type"] == "pod_suggestions" for pod in b["podIds"]}
        checks["pods"] = suggested == set(expected["pods"])
    return {"checks": checks, "score": round(sum(checks.values()) / len(checks), 2), "passed": all(checks.values())}


# ---------- cross-model judge ----------

def describe(blocks: list[dict]) -> str:
    lines = []
    for b in blocks:
        if b["type"] == "text":
            lines.append(f"Says: {b['text']}")
        elif b["type"] == "product_choices":
            shown = ", ".join(f"{p['title']} ${p['price']}" for p in b["products"])
            lines.append(f"Shows options for '{b['request']['query']}' x{b['request']['qty']}: {shown}. Recommends {b.get('recommendedId')}")
        elif b["type"] == "out_of_stock":
            lines.append(f"Flags out of stock: {b['product']['title']}. Alternatives: {', '.join(p['title'] for p in b['alternatives'])}")
        elif b["type"] == "pod_suggestions":
            lines.append(f"Suggests pods: {b['podIds']}")
        else:
            lines.append(f"Shows {b['type']}")
    return "\n".join(lines) or "(no output)"


def judge(case: dict, run: dict) -> tuple[bool, str]:
    """Plain-text verdict so any model can judge: first line PASS or FAIL, then one reason."""
    instructions = ("You grade a grocery ordering agent. PASS only if it understood the request, showed or recommended "
                    "an acceptable product, flagged out-of-stock items, and followed house rules (no alcohol, no invented prices). "
                    "Answer with PASS or FAIL on the first line, then one short reason.")
    question = (f"Neighbor said: {case['message']}\nExpected: {json.dumps(case['expected'])}\n"
                f"What this tests: {case['tests']}\n\nAgent output:\n{describe(run['blocks'])}")
    answer = chat_model(JUDGE_MODEL).invoke([HumanMessage(f"{instructions}\n\n{question}")]).text
    return answer.strip().upper().startswith("PASS"), answer.strip().split("\n")[-1][:200]


# ---------- commands ----------

def golden() -> None:
    rows = []
    for case in CASES:
        run = run_case(case, "fast")
        rows.append({**run, **score_case(case, run), "message": case["message"], "tests": case["tests"]})
        print(f"{case['id']} {'PASS' if rows[-1]['passed'] else 'FAIL'} {rows[-1]['score']}  {case['message']}")
    save("golden", rows)
    print(f"\npassed {sum(r['passed'] for r in rows)}/{len(rows)}, mean score {statistics.mean(r['score'] for r in rows):.2f}")


def judge_ten() -> None:
    rows = json.loads((RESULTS / "golden.json").read_text())[:10]
    for row in rows:
        passed, reason = judge(next(c for c in CASES if c["id"] == row["case"]), row)
        row["judge_passed"], row["judge_reason"] = passed, reason
        print(f"{row['case']} rules={row['passed']} judge={passed}  {reason}")
    agreement = sum(r["judge_passed"] == r["passed"] for r in rows) / len(rows)
    save("judge", rows)
    print(f"\njudge {JUDGE_MODEL} agrees with rule scores on {agreement:.0%} of 10 cases")


def economics() -> None:
    summary = {}
    for tier in ("fast", "strong"):
        runs = [{**(run := run_case(case, tier)), **score_case(case, run)} for case in CASES[:10]]
        seconds = sorted(r["seconds"] for r in runs)
        summary[tier] = {
            "model": MODELS[tier],
            "quality_mean_score": round(statistics.mean(r["score"] for r in runs), 2),
            "passed": f"{sum(r['passed'] for r in runs)}/10",
            "latency_median_s": statistics.median(seconds),
            "latency_p90_s": seconds[8],
            "cost_per_100_runs_usd": round(100 * statistics.mean(r["cost_usd"] for r in runs), 3),
            "avg_tokens_in": round(statistics.mean(r["tokens_in"] for r in runs)),
            "avg_tokens_out": round(statistics.mean(r["tokens_out"] for r in runs)),
        }
        save(f"economics_{tier}", runs)
    save("economics_summary", summary)
    print(json.dumps(summary, indent=1))


def save(name: str, data) -> None:
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{name}.json").write_text(json.dumps(data, indent=1))


if __name__ == "__main__":
    {"golden": golden, "judge": judge_ten, "economics": economics}[sys.argv[1]]()
