# HuddleCart eval pack

All runs use the catalog snapshot (`HUDDLECART_SEARCH=snapshot`) so answers are stable. Raw outputs are in `evals/results/`.

## 1. Golden cases (20)

Expected outputs live in `golden_cases.json`. Rule score: 1.0 when intent and every expected product (or out-of-stock flag, or pod) match, partial credit per check.

- Run 1, before rule fixes: **16/20 passed, mean 0.85**
- Run 2, after rule fixes: **20/20 passed, mean 1.00**
- Agent model for both: `gemini-3.5-flash-lite`

Fill in the team column: each teammate reads the output in `results/golden.json` and gives 0, 0.5 or 1.

| Case | Message | Run 1 | Run 2 | Team score |
|---|---|---|---|---|
| c01 | 2 shrimp chips | 1.0 | 1.0 | |
| c02 | can I get the spicy shrimp chips | 0.5 | 1.0 | |
| c03 | buldak noodles | 1.0 | 1.0 | |
| c04 | 2 bags of frozen dumplings | 0.5 | 1.0 | |
| c05 | chicken dumplings please | 1.0 | 1.0 | |
| c06 | tofu and bok choy | 1.0 | 1.0 | |
| c07 | 3 pocky | 1.0 | 1.0 | |
| c08 | jasmin rice 5 lb | 1.0 | 1.0 | |
| c09 | do you have paneer | 1.0 | 1.0 | |
| c10 | kimchi, scallions and soy sauce | 1.0 | 1.0 | |
| c11 | how close are we to free shipping? | 1.0 | 1.0 | |
| c12 | add a 6 pack of beer | 1.0 | 1.0 | |
| c13 | hi! what can you do? | 1.0 | 1.0 | |
| c14 | I want cheddar cheese by tomorrow | 0.0 | 1.0 | |
| c15 | mango mochi and hello panda | 1.0 | 1.0 | |
| c16 | oat milk | 1.0 | 1.0 | |
| c17 | a dozen eggs and a loaf of bread | 0.0 | 1.0 | |
| c18 | spaghetti and marinara for pasta night | 1.0 | 1.0 | |
| c19 | I need eggs by tonight | 1.0 | 1.0 | |
| c20 | sharp cheddar | 1.0 | 1.0 | |

## 2. Cross-model judge on 10

Judge: `gemma-4-31b-it`, a different model family from the Gemini agent. It reads the case, the expected output and the agent's blocks and says pass or fail.

**Agreement with rule scores: 8/10 = 80%**

| Case | Rules | Judge | Judge reason |
|---|---|---|---|
| c01 | pass | pass | Understood request, recommended correct product, and handled quantity. |
| c02 | pass | pass | The agent correctly flagged the spicy shrimp chips as out of stock and provided alternatives. |
| c03 | pass | fail | It listed non-Buldak noodles (Indomie and Nongshim) as Buldak noodles. |
| c04 | pass | fail | Included out-of-stock chicken dumplings. |
| c05 | pass | pass | The agent correctly flagged the chicken dumplings as out of stock and provided alternatives. |
| c06 | pass | pass | The agent correctly identified and recommended both requested items. |
| c07 | pass | pass | The agent correctly handled the flavor ambiguity by presenting multiple Pocky options. |
| c08 | pass | pass | The agent correctly handled the typo and provided an acceptable 5lb jasmine rice product. |
| c09 | pass | pass | The agent correctly flagged the paneer as out of stock. |
| c10 | pass | pass | The agent correctly identified and recommended all three requested items. |

Both disagreements are cases where the judge is stricter than the rules: the right product was recommended, but the card row also showed other alternatives (other noodle brands, an out-of-stock dumpling).

## 3. Top three failure patterns

1. **Quiet swaps when the exact item is out of stock** (c02). "Spicy shrimp chips" got the original flavor recommended instead of a flag. Fix: a rule in `item_blocks`, if an exact title match is out of stock, always show the out-of-stock card with alternatives.
2. **Deadline found but intent mislabeled** (c14). The model extracted `deadline_hours=24` but called it `add_items`, so it searched one store and never checked pods. Fix: a rule in `understand`, any deadline means `find_pod`.
3. **Vague requests land on an out-of-stock product** (c04). "Frozen dumplings" picked the out-of-stock chicken dumplings when in-stock ones existed. Still happens 1 in 10 on the fast tier, never on the strong tier.

Also seen once: a model call returned nothing (c17, `Error calling model 'gemini-3.5-flash-lite' (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'messa`). It passed on retry; production needs one retry on provider errors.

## 4. Unit economics: same 10 tasks, two tiers

Prices from ai.google.dev/gemini-api/docs/pricing (paid tier, per 1M tokens): Flash-Lite $0.30 in / $2.50 out, 3 Flash $0.50 in / $3.00 out. Our free key ran them at $0.

| | Fast: gemini-3.5-flash-lite | Strong: gemini-3-flash-preview |
|---|---|---|
| Quality | 9/10, mean 0.95 | 10/10, mean 1.00 |
| Median latency | 3.6 s | 5.7 s |
| p90 latency | 11.8 s | 14.6 s |
| Avg tokens in / out | 724 / 161 | 724 / 1,514 |
| Cost per 100 runs | **$0.06** | **$0.49** |

**Trade-off we accept:** Flash-Lite by default. It is 8x cheaper and 2 s faster per message, and its one miss (c04) is a vague request where the neighbor still sees every option and taps Add themselves, so no money moves on a wrong guess. The strong tier's extra cost is mostly thinking tokens. A pod of 8 people sending about 5 messages each costs well under 1 cent in model spend on either tier, against $16 in pod fees.
