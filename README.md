# `gemini-eval` Framework

A structured, reproducible evaluation and hill-climbing framework for Gemini model migrations, prompt optimization, and cost/latency tuning.

* **How `gemini-eval` was built:** Adapted directly from the [`anthropic-eval`](../anthropic-eval) framework ([`anthropics/skills/skills/claude-api/shared/evals`](https://github.com/anthropics/skills/tree/main/skills/claude-api/shared/evals)), preserving 100% of its evaluation science, methodologies, and directory/artifact structure while tailoring it for **Antigravity / Jetski** and the **Gemini ecosystem** (see [`references/diff.md`](./references/diff.md) for the full conversion map):
  * **Antigravity / Jetski Native Tooling:** Replaced Claude Code tool conventions with Jetski's native tools (`ask_question`, background `run_command` with reactive wakeup, `invoke_subagent` for isolated `train`-only round analysis, and `.antigravity/hillclimb/<flow>/` state paths).
  * **Python & `google-genai` SDK Native:** Ported the Node.js (`.mjs`) runner scaffold and HTML report bundler to zero-dependency **Python** ([`report/runner-scaffold.py`](./report/runner-scaffold.py), [`report/build-report-lite.py`](./report/build-report-lite.py)) wired to the Google GenAI SDK (`google-genai`), Gemini model families (`gemini-4-pro`, `gemini-3.8-flash`, `gemini-2.5-*`), and Gemini API parameters (`thinking_config` / `thinking_level`, `response_schema`, `finishReason == "MAX_TOKENS"`, `thoughtsTokenCount`, and `cachedContentTokenCount`).

## Why Use `gemini-eval` Instead of Ad-Hoc Throwaway Eval Scripts in Jetski?

* **Prevents Overfitting (Strict Train/Test Isolation):**
  * **`gemini-eval`:** Enforces a stratified `train` / `test` split (e.g., 60/40) at the runner level ([`report/runner-scaffold.py`](./report/runner-scaffold.py) and [`example-migration/run-eval.py`](./example-migration/run-eval.py)). Jetski only inspects `train` failures when iterating on prompts or model configs, keeping `test` strictly held-out.
  * **Throwaway Code:** Usually evaluates and inspects all cases together, causing the agent to tune prompts to pass specific test cases (memorizing the test set).

* **Eliminates Judge Bias (Blind Pairwise & Anti-Self-Bias):**
  * **`gemini-eval`:** Randomizes candidate order (`Response A` vs. `Response B`) during pairwise judging so the judge cannot tell which output is `baseline` vs. `v1`, and enforces an anti-self-bias rule (never using the model-under-test as its own judge).
  * **Throwaway Code:** Often grades outputs in the same context window or passes unblinded labels, introducing position bias and self-preference bias.

* **Statistical Rigor & Noise-Floor Math:**
  * **`gemini-eval`:** Automatically computes 95% confidence intervals (`± CI`), multi-rep variance (`--reps`), and per-category agreement matrices across runs in [`report/runner-scaffold.py`](./report/runner-scaffold.py) to separate real quality gains from LLM sampling noise.
  * **Throwaway Code:** Relies on single-run point averages without confidence intervals, leading to chasing random variance during hill-climbing.

* **Layered Deterministic Code Graders + Calibrated LLM Judge:**
  * **`gemini-eval`:** Combines hard programmatic gates (JSON schema validation, truncation detection via `finishReason == "MAX_TOKENS"`, field compliance rules, and bipartite item matching) with structured LLM rubric/pairwise judges ([`build-eval.md`](./build-eval.md)).
  * **Throwaway Code:** Ad-hoc scripts frequently miss edge cases like silent output truncations, ungrounded quotes, or subtle schema drift.

* **Context Window Hygiene & Scalable Execution:**
  * **`gemini-eval`:** Runs model and judge calls concurrently in Python (`run-eval.py`), persists standardized artifacts (`results.jsonl`, `errors.jsonl`, and per-case `traces/*.json` per [`report/SCHEMA.md`](./report/SCHEMA.md)), and spawns isolated analyzer subagents only on failing `train` traces ([`eval-hillclimb.md`](./eval-hillclimb.md)).
  * **Throwaway Code:** Stuffing large datasets and transcripts directly into an agent session bloats the context window, degrades reasoning quality, and cannot scale to dozens of long-context cases.

* **Accurate Telemetry, Cost Separation & Visual Reporting:**
  * **`gemini-eval`:** Tracks exact API token usage (`promptTokenCount`, `candidatesTokenCount`, `thoughtsTokenCount`), latency, and separates pure production model cost from evaluation judge cost—compiling every round (`baseline` $\rightarrow$ `v1` $\rightarrow$ `v2`) into [`trajectory/scores.tsv`](./report/SCHEMA.md) and a self-contained [`report.html`](./report/build-report-lite.py) via [`report/build-report-lite.py`](./report/build-report-lite.py).
  * **Throwaway Code:** Produces inconsistent console logs that cannot be compared across hill-climb iterations or shared as auditable migration reports.

---

## Core Components

* **Playbooks:**
  * [`build-eval.md`](./build-eval.md) — End-to-end guide for designing datasets, deterministic graders, LLM judges, and building `run-eval.py`.
  * [`eval-hillclimb.md`](./eval-hillclimb.md) — Iterative quality hill-climbing workflow on `train` while guarding against `test` regression.
    * **Pre-Flight Calibration:** Establishes the baseline noise floor (`± CI` half-width across `n × reps`), headroom, and harness integrity (`--approve-harness`) before round 1.
    * **Isolated Analyzer Subagent (`analyze` $\rightarrow$ `apply` $\rightarrow$ `run` $\rightarrow$ `record`):** Spawns a fresh analyzer subagent each round that reads *only* `train` failure traces (`traces/<id>_rep<k>.json`) while the main session sees only aggregate scores—preventing `test` data leakage.
    * **Single-Hypothesis Root Fixes & De-Fluffing:** Proposes one generalizable behavioral fix per round (prompt, tool schema, `thinking_config`, or code) sized to clear the noise floor, strips non-operational prompt fluff, and records a reversible `vN/change.patch`.
    * **Plateau & Guardrail Stopping Rules:** Continues until the primary metric plateaus for $K \ge 3$ rounds or any guardrail metric regresses outside noise; evaluates the final winner on the held-out `test` split.
  * [`cost-hillclimb.md`](./cost-hillclimb.md) — Ordered optimization search to minimize cost/latency while holding quality within noise of baseline:
    * **Step 0 — Caching Health Verification:** Audits implicit/explicit context caching (`cachedContentTokenCount`) before and after every lever change so cache invalidation isn't mistaken for model cost.
    * **Step 1 — Legacy Prompt & Config Audit:** Strips dated prompt scaffolding and legacy parameters that inflate output/thinking tokens or mis-rank newer Gemini models (`gemini-3.8-flash`, `gemini-4-pro`).
    * **Step 2 — Model × Thinking/Effort Staircase Walk:** Instead of sweeping a full factorial grid, enters at the top cost-plausible tier at `LOW` thinking/effort; steps *down* a model tier on pass, *right* (higher effort) on fail, and prunes cells projected above the incumbent's cost $c^*$.
    * **Step 3 & 4 — Frozen-Model Prompt Climb & Down-Left Re-Probe:** Runs prompt hill-climbing on the winning model, then re-probes one cell down-left (one tier cheaper or one thinking notch lower) since cleaner prompts often unlock cheaper model tiers.
    * **Step 5 — Pre-Registered Joint Confirm (`n >= 3`):** Validates the final `(model, prompt, thinking_config)` tuple across $n \ge 3$ fresh runs against three pre-registered adoption gates: **Quality Band**, **Cost Margin**, and **Verified Mechanism**.
  * [`eval-audit.md`](./eval-audit.md) — Auditing existing evaluation suites for data leakage, judge bias, and grader gaps.
* **Python Runner & Reporting Engine:**
  * *Why pre-built executables are needed:* Markdown instructions alone leave plumbing (async concurrency, retry logic, CI math, artifact schemas, and HTML bundling) up to the LLM to reinvent every session—wasting tokens and introducing bugs. Pre-built Python executables lock down the deterministic infrastructure so Jetski only writes the task-specific model call and grading logic (`TODO` slots).
  * [`report/runner-scaffold.py`](./report/runner-scaffold.py) — Reusable Python evaluation harness (`run-eval.py` template).
    * **Benefits:** Guarantees identical CLI flags (`--round`, `--split`, `--reps`, `--case`), parallel worker execution, served-model identity checks, truncation detection, 95% confidence interval (`± CI`) math, and append-only `trajectory/scores.tsv` logging without rewriting boilerplate.
  * [`report/build-report-lite.py`](./report/build-report-lite.py) — Zero-dependency Python HTML bundler that compiles `metrics.md`, `narrative.md`, `scores.tsv`, and `traces/` into a single self-contained `report.html`.
    * **Benefits:** Eliminates fragile custom plotting scripts; produces a standardized, interactive side-by-side trace viewer and hill-climb trajectory dashboard in one command.
  * [`report/SCHEMA.md`](./report/SCHEMA.md) — Strict contract for `results.jsonl`, `errors.jsonl`, `traces/*.json`, and `scores.tsv`.
    * **Benefits:** Ensures the runner (`run-eval.py`), analyzer subagents, and report bundler (`build-report-lite.py`) interoperate seamlessly across every round.
* **Reference Example:**
  * [`example-migration/run-eval.py`](./example-migration/run-eval.py) — Complete reference implementation in Python showing how a flow plugs into `runner-scaffold.py`.

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
