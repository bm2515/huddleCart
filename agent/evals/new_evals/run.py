"""Policy v0.2 eval pack: 20 golden scenarios from evals.yaml, run through huddlecart.orders.

  python -m evals.new_evals.run golden [--runs 3]       # run the 20 golden scenarios, code-checked
  python -m evals.new_evals.run hard [--runs 3]         # the 15 harder scenarios in hard.yaml, same checks
  python -m evals.new_evals.run judge-hard              # Gemma judges the 15 hard cases, failures included
  python -m evals.new_evals.run judge                   # Gemma judges 10 of them; agreement with code checks
  python -m evals.new_evals.run team-sheet NAME ...     # CSV for teammates to score each case 0 / 0.5 / 1
  python -m evals.new_evals.run team                    # read the filled CSV, write the team table into EVALS.md

Needs GOOGLE_API_KEY (or a line GOOGLE_API_KEY=... in agent/.env) for the AI steps and the judge.
"""
import csv
import json
import os
import re
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import yaml

HERE = Path(__file__).parent
RESULTS = HERE / "results"
ENV_FILE = HERE.parent.parent / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"'))

SPEC = yaml.safe_load((HERE / "evals.yaml").read_text())
SCENARIOS = {s["id"]: s for s in SPEC["scenarios"]}
HARD_SPEC = yaml.safe_load((HERE / "hard.yaml").read_text())  # harder inputs, to find where the AI breaks
HARD = {s["id"]: s for s in HARD_SPEC["scenarios"]}
POLICY = (HERE / "policy.md").read_text()

# All 13 critical scenarios + 7 major ones that lean on the AI (matching, asking, holding, wording).
GOLDEN = [
    "avail-sub-allergen-002", "avail-sub-halal-015", "combine-same-sku-011", "money-big-order-005",
    "money-rounding-022", "money-dropped-household-023", "privacy-views-024", "safety-injection-025",
    "understand-dietary-match-027", "money-payment-fails-031", "money-store-minimum-032",
    "safety-age-restricted-033", "timing-order-once-036",
    "avail-sub-001", "avail-partial-003", "qty-outlier-004", "understand-ask-006",
    "understand-messy-text-009", "understand-multi-item-010", "avail-not-carried-026",
]
# Ten golden cases where the AI reads text or writes a message the household sees.
JUDGED = [
    "avail-sub-001", "avail-sub-allergen-002", "avail-partial-003", "qty-outlier-004", "understand-ask-006",
    "understand-messy-text-009", "avail-sub-halal-015", "safety-injection-025", "avail-not-carried-026",
    "understand-dietary-match-027",
]
JUDGE_MODEL = os.getenv("HUDDLECART_JUDGE_MODEL", "gemma-4-31b-it")
JUDGE_TIMEOUT = 120  # seconds per judge call


# ---------- code checks ----------

def as_counter(items: list[dict]) -> Counter:
    c = Counter()
    for i in items or []:
        c[i["sku"]] += i["qty"]
    return c


def note_matches(note: dict, want: dict) -> bool:
    if note["to"] != want["to"]:
        return False
    if "outcome" in want and note["outcome"] != want["outcome"]:
        return False
    if "about" in want:
        about = str(want["about"]).lower()
        return about in (str(note["about"]).lower(), str(note["about_text"]).lower()) or about in str(note["about_text"]).lower()
    return True


def check_invariant(expr: str, out: dict) -> bool:
    charges = out["charges"]
    cents = lambda x: round(x * 100)  # noqa: E731
    if m := re.fullmatch(r"total_qty\(([\w-]+)\) == (\d+)", expr):
        return as_counter(out["store_order"])[m.group(1)] == int(m.group(2))
    if expr == "sum(charges.total) == order.total":
        return sum(cents(c["total"]) for c in charges.values()) == cents(out["order_total"])
    if m := re.fullmatch(r"sum\(charges\.delivery\) == ([\d.]+)", expr):
        return sum(cents(c["delivery"]) for c in charges.values()) == cents(float(m.group(1)))
    if expr == "all(charge.total >= 0)":
        return all(c["total"] >= 0 for c in charges.values())
    if m := re.fullmatch(r"charges\.(\w+)\.total == ([\d.]+)", expr):
        return cents(charges[m.group(1)]["total"]) == cents(float(m.group(2)))
    if m := re.fullmatch(r'payment_status == "(\w+)"', expr):
        return out["payment_status"] == m.group(1)
    raise ValueError(f"unsupported invariant: {expr}")


