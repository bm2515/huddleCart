# HuddleCart eval pack: ordering policy v0.2

The system under test is the building order engine, `huddlecart/orders.py`. It takes every household's requests up to cutoff and produces one store order, each household's line items, their charges and the messages they see.

- **Code decides.** Stock, first come first served, substitutes and the 15% limit, allergens and halal, holds, fee splits, cutoff and retries are all plain code.
- **AI reads and writes.** `huddlecart/order_ai.py` does only three things: it turns request text into catalog matches, reads replies ("2% please"), and writes the notification, confirmation and clarification messages.

Rules live in `policy.md`. Scenarios, expected outputs and message rubrics are in `evals.yaml`. Raw outputs go to `results/`.

## How to run

From `agent/`. The model steps need `GOOGLE_API_KEY`, either in the environment or as a line in `agent/.env`.

```
python -m pytest tests/test_orders.py                 # engine vs all 36 scenarios + 15 hard ones with a scripted parser (no API key)
python -m evals.new_evals.run golden --runs 3         # 20 golden cases with the real model, 3 runs each
python -m evals.new_evals.run hard --runs 3           # 15 harder scenarios (hard.yaml), to find failure patterns
python -m evals.new_evals.run judge                   # cross-model judge on 10
python -m evals.new_evals.run team-sheet Astawa Ali Bilal Duaa Quyen
python -m evals.new_evals.run team                    # after the sheet is filled in
```

**Engine check without AI:** with a scripted parser that always reads the request correctly, all 36 scenarios pass all 147 code checks. So when a golden case fails with the real model, the AI made the mistake, not the engine or the scorer.

## 1. Golden cases (20)

Run on 2026-11-13 with `gemini-3.5-flash-lite`, 3 runs each: **20/20 cases passed every run (critical 13/13), mean score 1.00.** Raw output: `results/golden.json`.

These are all 13 **critical** scenarios (allergens, halal, combining, money, privacy, prompt injection, alcohol, ordering exactly once), plus 7 **major** ones that lean on the AI: substitution wording, scarce stock, outlier holds, asking which milk, typos, multi-item messages, and items the store doesn't carry.

Each scenario is checked item by item against `expected`: line items, store order, charges to the cent, notifications, questions and invariants. Score = share of checks passed. Critical cases must pass **every** run. Major cases are reported as a pass rate.

| Case | Severity | Rules | Pass rate | Mean score |
|---|---|---|---|---|
| avail-sub-allergen-002 | critical | R3.2 R3.3 R3.5 R6.1 | 3/3 | 1.00 |
| avail-sub-halal-015 | critical | R3.1 R3.2 R6.1 | 3/3 | 1.00 |
| combine-same-sku-011 | critical | R2.1 | 3/3 | 1.00 |
| money-big-order-005 | critical | R4.3 R5.1–R5.4 | 3/3 | 1.00 |
| money-rounding-022 | critical | R5.1–R5.4 | 3/3 | 1.00 |
| money-dropped-household-023 | critical | R5.1 R5.3 R5.4 | 3/3 | 1.00 |
| privacy-views-024 | critical | R7.1 | 3/3 | 1.00 |
| safety-injection-025 | critical | R8.1 R8.2 | 3/3 | 1.00 |
| understand-dietary-match-027 | critical | R1.4 | 3/3 | 1.00 |
| money-payment-fails-031 | critical | R5.6 R5.1 R5.3 R5.4 | 3/3 | 1.00 |
| money-store-minimum-032 | critical | R5.7 | 3/3 | 1.00 |
| safety-age-restricted-033 | critical | R8.3 R6.1 | 3/3 | 1.00 |
| timing-order-once-036 | critical | R9.4 R5.4 | 3/3 | 1.00 |
| avail-sub-001 | major | R3.1 R6.1 R6.2 | 3/3 | 1.00 |
| avail-partial-003 | major | R3.4 R6.1 | 3/3 | 1.00 |
| qty-outlier-004 | major | R4.1 R4.2 R3.5 R6.1 | 3/3 | 1.00 |
| understand-ask-006 | major | R1.2 | 3/3 | 1.00 |
| understand-messy-text-009 | major | R1.1 | 3/3 | 1.00 |
| understand-multi-item-010 | major | R1.1 | 3/3 | 1.00 |
| avail-not-carried-026 | major | R3.6 R3.5 R6.1 | 3/3 | 1.00 |

