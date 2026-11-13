"""Run the ordering policy engine on a LangSmith dataset (default `huddlecart-policy-golden`, override with HUDDLECART_POLICY_DATASET) and record an experiment.

  python -m evals.run_policy_evals            # deterministic checks + Gemma judge on the 6 wording rubrics
  python -m evals.run_policy_evals --no-judge  # deterministic only: no model calls, free to re-run

Critical scenarios gate the run (every one must pass). Major scenarios report a pass rate.
"""
import os
import re
import sys

from langchain_google_genai import ChatGoogleGenerativeAI
from langsmith import Client, evaluate

from huddlecart.policy import run_policy

DATASET = os.getenv("HUDDLECART_POLICY_DATASET", "huddlecart-policy-golden")
JUDGE_MODEL = os.getenv("HUDDLECART_JUDGE_MODEL", "gemma-4-31b-it")
USE_JUDGE = "--no-judge" not in sys.argv


def target(inputs: dict) -> dict:
    return run_policy(inputs["setup"])


def lines(items: list[dict]) -> list[tuple]:
    return sorted((line["sku"], line["qty"]) for line in items)


def matches(expected: dict, got: dict) -> bool:
    return all(got.get(key) == value for key, value in expected.items() if key != "options_include") and \
        set(expected.get("options_include", [])) <= set(got.get("options_include", []))


def check_invariant(rule: str, out: dict) -> bool:
    charges = out.get("charges", {}).values()
    if m := re.fullmatch(r"total_qty\((.+)\) == (\d+)", rule):
        return sum(l["qty"] for ls in out["line_items"].values() for l in ls if l["sku"] == m[1]) == int(m[2])
    if rule == "sum(charges.total) == order.total":
        return round(sum(c["total"] for c in charges), 2) == out.get("order_total", round(sum(c["total"] for c in charges), 2))
    if m := re.fullmatch(r"sum\(charges\.delivery\) == ([\d.]+)", rule):
        return round(sum(c["delivery"] for c in charges), 2) == float(m[1])
    if m := re.fullmatch(r"charges\.(\w+)\.total == 0", rule):
        return out["charges"][m[1]]["total"] == 0
    if rule == "all(charge.total >= 0)":
        return all(c["total"] >= 0 for c in charges)
    if m := re.fullmatch(r'payment_status == "(\w+)"', rule):
        return out.get("payment_status") == m[1]
    raise ValueError(f"unknown invariant: {rule}")


CHECKED_FIELDS = {"line_items", "must_not_include", "store_order", "store_order_must_not_contain", "store_order_excludes_households",
                  "charges", "subtotals", "order_placed", "next_order", "external_orders", "charge_attempts", "store_orders_count",
                  "notifications", "confirmation_requests", "clarification_requests", "no_notifications_to",
                  "final_notifications_exclude", "invariants", "views"}
NOT_GRADED = {"notes", "expected_raw", "judge", "rubrics"}


def failed_checks(expected: dict, out: dict) -> list[str]:
    """Every deterministic field in the expected output, checked exactly. Returns the names of the checks that failed."""
    failures = []
    for hid, items in expected.get("line_items", {}).items():
        if lines(items) != lines(out["line_items"].get(hid, [])):
            failures.append(f"line_items.{hid}")
    for hid, skus in expected.get("must_not_include", {}).items():
        if {l["sku"] for l in out["line_items"].get(hid, [])} & set(skus):
            failures.append(f"must_not_include.{hid}")
    if "store_order" in expected and lines(expected["store_order"]) != lines(out["store_order"]):
        failures.append("store_order")
    if set(expected.get("store_order_must_not_contain", [])) & {l["sku"] for l in out["store_order"]}:
        failures.append("store_order_must_not_contain")
    if set(expected.get("store_order_excludes_households", [])) & set(out.get("store_order_households", [])):
        failures.append("store_order_excludes_households")
    if "charges" in expected:  # each listed household matches on the fields given; anyone not listed pays nothing
        charges = out.get("charges", {})
        listed_ok = all({k: charges.get(hid, {}).get(k) for k in want} == want if isinstance(want, dict) else charges.get(hid, {}).get("total") == want
                        for hid, want in expected["charges"].items())
        if not listed_ok or any(c["total"] for hid, c in charges.items() if hid not in expected["charges"]):
            failures.append("charges")
    for key in ("subtotals", "order_placed", "next_order", "external_orders", "charge_attempts", "store_orders_count"):
        if key in expected:
            got = out.get(key)
            if key == "subtotals":
                got = {hid: out["subtotals"].get(hid) for hid in expected[key]}
            if key == "next_order":
                got = {hid: lines(v) for hid, v in out["next_order"].items()}
                if got != {hid: lines(v) for hid, v in expected[key].items()}:
                    failures.append(key)
                continue
            if got != expected[key]:
                failures.append(key)
    for key in ("notifications", "confirmation_requests", "clarification_requests"):
        if key in expected:
            if expected[key] == [] and out[key]:
                failures.append(f"{key}.none_expected")
            for wanted in expected[key]:
                if not any(matches(wanted, got) for got in out[key]):
                    failures.append(f"{key}.{wanted['to']}")
    if {n["to"] for n in out["notifications"]} & set(expected.get("no_notifications_to", [])):
        failures.append("no_notifications_to")
    for unwanted in expected.get("final_notifications_exclude", []):
        if any(matches(unwanted, got) for got in out["notifications"]):
            failures.append("final_notifications_exclude")
    for rule in expected.get("invariants", []):
        if not check_invariant(rule, out):
            failures.append(f"invariant: {rule}")
    for view, want in expected.get("views", {}).items():
        got = out["views"].get(view, {})
        if not set(want.get("contains_skus", [])) <= set(got.get("skus", [])) or set(want.get("must_not_contain_skus", [])) & set(got.get("skus", [])) \
                or want.get("contains_household_ids") != got.get("household_ids", want.get("contains_household_ids")):
            failures.append(f"views.{view}")
    for key in set(expected) - CHECKED_FIELDS - NOT_GRADED:  # fields added in newer datasets must match exactly, never pass silently
        if out.get(key) != expected[key]:
            failures.append(f"{key} (exact match)")
    return failures