def score(expected: dict, out: dict) -> dict:
    checks: dict[str, bool] = {}
    for hid, items in expected.get("line_items", {}).items():
        checks[f"line_items.{hid}"] = as_counter(out["line_items"].get(hid, [])) == as_counter(items)
    for hid, skus in expected.get("must_not_include", {}).items():
        checks[f"must_not_include.{hid}"] = not set(skus) & set(as_counter(out["line_items"].get(hid, [])))
    if "store_order" in expected:
        checks["store_order"] = as_counter(out["store_order"]) == as_counter(expected["store_order"])
    if "store_order_must_not_contain" in expected:
        checks["store_order_must_not_contain"] = not set(expected["store_order_must_not_contain"]) & set(as_counter(out["store_order"]))
    if "store_order_excludes_households" in expected:
        checks["store_order_excludes_households"] = all(not out["line_items"].get(h) for h in expected["store_order_excludes_households"])
    if "order_placed" in expected:
        checks["order_placed"] = out["order_placed"] == expected["order_placed"]
    for i, want in enumerate(expected.get("notifications", [])):
        checks[f"notification.{want['to']}.{want['outcome']}"] = any(note_matches(n, want) for n in out["notifications"])
    if "no_notifications_to" in expected:
        checks["no_notifications_to"] = not any(n["to"] in expected["no_notifications_to"] for n in out["notifications"])
    for want in expected.get("final_notifications_exclude", []):
        checks[f"no_notification.{want['to']}.{want['outcome']}"] = not any(note_matches(n, want) for n in out["notifications"])
    for kind in ("clarification_requests", "confirmation_requests"):
        if kind not in expected:
            continue
        if not expected[kind]:
            checks[f"{kind}.none"] = not out[kind]
        for want in expected[kind]:
            def ok(q, want=want):
                if q["to"] != want["to"]:
                    return False
                about = str(want["about"]).lower()
                if about not in (str(q["about"]).lower(), str(q.get("about_text", "")).lower()) and about not in str(q.get("about_text", "")).lower():
                    return False
                if "qty" in want and q.get("qty") != want["qty"]:
                    return False
                if "reason" in want and q.get("reason") != want["reason"]:
                    return False
                return set(want.get("options_include", [])) <= {o["sku"] for o in q.get("options", [])}
            checks[f"{kind}.{want['to']}"] = any(ok(q) for q in out[kind])
    for hid, want in expected.get("charges", {}).items():
        got = out["charges"].get(hid, {})
        checks[f"charges.{hid}"] = all(round(got.get(k, -1) * 100) == round(v * 100) for k, v in want.items())
    for hid, want in expected.get("subtotals", {}).items():
        checks[f"subtotal.{hid}"] = round(out["subtotals"].get(hid, -1) * 100) == round(want * 100)
    for expr in expected.get("invariants", []):
        checks[f"invariant: {expr}"] = check_invariant(expr, out)
    for view, want in expected.get("views", {}).items():
        got = out["views"].get(view, {})
        skus = set(as_counter(got.get("items", [])))
        ok = set(want.get("contains_skus", [])) <= skus and not set(want.get("must_not_contain_skus", [])) & skus
        if "contains_household_ids" in want:
            ok = ok and got.get("household_ids", []) == want["contains_household_ids"]
        checks[f"view.{view}"] = ok
    if "external_orders" in expected:
        checks["external_orders"] = out["external_orders"] == expected["external_orders"]
    for hid, items in expected.get("next_order", {}).items():
        checks[f"next_order.{hid}"] = as_counter(out["next_order"].get(hid, [])) == as_counter(items)
    if "store_orders_count" in expected:
        checks["store_orders_count"] = out["store_orders_count"] == expected["store_orders_count"]
    for hid, n in expected.get("charge_attempts", {}).items():
        checks[f"charge_attempts.{hid}"] = out["charge_attempts"].get(hid, 0) == n
    return {"checks": checks, "score": round(sum(checks.values()) / len(checks), 2), "passed": all(checks.values())}


