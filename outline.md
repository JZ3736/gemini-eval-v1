# `gemini-eval` Playbooks Outline & Best-Practice Guardrails

An analysis of the four core playbooks in `gemini-eval/`, detailing **what each playbook includes** and **the critical evaluation best practices that ad-hoc / dynamically generated eval scripts almost always miss**.

---

## 1. [`build-eval.md`](./build-eval.md) — Designing & Building the Eval

* **What It Includes:**
  * Scoping a single flow (`--flow <flow-name>`) and locating the application's real entry point (`Step 0`).
  * Sourcing 15–100 realistic inputs from logs, tickets, or anchored synthesis, checking PII/retention rules, and getting explicit user sign-off (`Step 1`).
  * Selecting the right grading tier: Programmatic checks $\rightarrow$ Blind Pairwise Judge $\rightarrow$ Pointwise Rubric Judge $\rightarrow$ Human spot-check (`Step 2`).
  * Building `run-eval.py` from [`report/runner-scaffold.py`](./report/runner-scaffold.py), running the baseline, and compiling the interactive `report.html` via [`report/build-report-lite.py`](./report/build-report-lite.py) (`Step 3–4`).

* **What Ad-Hoc / Dynamic Evals Miss Without This Playbook:**
  * **Frozen Pairwise Reference (`baseline/ref/`):** When using a pairwise judge across multiple rounds, `build-eval.md` freezes the baseline outputs to disk once and sets baseline's self-win rate to `0.500`. Ad-hoc scripts regenerate or re-compare shifting outputs, making win rates incomparable across rounds.
  * **Oracle (~100%) & Null (~0%) Smoke Tests Before Spending Money:** Requires pushing a known-good answer (oracle) and an empty/wrong answer (null) through the grader *before* running the dataset. Ad-hoc scripts skip this and discover after paying for 100 calls that the grader or regex had a bug.
  * **Pilot-Measured Cost Projection (Not Guessing):** Measures actual `input + output + thinking + judge` tokens on 1–2 pilot cases (`min / median / max`) to calculate exact run cost before asking consent. Ad-hoc agents guess token counts from string length (routinely 3–10$\times$ off because they ignore `thoughtsTokenCount` and multi-turn growth).
  * **Calling the Real Entry Point vs. Rewriting the API Call:** Instructs the agent to invoke the customer's actual function/agent loop (mocking only dangerous DB/email side effects) rather than copy-pasting the prompt into a raw API call that bypasses the customer's real parser and tool wiring.
  * **Mandatory Two-Gate Human Sign-Off:** Forces a hard stop until the human reviews 5 real graded examples in `report.html` and confirms *"I wouldn't have scored any of these differently."*

---

## 2. [`eval-audit.md`](./eval-audit.md) — Auditing Dataset, Harness & Grader Hygiene

* **What It Includes:**
  * 3-tier dataset audit: programmatic checks (duplicates, class balance, length skew) $\rightarrow$ stratified human/agent read $\rightarrow$ LLM per-case auditor (`§1`).
  * Harness & plumbing audit (`§2`), metrics hygiene (`§3`), grader & LLM-judge bias audit (`§4`), and statistical power / noise-floor math (`§5`).

* **What Ad-Hoc / Dynamic Evals Miss Without This Playbook:**
  * **Catching "Old-Model Outputs Disguised as Ground Truth":** In model migrations, customers often hand over the *old model's* outputs as the "expected" golden set. `eval-audit.md` flags this immediately—because reference-matching against old model outputs penalizes a smarter model (`gemini-3.8-flash` / `gemini-4-pro`) whenever it improves on the old model's mistakes!
  * **Separating Infra Errors (`errors.jsonl`) from Model Failures (`results.jsonl`):** Ad-hoc scripts catch `429` rate limits, timeouts, or `MAX_TOKENS` truncations and score them as `0.0` (fail). `eval-audit.md` routes infra crashes to `errors.jsonl` (so resume re-runs them) and marks cut-off responses as `status: "truncated"` instead of averaging them in as wrong answers.
  * **"No Answer" vs. "Negative Answer" Conflation:** Ensures an empty/crashed response (`[]` or `None`) isn't scored the same as a valid negative prediction (`"no signals found"`).
  * **Served-Model Identity Assertion:** Checks `response.model_version` on every call to prove a provider fallback or alias didn't silently route requests to a different model.
  * **Anti-Bias Judge Rules:** Enforces randomized A/B order (position bias), no `"reference/baseline"` labels shown to the judge (label deference), explicit instruction not to reward length (verbosity bias), and never using the model-under-test as its own judge (self-preference bias).

---