def policy_checks(run, example) -> dict:
    failures = failed_checks(example.outputs, run.outputs)
    return {"key": "policy_exact", "score": int(not failures), "comment": "; ".join(failures) or "all checks pass"}


def wording_judge(run, example) -> dict:
    """Gemma grades notification / clarification / confirmation text against the dataset's rubric."""
    judged = example.outputs.get("judge", [])
    if not judged or not USE_JUDGE:
        return {"key": "wording_rubric", "score": None, "comment": "no rubric for this scenario"}
    model = ChatGoogleGenerativeAI(model=JUDGE_MODEL, temperature=0)
    verdicts = []
    for item in judged:
        text = run.outputs["messages"].get(item["target"], "(no message sent)")
        rubric = "\n".join(f"- {c}" for c in example.outputs["rubrics"][item["rubric"]]["pass_if_all"])
        reply = model.invoke(f"Grade this message a grocery app sent to a household.\nMessage: {text}\n\nIt passes only if ALL of these hold:\n{rubric}\n\n"
                             "Answer with PASS or FAIL on the first line, then one short reason.").content
        reply = reply if isinstance(reply, str) else " ".join(part.get("text", "") for part in reply if isinstance(part, dict))
        verdicts.append((reply.strip().upper().startswith("PASS"), reply.strip().splitlines()[-1][:200]))
    return {"key": "wording_rubric", "score": int(all(v for v, _ in verdicts)), "comment": " | ".join(r for _, r in verdicts)}


def passed(run, example) -> bool:
    return not failed_checks(example.outputs, run.outputs)


def critical_gate(runs, examples) -> dict:
    critical = [(r, e) for r, e in zip(runs, examples) if e.metadata["severity"] == "critical"]
    return {"key": "critical_gate", "score": int(all(passed(r, e) for r, e in critical)), "comment": f"{sum(passed(r, e) for r, e in critical)}/{len(critical)} critical pass"}


def major_pass_rate(runs, examples) -> dict:
    major = [(r, e) for r, e in zip(runs, examples) if e.metadata["severity"] == "major"]
    return {"key": "major_pass_rate", "score": sum(passed(r, e) for r, e in major) / len(major)}


if __name__ == "__main__":
    results = evaluate(
        target, data=DATASET, evaluators=[policy_checks, wording_judge], summary_evaluators=[critical_gate, major_pass_rate],
        experiment_prefix=f"policy-engine-{DATASET}", metadata={"engine": "huddlecart.policy", "judge": JUDGE_MODEL if USE_JUDGE else None},
        max_concurrency=4, client=Client(),
    )
    print(results.experiment_name)
    for row in results:
        scores = {r.key: r.score for r in row["evaluation_results"]["results"]}
        failed = next((r.comment for r in row["evaluation_results"]["results"] if r.key == "policy_exact" and not r.score), "")
        print(f"{row['example'].metadata['severity']:8} {row['example'].inputs['scenario_id']:34} {scores} {failed}")