# ---------- running ----------

def run_one(scenario: dict, brain, defaults: dict | None = None) -> dict:
    from huddlecart.orders import run_scenario
    started = time.perf_counter()
    try:
        out, error = run_scenario(scenario["setup"], defaults or SPEC["defaults"], brain), None
    except Exception as exc:  # a provider error or crash is a failed run, not a crashed eval
        out, error = None, f"{type(exc).__name__}: {exc}"[:300]
    seconds = round(time.perf_counter() - started, 2)
    graded = score(scenario["expected"], out) if out else {"checks": {}, "score": 0.0, "passed": False}
    return {"seconds": seconds, "error": error, "output": out, **graded}


def run_cases(name: str, scenarios: dict, defaults: dict) -> None:
    from huddlecart.order_ai import LLMBrain
    runs = int(sys.argv[sys.argv.index("--runs") + 1]) if "--runs" in sys.argv else 3
    brain = LLMBrain()
    rows = []
    for sid, s in scenarios.items():
        attempts = [run_one(s, brain, defaults) for _ in range(runs)]
        passes = sum(a["passed"] for a in attempts)
        rows.append({"id": sid, "title": s["title"], "severity": s["severity"], "policy": s["policy"],
                     "model": brain.model_name, "runs": attempts, "passes": passes,
                     "score": round(statistics.mean(a["score"] for a in attempts), 2)})
        bar = "PASS" if passes == runs else ("FAIL" if s["severity"] == "critical" or passes == 0 else "FLAKY")
        print(f"{bar:5} {passes}/{runs}  {s['severity']:8} {sid}")
        for a in attempts:
            failed = [k for k, v in a["checks"].items() if not v]
            if failed or a["error"]:
                print(f"        {a['error'] or ', '.join(failed)}")
    save(name, rows)
    crit = [r for r in rows if r["severity"] == "critical"]
    print(f"\nall runs passed: {sum(r['passes'] == runs for r in rows)}/{len(rows)} cases; "
          f"critical {sum(r['passes'] == runs for r in crit)}/{len(crit)}; mean score {statistics.mean(r['score'] for r in rows):.2f}")


def golden() -> None:
    run_cases("golden", {sid: SCENARIOS[sid] for sid in GOLDEN}, SPEC["defaults"])


def hard() -> None:
    run_cases("hard", HARD, HARD_SPEC["defaults"])


# ---------- cross-model judge ----------

def rules_text(ids: list[str]) -> str:
    return "\n".join(line.strip() for line in POLICY.splitlines() if any(line.strip().startswith(f"- **{i}**") for i in ids))


def summary(out: dict | None) -> str:
    if not out:
        return "(the run crashed, no output)"
    parts = [f"Line items per household: {json.dumps(out['line_items'])}",
             f"Store order: {json.dumps(out['store_order'])}; order placed: {out['order_placed']}"]
    if out["charges"]:
        parts.append(f"Charges: {json.dumps(out['charges'])}")
    for kind in ("clarification_requests", "confirmation_requests", "notifications"):
        for q in out[kind]:
            label = q.get("outcome") or q.get("reason") or "question"
            parts.append(f"{kind[:-1]} to {q['to']} about {q['about']} ({label}): \"{q['text']}\"")
    return "\n".join(parts)


def judge_model():
    """A call with no answer would otherwise wait forever; time out after 2 minutes and let judge() retry."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(model=JUDGE_MODEL, temperature=0, timeout=JUDGE_TIMEOUT, max_retries=0)


def judge(row: dict, scenario: dict | None = None, run: int = 0) -> dict:
    from langchain_core.messages import HumanMessage
    s = scenario or SCENARIOS[row["id"]]
    rubrics = {name: r for name, r in SPEC["rubrics"].items()}
    prompt = f"""You grade a grocery ordering system that combines a building's orders. Code made the decisions; an AI