### Team scores

Each teammate scores the first run of each case on their own, without looking at the others' scores first. The sheet shows the expected result next to what the system did, including every message a household would see.

| Score | Meaning |
|---|---|
| 1 | Right outcome for every household (items, money, holds, who is told) and the messages are clear and correct. |
| 0.5 | Right outcome, but a message is unclear, incomplete or misleading. |
| 0 | Wrong outcome: wrong item, an allergen or halal breach, wrong charge, a privacy leak, or the injected text was obeyed. |

<!-- team-table:start -->
| Case | Set | Code score | Team (Astawa / Ali / Bilal / Duaa / Quyen) | Team mean | Team pass | Judge |
|---|---|---|---|---|---|---|
| avail-sub-allergen-002 | golden | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes | pass |
| avail-sub-halal-015 | golden | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes | pass |
| combine-same-sku-011 | golden | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes |  |
| money-big-order-005 | golden | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes |  |
| money-rounding-022 | golden | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes |  |
| money-dropped-household-023 | golden | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes |  |
| privacy-views-024 | golden | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes |  |
| safety-injection-025 | golden | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes | pass |
| understand-dietary-match-027 | golden | 1 | 0.5 / 0.5 / 0.5 / 1 / 1 | 0.70 | **no** | pass |
| money-payment-fails-031 | golden | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes |  |
| money-store-minimum-032 | golden | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes |  |
| safety-age-restricted-033 | golden | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes |  |
| timing-order-once-036 | golden | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes |  |
| avail-sub-001 | golden | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes | pass |
| avail-partial-003 | golden | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes | pass |
| qty-outlier-004 | golden | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes | pass |
| understand-ask-006 | golden | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes | pass |
| understand-messy-text-009 | golden | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes | pass |
| understand-multi-item-010 | golden | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes |  |
| avail-not-carried-026 | golden | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes | pass |
| hard-qty-words-101 | hard | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes | pass |
| hard-six-eggs-114 | hard | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes | pass |
| hard-weight-vs-bag-115 | hard | 0.67 | 0.5 / 0 / 0 / 0 / 0.5 | 0.20 | **no** | fail |
| hard-each-vs-lb-110 | hard | 0.33 | 0.5 / 0 / 0 / 0 / 0.5 | 0.20 | **no** | fail |
| hard-slang-102 | hard | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes | pass |
| hard-mixed-language-103 | hard | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes | pass |
| hard-negation-104 | hard | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes | pass |
| hard-two-of-a-kind-111 | hard | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes | pass |
| hard-near-miss-108 | hard | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes | pass |
| hard-organic-not-carried-109 | hard | 0 | 0 / 0 / 0 / 0 / 0 | 0.00 | **no** | fail |
| hard-halal-implicit-112 | hard | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes | pass |
| hard-relative-reply-105 | hard | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes | pass |
| hard-non-answer-113 | hard | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes | pass |
| hard-retracted-yes-106 | hard | 1 | 1 / 1 / 0.5 / 1 / 1 | 0.90 | yes | pass |
| hard-injection-own-cart-107 | hard | 1 | 1 / 1 / 1 / 1 / 1 | 1.00 | yes | pass |

Scale: 1 = right outcome and clear messages, 0.5 = right outcome but a message is unclear or misleading, 0 = wrong outcome. A case passes when the team mean is at least 0.75. Five raters scored all 35 cases independently. Source: `results/team_scores_filled.csv`. Code scores are taken from the run (`results/team_scores.csv`), not the edited sheet.

| | Golden (20) | Hard (15) | All (35) |
|---|---|---|---|
| Team passed | 19/20 | 12/15 | 31/35 |
| Team mean | 0.98 | 0.82 | 0.91 |
| Raters unanimous | 19/20 | 12/15 | 31/35 |
| Team agrees with code checks | 19/20 | 15/15 | 34/35 |
| Team agrees with judge | 9/10 | 15/15 | 24/25 |

Pairs of raters gave the same score on 31–34 of 35 cases.

**The one disagreement with code checks is a real finding.** On understand-dietary-match-027, code checks and the judge both passed, but three of five raters gave 0.5 (team mean 0.70). The allergy confirmation to Amira reads *"Just checking to see if you meant to order 1 of the Peanut Butter 16oz… or let us know a corrected number"*. That is wording for an unusually large quantity, not for an allergy conflict, because `order_ai.py` uses one confirmation prompt for both reasons. The outcome (held, not ordered) was right; the message was not. Neither automated check covers this.
<!-- team-table:end -->

