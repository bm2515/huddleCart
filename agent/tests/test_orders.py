"""The order engine against all 36 policy v0.2 scenarios, with the rule-based brain (no API key).

If these pass, a golden-case failure with the real model is the AI's mistake, not the engine's or the scorer's.
"""
import pytest

from evals.new_evals.run import SCENARIOS, SPEC, score
from huddlecart.orders import RuleBrain, run_scenario


@pytest.mark.parametrize("sid", list(SCENARIOS))
def test_scenario(sid):
    scenario = SCENARIOS[sid]
    out = run_scenario(scenario["setup"], SPEC["defaults"], RuleBrain())
    graded = score(scenario["expected"], out)
    assert graded["passed"], [k for k, ok in graded["checks"].items() if not ok]


class LyingBrain(RuleBrain):
    """Reads every request as whatever `reads` says, to check that code, not the model, has the last word."""

    def __init__(self, reads):
        self.reads = reads

    def read_request(self, text, catalog):
        return self.reads(text, catalog)


def test_made_up_sku_is_never_ordered():  # R3.6
    setup = {"catalog": [{"sku": "eggs-12", "name": "Eggs, dozen", "category": "eggs", "price": 4.29, "unit": 12, "stock": 30}],
             "households": [{"id": "ana", "requests": [{"text": "curry leaves", "added_at": "2026-11-14T09:00:00"}]}]}
    brain = LyingBrain(lambda text, catalog: [{"item": text, "skus": ["curry-leaves-from-elsewhere"], "qty": 1, "pieces": None}])
    out = run_scenario(setup, SPEC["defaults"], brain)
    assert out["line_items"]["ana"] == [] and out["store_order"] == [] and out["external_orders"] == []
    assert [n["outcome"] for n in out["notifications"]] == ["dropped"]


def test_fooled_brain_still_cannot_order_alcohol_or_touch_other_carts():  # R8.2, R8.3
    scenario = SCENARIOS["safety-injection-025"]
    brain = LyingBrain(lambda text, catalog: [{"item": "red wine", "skus": ["red-wine-750ml"], "qty": 6, "pieces": None}]
                       if "SYSTEM" in text else RuleBrain().read_request(text, catalog))
    out = run_scenario(scenario["setup"], SPEC["defaults"], brain)
    assert out["line_items"]["ben"] == [{"sku": "eggs-12", "qty": 1}]
    assert "red-wine-750ml" not in {l["sku"] for l in out["store_order"]}
    assert out["payment_status"] == "pending"


# ---------- hard set: the engine with a scripted correct reading of every request and reply ----------

from evals.new_evals.run import HARD, HARD_SPEC  # noqa: E402


class ScriptedBrain(RuleBrain):
    """Reads exactly what `scripted` in hard.yaml says is the right reading."""

    def __init__(self, script):
        self.script = script

    def read_request(self, text, catalog):
        return [dict(r) for r in self.script["reads"][text]]

    def read_choice(self, reply, options):
        return self.script["choice"][reply]

    def read_yes(self, reply):
        return self.script["confirms"][reply]


@pytest.mark.parametrize("sid", list(HARD))
def test_hard_scenario_with_correct_reading(sid):
    scenario = HARD[sid]
    out = run_scenario(scenario["setup"], HARD_SPEC["defaults"], ScriptedBrain(scenario["scripted"]))
    graded = score(scenario["expected"], out)
    assert graded["passed"], [k for k, ok in graded["checks"].items() if not ok]
