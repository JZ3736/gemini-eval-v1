# `gemini-eval` Framework

A structured, reproducible evaluation and hill-climbing framework for Gemini model migrations, prompt optimization, and cost/latency tuning.

* **How `gemini-eval` was built:** Adapted directly from the [`anthropic-eval`](../anthropic-eval) framework ([`anthropics/skills/skills/claude-api/shared/evals`](https://github.com/anthropics/skills/tree/main/skills/claude-api/shared/evals)), preserving 100% of its evaluation science, methodologies, and directory/artifact structure while tailoring it for **Antigravity / Jetski** and the **Gemini ecosystem** (see [`references/diff.md`](./references/diff.md) for the full conversion map):
  * **Antigravity / Jetski Native Tooling:** Replaced Claude Code tool conventions with Jetski's native tools (`ask_question`, background `run_command` with reactive wakeup, `invoke_subagent` for isolated `train`-only round analysis, and `.antigravity/hillclimb/<flow>/` state paths).
  * **Python & `google-genai` SDK Native:** Ported the Node.js (`.mjs`) runner scaffold and HTML report bundler to zero-dependency **Python** ([`report/runner-scaffold.py`](./report/runner-scaffold.py), [`report/build-report-lite.py`](./report/build-report-lite.py)) wired to the Google GenAI SDK (`google-genai`), Gemini model families (`gemini-4-pro`, `gemini-3.8-flash`, `gemini-2.5-*`), and Gemini API parameters (`thinking_config` / `thinking_level`, `response_schema`, `finishReason == "MAX_TOKENS"`, `thoughtsTokenCount`, and `cachedContentTokenCount`).

* **How to use `gemini-eval`:**
  * **1. Clone `gemini-eval` into Your Workspace:** Run `git clone https://github.com/JZ3736/gemini-eval-v1.git gemini-eval` in your Antigravity / Jetski workspace (`gemini-eval/` stays untouched as your reusable toolkit).
  * **2. Point to the Customer's Agent Repo or Dataset Folder:** Never copy customer code into `gemini-eval/`. Instead, keep the customer's work in its own sibling folder—either **clone/open the customer's agent repo as-is** (so its `.venv`, imports, and `git diff` patches stay intact) or **create a lightweight case folder** (like `case-acroynm/`) if they only provided datasets and prompts.
  * **3. Ask Jetski to Run the Eval Using `gemini-eval`:** Tell Jetski: *"Read the customer folder/repo at `<customer-folder>` and use the `gemini-eval` framework to run the eval (e.g., migrating to `gemini-3.8-flash`)."* Jetski automatically follows `gemini-eval/` to build `run-eval.py` inside the customer folder, run the evaluation / hill-climb, and generate `report.html`, `narrative.md`, and clean `change.patch` diffs.

## Why Use `gemini-eval` Instead of Ad-Hoc Throwaway Eval Scripts in Jetski?

* **Prevents Overfitting (Strict Train/Test Isolation):**
  * **`gemini-eval`:** Enforces a stratified `train` / `test` split (e.g., 60/40) at the runner level ([`report/runner-scaffold.py`](./report/runner-scaffold.py)). Jetski only inspects `train` failures when iterating on prompts or model configs, keeping `test` strictly held-out.
  * **Throwaway Code:** Usually evaluates and inspects all cases together, causing the agent to tune prompts to pass specific test cases (memorizing the test set).

* **Eliminates Judge Bias (Blind Pairwise & Anti-Self-Bias):**
  * **`gemini-eval`:** Randomizes candidate order (`Response A` vs. `Response B`) during pairwise judging so the judge cannot tell which output is `baseline` vs. `v1`, and enforces an anti-self-bias rule (never using the model-under-test as its own judge).
  * **Throwaway Code:** Often grades outputs in the same context window or passes unblinded labels, introducing position bias and self-preference bias.

* **Separates Real Wins from Random Luck (Noise-Floor Math):**
  * **`gemini-eval`:** Because LLMs can give slightly different answers on every run, [`report/runner-scaffold.py`](./report/runner-scaffold.py) supports running each case multiple times (`--reps`) and calculates a margin of error (`± CI`). You immediately know if a `+3%` score jump is a real improvement or just random luck.
  * **Throwaway Code:** Looks at a single-run average with no margin of error, tricking you into keeping prompt changes that only won by chance.

* **Code Checks for Facts + AI Judge for Nuance:**
  * **`gemini-eval`:** Uses strict Python code to check objective rules (Did the output get cut off at `MAX_TOKENS`? Is the JSON valid? Is the quote actually in the transcript?) and only uses an AI Judge for subjective quality ([`build-eval.md`](./build-eval.md)).
  * **Throwaway Code:** Relies on an AI Judge to grade everything or uses quick scripts that miss cut-off responses, hallucinated quotes, or broken JSON fields.

* **Fast Parallel Runs Without Overloading the Agent's Memory:**
  * **`gemini-eval`:** Runs all test cases in parallel in Python (`run-eval.py`), saves outputs to disk (`results.jsonl` and `traces/*.json` per [`report/SCHEMA.md`](./report/SCHEMA.md)), and only asks a helper subagent to read the specific `train` cases that failed ([`eval-hillclimb.md`](./eval-hillclimb.md)).
  * **Throwaway Code:** Pastes dozens of long transcripts directly into one chat window—slowing down the agent, overflowing its memory, and hurting reasoning quality.

* **Exact Cost Tracking & One-Click Visual Report (`report.html`):**
  * **`gemini-eval`:** Automatically records input, output, and thinking tokens, latency, and exact dollar cost per call (separating your app's model cost from the AI Judge's cost), then builds an interactive [`report.html`](./report/build-report-lite.py) via [`report/build-report-lite.py`](./report/build-report-lite.py) to compare every round (`baseline` $\rightarrow$ `v1` $\rightarrow$ `v2`).
  * **Throwaway Code:** Prints messy terminal text that doesn't separate judge cost from model cost and can't be shared with customers as a clean report.

---

## Core Components

* **Playbooks:**
  * [`build-eval.md`](./build-eval.md) — Step-by-step guide to build a working `run-eval.py` from scratch when a customer doesn't have an eval yet:
    * **Scope One Flow & Build the Dataset:** Picks one clear task to test, gathers 15–50 real examples (from logs or synthetic edge cases), verifies ground-truth answers are accurate, and locks a random `train` / `test` split.
    * **Pick the Simplest Grader That Works:** Uses fast Python checks first (exact match, regex, JSON schema, unit tests) and only adds an AI Judge (with a clear rubric or blind A/B comparison) when grading subjective quality.
    * **Estimate Cost Before Spending Money:** Runs 1–2 pilot cases first to measure token usage and shows the user the exact dollar estimate before running the full dataset.
    * **Wire Up `run-eval.py` & Generate `report.html`:** Plugs the customer's prompt/model call and grader into [`report/runner-scaffold.py`](./report/runner-scaffold.py), runs the `baseline`, and compiles the interactive HTML report.
  * [`eval-hillclimb.md`](./eval-hillclimb.md) — Automated loop to iteratively improve quality scores without overfitting:
    * **Measure the Noise Floor First:** Before changing anything, runs the baseline to see how much scores fluctuate naturally—so the agent only keeps edits that beat random variance.
    * **Blind the Agent to Test Data (Subagent Isolation):** Each round, a fresh analyzer subagent reads *only* failing `train` transcripts to diagnose root causes. The main agent never sees `test` transcripts, making it impossible to "cheat" or memorize test answers.
    * **One Root-Cause Fix per Round:** Instead of guessing or piling on vague "be careful" prompt fluff, the agent tests **one** concrete change at a time (prompt rule, tool definition, or `thinking_config`) and saves a clean git diff (`vN/change.patch`) so losing ideas are easily reverted.
    * **Automatic Stopping & Guardrails:** Keeps iterating until scores plateau for 3+ rounds or a guardrail metric (like latency or compliance) drops, then judges the final winner strictly on the unseen `test` split.
  * [`cost-hillclimb.md`](./cost-hillclimb.md) — Structured search to cut API cost and latency while keeping baseline quality:
    * **Fix Free Wins First (Caching & Prompt Bloat):** Verifies context caching is working and strips legacy prompt instructions that force newer Gemini models (`gemini-3.8-flash`, `gemini-4-pro`) to waste output/thinking tokens.
    * **Smart "Staircase Walk" Instead of Brute-Force Grid:** Rather than paying to test every combination of model $\times$ thinking budget, starts at a strong model with `LOW` thinking and steps **down** to cheaper models when quality passes, or **right** to higher thinking when quality fails—skipping expensive configurations that can't win.
    * **Re-Test Cheaper Tiers After Prompt Tuning:** Once the prompt is tuned on the winning model, steps down one more notch (e.g., to `gemini-3.8-flash-lite` or lower thinking), since a cleaner prompt often unlocks a cheaper model that failed earlier.
    * **3-Run Final Confirmation:** Re-runs the winning setup 3+ times on held-out `test` cases to prove cost dropped, quality held, and the expected token/tool savings actually occurred.
  * [`eval-audit.md`](./eval-audit.md) — Health check to verify an evaluation suite is trustworthy before you spend time and money optimizing against it:
    * **What it does:** Inspects your dataset, runner, and graders for hidden flaws—such as ground-truth labels copied from the old model's unverified outputs, API/timeout crashes falsely scored as `0` model failures, silent model fallbacks, or judges grading their own outputs.
    * **Benefits:** Stops you from optimizing against a "broken ruler"—ensuring a better model isn't unfairly penalized for disagreeing with old model mistakes, separating infra errors from model quality, and confirming the eval has enough statistical signal to detect real improvements.
* **Python Runner & Reporting Engine:**
  * *Why pre-built scripts are needed:* Without them, Jetski would have to write parallel execution, retry logic, error handling, and HTML report code from scratch every time—wasting time and introducing bugs. With these ready-made scripts, Jetski only fills in 3 simple functions (`load_cases`, `run_case`, `grade_case`).
  * [`report/runner-scaffold.py`](./report/runner-scaffold.py) — Ready-made template for `run-eval.py`.
    * **Benefits:** Handles running cases in parallel, automatic retries, crash-safe resume (picks up where it left off if interrupted), cut-off output detection, and margin-of-error (`± CI`) math out of the box.
  * [`report/build-report-lite.py`](./report/build-report-lite.py) — One-command HTML report builder.
    * **Benefits:** Turns raw scores and transcripts into a single, shareable `report.html` file where you can view score trends across rounds and click into side-by-side model outputs—no extra packages or web server needed.
  * [`report/SCHEMA.md`](./report/SCHEMA.md) — Standard file format rules for scores (`results.jsonl`), transcripts (`traces/`), and logs (`scores.tsv`).
    * **Benefits:** Keeps every file in a predictable format so the runner, the analyzer subagent, and the HTML report builder always work together without breaking.

---

## Reference Skills

* **Referenced Public-Facing Gemini Skills (GitHub):**
  * [`google-gemini/gemini-skills` — `skills/gemini-api-dev/SKILL.md`](https://github.com/google-gemini/gemini-skills/blob/main/skills/gemini-api-dev/SKILL.md) — Active Gemini model catalog, `google-genai` SDK client initialization, structured outputs (`response_schema`), and tool declaration patterns.
  * [`google-gemini/gemini-skills` — `skills/gemini-api-dev/references/migration.md`](https://github.com/google-gemini/gemini-skills/blob/main/skills/gemini-api-dev/references/migration.md) — Legacy-to-current Gemini model mappings, deprecated SDK (`google-generativeai` $\rightarrow$ `google-genai`) shifts, and `generateContent` / `Interactions` API migration guidance.
  * [`google/skills` — `skills/cloud/gemini-api/SKILL.md`](https://github.com/google/skills/blob/main/skills/cloud/gemini-api/SKILL.md) — Google Cloud / Vertex AI Gemini integration patterns and authentication.
  * [`google/skills` — `skills/cloud/gemini-api/references/advanced_features.md`](https://github.com/google/skills/blob/main/skills/cloud/gemini-api/references/advanced_features.md) — Implementation syntax for Content Caching (`client.caches.create`), Batch Prediction (`client.batches.create`), and Thinking (`ThinkingConfig` / `thinking_level`).

* **Local Gap-Filling Reference Files Created (`references/`):**
  * [`references/pricing.md`](./references/pricing.md) — **Fills the token-pricing & cost-math gap:** Public skills omit per-token dollar rate cards and eval cost formulas. Provides the $/1M token rate card across Gemini 4 / 3.8 / 3.5 / 2.5 and cross-family judges, exact `cost_usd` calculation (including billed `thinking_tokens` and discounted `cachedContentTokenCount`), and ready-to-paste `_state.json` `prices` maps.
  * [`references/prompt-audit.md`](./references/prompt-audit.md) — **Fills the pre-migration prompt & config audit gap:** Public migration docs cover SDK/API syntax changes but not prompt-behavior shifts. Provides the 5-part prompt-cruft audit (removing legacy step-by-step rituals, redundant tool checks, and heavy-handed `IMPORTANT!` caps that cause over-refusals or token bloat on `gemini-3.8-flash` / `gemini-4-pro`) and `GenerateContentConfig` normalization (`temperature=1.0`, `thinking_level` vs. `thinking_budget`).
  * [`references/cost-optimization.md`](./references/cost-optimization.md) — **Fills the operational cost-checklist & cache-debugging gap:** Public docs show how to call caching/batch APIs but not how to prioritize levers or debug silent cache misses. Provides the 7-step no-eval cost reduction order and context-caching invalidation diagnostics (prefix dynamic-token leaks, mid-session `thinking_config` key changes).
  * [`references/diff.md`](./references/diff.md) — **Fills the framework conversion traceability gap:** Documents the exact architectural, tool, schema, and Python runner mappings from the original Anthropic eval template to `gemini-eval`.

---

## Next Step: Packaging as a Portable, Shareable Skill

To enable any AI engineer to run standardized, reproducible customer evaluations out-of-the-box without copying files into customer repos:

* **1. Add a Root `SKILL.md` Entrypoint:**
  * Create `gemini-eval/SKILL.md` with YAML frontmatter (`name: gemini-eval`, `description: ...`) that routes user intents (`build`, `hillclimb`, `cost`, `audit`) to [`build-eval.md`](./build-eval.md), [`eval-hillclimb.md`](./eval-hillclimb.md), [`cost-hillclimb.md`](./cost-hillclimb.md), and [`eval-audit.md`](./eval-audit.md).
  * Instruct the agent to resolve [`report/runner-scaffold.py`](./report/runner-scaffold.py) and [`report/build-report-lite.py`](./report/build-report-lite.py) relative to the installed skill directory while writing all run artifacts to the customer's workspace (`.antigravity/hillclimb/<flow>/`).

* **2. Bundle as a Self-Contained Skill Directory:**
  * Keep the directory structure atomic and zero-dependency (standard Python + `google-genai` SDK):
    ```text
    gemini-eval/
    ├── SKILL.md                  # Skill entrypoint & sub-command router
    ├── build-eval.md             # Eval creation playbook
    ├── eval-hillclimb.md         # Quality hill-climb playbook
    ├── cost-hillclimb.md         # Cost/latency staircase playbook
    ├── eval-audit.md             # Eval suite audit playbook
    ├── report/
    │   ├── runner-scaffold.py    # Reusable Python eval harness
    │   ├── build-report-lite.py  # Zero-dependency HTML report bundler
    │   └── SCHEMA.md             # Artifact & JSONL data contract
    └── references/
        ├── pricing.md            # Token rate card & cost_usd formulas
        ├── prompt-audit.md       # Pre-migration prompt & config audit
        └── cost-optimization.md  # Caching & no-eval cost checklist
    ```

* **3. Distribute Across Agent Environments:**
  * **Global Engineer Install (Antigravity / Jetski):** Install once into `~/.gemini/config/skills/gemini-eval/` (or symlink via git) so the skill is automatically discovered across all customer workspaces on the engineer's machine.
  * **Team / Customer Repo Distribution:** Publish to a shared Git repository so any engineer can install it in one command (`git clone` into `~/.gemini/config/skills/gemini-eval/` or `.agent/skills/gemini-eval/`).

* **4. Standardized Customer Delivery Workflow:**
  * **Build:** Point Jetski at the customer's codebase and dataset $\rightarrow$ generates `run-eval.py` from `runner-scaffold.py` with stratified `train`/`test` splits and calibrated graders.
  * **Climb:** Run autonomous quality or cost hill-climbing $\rightarrow$ logs auditable per-round diffs (`vN/change.patch`), token/cost telemetry (`results.jsonl`), and full transcripts (`traces/`).
  * **Hand Off:** Run `build-report-lite.py` to hand the customer a single self-contained `report.html`, `narrative.md`, and clean git patches ready for production PR review.