wrote the messages. Grade two things separately.

DECISIONS: PASS if what got ordered, dropped, held, substituted, charged and who got notified matches the expected
result and the policy rules. FAIL otherwise.
MESSAGES: PASS if every message the households see meets the rubric below, FAIL if any misses a point, N/A if there are none.

Policy rules this scenario tests:
{rules_text(s['policy'])}

Scenario: {s['title']}
Setup: {json.dumps(s['setup'], default=str)}
Expected: {json.dumps(s['expected'], default=str)}

Message rubrics: {json.dumps(rubrics)}

What the system did:
{summary(row['runs'][run]['output'])}

Answer in exactly three lines:
DECISIONS: PASS or FAIL
MESSAGES: PASS, FAIL or N/A
REASON: one short sentence"""
    for attempt in range(4):  # a provider error (500, rate limit) is retried, not counted as a verdict
        try:
            answer = judge_model().invoke([HumanMessage(prompt)]).text.strip()
            break
        except Exception:
            if attempt == 3:
                raise
            time.sleep(5 * 2 ** attempt)
    found = {k: (m.group(1).upper() if (m := re.search(rf"{k}:\s*\**\s*(PASS|FAIL|N/A)", answer, re.I)) else "?")
             for k in ("DECISIONS", "MESSAGES")}
    reason = m.group(1).strip() if (m := re.search(r"REASON:\s*(.+)", answer, re.I)) else answer.splitlines()[-1]
    return {"decisions": found["DECISIONS"], "messages": found["MESSAGES"], "reason": reason[:240], "raw": answer}


def judge_ten() -> None:
    rows = {r["id"]: r for r in load("golden")}
    out = []
    for sid in JUDGED:
        row = rows[sid]
        verdict = judge(row)
        code_pass = row["runs"][0]["passed"]
        out.append({"id": sid, "code_passed": code_pass, "judge_decisions_passed": verdict["decisions"] == "PASS",
                    "judge_messages": verdict["messages"], "reason": verdict["reason"], "raw": verdict["raw"]})
        print(f"{sid:32} code={'pass' if code_pass else 'fail'} judge={verdict['decisions'].lower()} "
              f"messages={verdict['messages'].lower()}  {verdict['reason']}")
    agree = sum(r["code_passed"] == r["judge_decisions_passed"] for r in out)
    save("judge", out)
    print(f"\njudge {JUDGE_MODEL} agrees with code checks on {agree}/{len(out)} = {agree / len(out):.0%}")


def pick_run(row: dict) -> int:
    """The first failing run if any run failed, else run 1: so the judge and the team see the failures."""
    return next((i for i, a in enumerate(row["runs"]) if not a["passed"]), 0)


def judge_hard() -> None:
    """Every case in the golden set passed, so the 10/10 agreement only shows the judge lets good runs through.
    The hard set has failures, so here agreement also shows whether the judge catches bad ones."""
    out = load("judge_hard") if (RESULTS / "judge_hard.json").exists() and "--fresh" not in sys.argv else []
    done = {r["id"] for r in out}  # resume: cases already judged are kept, so a crash or hang loses nothing
    for row in load("hard"):
        if row["id"] in done:
            continue
        run = pick_run(row)
        verdict = judge(row, HARD[row["id"]], run)
        code_pass = row["runs"][run]["passed"]
        out.append({"id": row["id"], "run": run + 1, "code_passed": code_pass, "judge_decisions_passed": verdict["decisions"] == "PASS",
                    "judge_messages": verdict["messages"], "reason": verdict["reason"], "raw": verdict["raw"]})
        save("judge_hard", out)
        print(f"{row['id']:32} run {run + 1} code={'pass' if code_pass else 'fail'} judge={verdict['decisions'].lower()} "
              f"messages={verdict['messages'].lower()}  {verdict['reason']}", flush=True)
    agree = sum(r["code_passed"] == r["judge_decisions_passed"] for r in out)
    fails = [r for r in out if not r["code_passed"]]
    passes = [r for r in out if r["code_passed"]]
    print(f"\njudge {JUDGE_MODEL} agrees with code checks on {agree}/{len(out)} = {agree / len(out):.0%}; "
          f"caught {sum(not r['judge_decisions_passed'] for r in fails)}/{len(fails)} failures, "
          f"passed {sum(r['judge_decisions_passed'] for r in passes)}/{len(passes)} correct runs")


# ---------- team scores ----------

SHEET = RESULTS / "team_scores.csv"
SHEET_FIXED = ["case", "title", "severity", "expected", "what_happened", "code_score"]


def team_sheet() -> None:
    names = [a for a in sys.argv[2:] if a != "--force"] or ["rater_1", "rater_2", "rater_3"]
    if SHEET.exists() and "--force" not in sys.argv:
        sys.exit(f"{SHEET} already exists. Pass --force to overwrite it (this erases any scores in it).")
    rows = {r["id"]: r for r in load("golden")}
    with SHEET.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(SHEET_FIXED + names)
        for sid in GOLDEN:
            s, row = SCENARIOS[sid], rows[sid]
            expected = yaml.safe_dump({k: v for k, v in s["expected"].items() if k != "judge"}, sort_keys=False, width=200).strip()
            w.writerow([sid, s["title"], s["severity"], expected, summary(row["runs"][0]["output"]), row["runs"][0]["score"]] + [""] * len(names))
        for row in load("hard") if (RESULTS / "hard.json").exists() else []:  # hard set: the run the judge saw
            s, run = HARD[row["id"]], pick_run(row)
            expected = yaml.safe_dump({k: v for k, v in s["expected"].items() if k != "judge"}, sort_keys=False, width=200).strip()
            shown = f"(hard set, run {run + 1} of {len(row['runs'])})\n{summary(row['runs'][run]['output'])}"
            w.writerow([row["id"], s["title"], s["severity"], expected, shown, row["runs"][run]["score"]] + [""] * len(names))
    print(f"wrote {SHEET} with columns for {names}")


def team() -> None:
    from evals.run_evals import TEAM_PASS_AT, summarize_team
    with SHEET.open() as f:
        reader = csv.DictReader(f)
        raters = [c for c in reader.fieldnames if c not in SHEET_FIXED]
        rows = [{**r, "rule_score": r["code_score"]} for r in reader]
    judged = {r["id"]: r["judge_decisions_passed"] for r in load("judge")} if (RESULTS / "judge.json").exists() else {}
    s = summarize_team([{**r, "case": r["case"]} for r in rows], raters, judged)
    table = ["| Case | Severity | Code score | Team (" + " / ".join(raters) + ") | Team mean |", "|---|---|---|---|---|"]
    for r in rows:
        c = s["per_case"][r["case"]]
        table.append(f"| {r['case']} | {r['severity']} | {r['code_score']} | {' / '.join(f'{x:g}' for x in c['scores'])} | {c['mean']:g} |")
    line = (f"Team: **{s['team_passed']}/{s['cases']} passed, mean {s['team_mean']:.2f}** ({len(raters)} raters; a case passes "
            f"when the team mean is at least {TEAM_PASS_AT}). Raters unanimous on {s['unanimous']}/{s['cases']}. "
            f"Team agrees with code checks on {s['team_vs_rules']}/{s['cases']} and with the judge on {s['team_vs_judge']}/{s['judged']}.")
    block = "\n".join(table) + "\n\n" + line
    doc = HERE / "EVALS.md"
    start, end = "<!-- team-table:start -->", "<!-- team-table:end -->"
    head, rest = doc.read_text().split(start)
    _, tail = rest.split(end)
    doc.write_text(f"{head}{start}\n{block}\n{end}{tail}")
    print(block)


def save(name: str, data) -> None:
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{name}.json").write_text(json.dumps(data, indent=1, default=str))


def load(name: str):
    return json.loads((RESULTS / f"{name}.json").read_text())


if __name__ == "__main__":
    {"golden": golden, "hard": hard, "judge": judge_ten, "judge-hard": judge_hard, "team-sheet": team_sheet, "team": team}[sys.argv[1]]()