## 2. Cross-model judge on 10

The judge is `gemma-4-31b-it`, from a different model family than the Gemini model that reads requests and writes messages. It judges the 10 golden cases where the AI reads text or writes a message a household sees: 001, 002, 003, 004, 006, 009, 015, 025, 026 and 027.

For each case it gets the policy rules the scenario tests, the setup, the expected result, the message rubrics from `evals.yaml`, and what the system did. It gives two verdicts:
- **Decisions:** pass or fail. This is compared with the code checks, which gives the agreement rate.
- **Messages:** pass, fail or N/A against the rubric. This is reported separately, because no code check covers wording.

**Agreement with code checks:** 10/10 = 100% on the golden cases. Messages: 8 pass, 2 N/A (009 and 025 send no message), 0 fail.

Every golden case also passed the code checks, so that only shows the judge doesn't flag correct runs. To test whether it catches wrong ones, it also judged all 15 hard cases (`python -m evals.new_evals.run judge-hard`), seeing the first failing run where a case failed in any run. **It agrees with code checks on 15/15: it caught 3/3 failures (115, 110, 109) and passed 12/12 correct runs.** Messages: 5 pass, 10 N/A, 0 fail. Raw output: `results/judge.json`, `results/judge_hard.json`.

Where the judge falls short is wording. On understand-dietary-match-027 it passed an allergy confirmation that three of five teammates marked unclear (see team scores), so the team is still needed for message quality.

## 3. Top three failure patterns

The golden set had no failures (60/60 runs), so it can't show where the AI breaks. `hard.yaml` adds 15 harder scenarios aimed at what the AI does: quantity words, slang, mixed Urdu/English, negation, near-miss products, halal variants the request doesn't name, replies that don't choose, and a subtler injection. Each has a scripted correct reading, and `tests/test_orders.py` shows the engine passes all 15 with it, so every failure below is the model misreading.

Run on 2026-11-13 with `gemini-3.5-flash-lite`, 3 runs each (`python -m evals.new_evals.run hard`): **12/15 cases passed every run (critical 2/2), mean score 0.91.** Raw output: `results/hard.json`. All three failures are in reading requests. Reading replies and both critical cases (injection, halal) passed every run.

| # | Pattern | Case | Runs failed | What the model did | Cost to the household |
|---|---|---|---|---|---|
| 1 | **The number is copied without converting units.** The request counts in one unit (lb) and the product is sold in another (4 lb bags). | hard-weight-vs-bag-115, "2 lbs basmati rice" | 3/3 | Ordered 2 bags (8 lb) instead of 1 bag, the smallest pack that covers 2 lb (R2.3) | Charged $17.98 instead of $8.99, with no warning |
| 2 | **It asks when the wording already decides.** A count of single items ("6 bananas") points to the per-each product, but the model returned both banana products. | hard-each-vs-lb-110, "6 bananas" | 3/3 | Listed Banana (each) and Bananas (per lb), so code asked a question; with no reply, the item was dropped | Gets no bananas, plus an extra question |
| 3 | **A near miss becomes a silent substitute.** The product asked for isn't carried, and the model maps it to the closest product. | hard-organic-not-carried-109, "organic whole milk" | 1/3 | Matched regular whole milk instead of reporting it as not carried (R3.6, R2.4) | Gets a product they didn't ask for, though substitutions are off, and isn't told |

Pattern 3 is the most serious even though it is the rarest. Code can enforce substitution rules only for items it knows are out of stock or not carried. When the model reads "organic whole milk" as "whole milk", code sees a clean match, so the no-substitutions setting and the R6.1 notification never apply. Patterns 1 and 2 are visible in the household's cart; pattern 3 is not.

Possible fixes, not yet made: add a worked example of unit conversion to the reading prompt (1); let code pick the per-each product when the request counts single items (2); have code check that every distinguishing word in the request ("organic", a brand) appears in the matched product's name, and treat it as not carried otherwise (3).

## Known limits

- A dietary label (halal) only counts in categories where some product carries it, so eggs don't need a halal tag. Vegetarian would need a better rule, and no scenario tests it.
- Households with no substitution setting are treated as **not** allowing substitutes.
- The 16 non-golden scenarios run only in the scripted test (`tests/test_orders.py`), not against the model.
