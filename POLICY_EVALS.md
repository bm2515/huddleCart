# HuddleCart policy evals v2

1. Upload the dataset (once):
   cd dataset
   pip install langsmith
   export LANGSMITH_API_KEY=your_key
   python import_policy_v2.py
   -> ends with "done: 13 examples in huddlecart-policy-golden-v2". Safe to re-run.

2. Run the policy engine on it:
   cd ../huddlecart/agent
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   export LANGSMITH_API_KEY=your_key
   export HUDDLECART_POLICY_DATASET=huddlecart-policy-golden-v2
   python -m evals.run_policy_evals --no-judge

The output lines (severity, scenario id, scores, failed check names) are safe to share.
The LangSmith experiment page shows the expected answers, so don't share it with the builder.
