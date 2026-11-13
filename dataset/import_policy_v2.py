"""Import huddlecart-policy-golden-v2 scenarios into LangSmith.

Usage:
    export LANGSMITH_API_KEY=...   # plus LANGSMITH_WORKSPACE_ID if you use one
    python import_policy_v2.py

Creates the dataset if missing, then upserts each scenario so re-runs are safe.
Each example: inputs = {setup, title, scenario_id}, outputs = expected fields,
metadata = policy tags / severity / split, same shape as huddlecart-policy-golden.
"""
import json
import uuid
from pathlib import Path

from langsmith import Client

DATASET_NAME = "huddlecart-policy-golden-v2"
DESCRIPTION = (
    "HuddleCart ordering policy v0.3 scenarios (13): compound rule interactions, "
    "boundary precision, multi-turn sequences and adversarial cases. "
    "Critical = must pass every run; major = pass rate."
)

scenarios = json.loads(Path(__file__).with_name("huddlecart-policy-golden-v2.json").read_text())

client = Client()

if client.has_dataset(dataset_name=DATASET_NAME):
    dataset = client.read_dataset(dataset_name=DATASET_NAME)
else:
    dataset = client.create_dataset(dataset_name=DATASET_NAME, description=DESCRIPTION)
print(f"dataset: {dataset.name} ({dataset.id})")

existing_ids = {str(example.id) for example in client.list_examples(dataset_id=dataset.id)}

for s in scenarios:
    meta = dict(s["metadata"])
    meta["scenario_id"] = s["scenario_id"]
    example_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{DATASET_NAME}:{s['scenario_id']}")
    fields = dict(
        inputs={"setup": s["setup"], "title": s["title"], "scenario_id": s["scenario_id"]},
        outputs=s["expected"] | {"expected_raw": s["expected_raw"]},
        metadata=meta,
    )
    if str(example_id) in existing_ids:
        client.update_example(example_id=example_id, **fields)
    else:
        client.create_example(dataset_id=dataset.id, example_id=example_id, **fields)
    print(f"  + {s['scenario_id']} ({meta['severity']})")

print(f"done: {len(scenarios)} examples in {DATASET_NAME}")