## 3. [`eval-hillclimb.md`](./eval-hillclimb.md) — Iterative Quality Optimization Loop

* **What It Includes:**
  * Pre-flight climbability proof: noise floor (`± CI`) vs. headroom (`Step 0.5`).
  * Agreeing on target metric, guardrails, editable scope, and stopping plateau rules (`Step 1–2`).
  * Stratified `train` / `test` split and `_state.json` tracking (`Step 3`).
  * Autonomous `analyze` $\rightarrow$ `apply` $\rightarrow$ `run` $\rightarrow$ `record` loop with isolated analyzer subagents (`Step 4`).

* **What Ad-Hoc / Dynamic Evals Miss Without This Playbook:**
  * **Never Splitting `train`/`test` by Baseline Score (Regression-to-the-Mean Trap):** Ad-hoc agents love to pick the "10 lowest-scoring cases" as the `train` set. `eval-hillclimb.md` strictly forbids this and requires a **random stratified split**—because hand-picking the worst baseline cases causes them to bounce back up on re-run by pure chance (regression to the mean), creating fake `train` gains that fail on `test`.
  * **Physical Subagent Isolation for `train` vs. `test`:** Instead of the main agent reading all transcripts (which leaks `test` cases into prompt edits), the main session only ever sees summary numbers and spawns a fresh analyzer subagent (`invoke_subagent`) given *only* `train` trace file paths.
  * **Build-Variance Control for Two-Stage Pipelines:** If the prompt builds an intermediate artifact (like an index or memory store) that is then queried, `eval-hillclimb.md` requires rebuilding the baseline 2–3 times unchanged to measure *build variance*—which single-build reps completely miss.
  * **Harness Integrity Gate (`--approve-harness` SHA-256):** Prevents an autonomous optimization loop from "improving" the score by accidentally (or cleverly) editing the grader or test cases instead of the app.
  * **De-Fluffing & Single-Hypothesis Patches (`vN/change.patch`):** Stops the agent from bundling 5 random prompt edits together or adding platitudes (*"be very careful, think step by step"*), ensuring every round tests one root cause and produces a clean git revert/PR diff.

---

## 4. [`cost-hillclimb.md`](./cost-hillclimb.md) — Cost & Latency Optimization Search

* **What It Includes:**
  * A strict 6-step lever order: Caching health (`Step 0`) $\rightarrow$ Legacy prompt/config audit (`Step 1`) $\rightarrow$ Model $\times$ Thinking staircase walk (`Step 2`) $\rightarrow$ Prompt climb on frozen model (`Step 3`) $\rightarrow$ Down-left re-probe (`Step 4`) $\rightarrow$ 3-run joint confirmation (`Step 5`).
  * Pre-registered 3-part adoption gates (Quality Band, Cost Margin, Verified Mechanism).

* **What Ad-Hoc / Dynamic Evals Miss Without This Playbook:**
  * **Detecting Silent Context-Cache Invalidation (`Step 0`):** Switching models or `thinking_config` mid-session invalidates prefix caches, making a cheaper setting look more expensive. Ad-hoc evals never check `cachedContentTokenCount` before and after each change.
  * **Stripping Legacy Prompt Rituals Before Comparing Models (`Step 1`):** Older prompts often contain forced visible `<scratchpad>` or "re-read every file" instructions. Newer models (`gemini-3.8-flash`, `gemini-4-pro`) follow these literally on top of native `thinking_config`, doubling token spend and mis-ranking models unless audited first.
  * **The "Stronger Model at Low Thinking" Inversion (`Step 2` Staircase Walk):** Ad-hoc cost tuning either tests an expensive full grid or only tests the cheapest model at default thinking. `cost-hillclimb.md` uses a **top-left staircase walk** because a stronger tier at `LOW` thinking often uses fewer turns and tokens than a smaller tier working hard—finding the cheapest passing config in `tiers + effort` steps instead of `tiers × effort`.
  * **Effort-Matched Cost Projections & $n \ge 2$ Promotion Near the Floor:** Prevents a "lucky single-run pass" on a cheap model from becoming the incumbent and pruning the real winner.
  * **The "Down-Left Re-Probe" After Prompt Cleanup (`Step 4`):** Prompt wins don't transfer across models, *but* cleaning up the prompt on a winning model often makes the next-cheaper model tier (or lower thinking notch) pass when it failed earlier.
  * **Requiring a Verified Mechanism Gate (`Step 5`):** Rejects any "cost win" that only happened due to random output-length variance rather than the predicted mechanism (e.g., fewer tool calls or lower thinking tokens), and reports the $n \ge 3$ fresh confirmation mean rather than the lucky selection-round score.
