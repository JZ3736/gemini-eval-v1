# `gemini-eval` Playbook - Under Review (MVP)

A coding-agent-driven, reproducible evaluation and hill-climbing playbook for Gemini model migrations, prompt optimization, and cost/latency tuning.

> **Status (MVP):** This playbook is currently an **MVP (Minimum Viable Product)**—more iterations and refinements are expected as we test it across real-world customer engagements and incorporate field feedback.

* **1. Purpose & How It Was Built:**
  * **Eliminate Ad-Hoc Eval Improvisation:** Prompting a coding agent without a playbook causes it to invent a new eval method each time, risking silent flaws like biased grading or prompt overfitting. `gemini-eval` gives Jetski a standardized, two-phase methodology—dataset audits, unbiased grading, locked `train`/`test` splits, and single-lever hill-climbing—to produce accurate, repeatable customer deliverables (`report.html`, `narrative.md`, and `change.patch`).
  * **Derived from `anthropic-eval`, Tailored for Gemini & Jetski:** Adapted directly from Anthropic's [`anthropic-eval` repo](https://github.com/anthropics/skills/tree/main/skills/claude-api/shared/evals) (introduced in the blog post [*Automating Eval Design and Hillclimbing*](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)), preserving 100% of its evaluation science while porting the Node.js runner/reporter to zero-dependency **Python** ([`report/runner-scaffold.py`](./report/runner-scaffold.py), [`report/build-report-lite.py`](./report/build-report-lite.py)) wired to the `google-genai` SDK, Jetski's native tools (isolated subagents, background runs, sign-off gates), and Gemini-specific optimization levers (`thinking_level` × model tier staircase walk, `response_schema`, context caching diagnostics, and legacy prompt-cruft audits—with `temperature` ignored and never tweaked as a hill-climbing lever on Gemini 3.5+ and Gemini 4; see [`references/diff.md`](./references/diff.md)).

* **2. Best-Suited Use Cases, Scenarios & Benefits:**
  * **Target Scenarios:** **(a) Model Upgrades** (Older Gemini $\rightarrow$ Newer Gemini to drive stickiness across accuracy, cost, and latency) and **(b) Competitive Displacement** (Non-Gemini $\rightarrow$ Gemini, while establishing objective thought leadership on Google Cloud's Agent Platform).
  * **Where It Fits vs. QIL (Fast Long-Tail Wedge):** While **QIL** serves high-stakes strategic engagements with strict onboarding criteria and heavy mutual engineering investment, `gemini-eval` provides a fast, lightweight field motion for **any customer who can benefit from eval help**. Customers often hold preconceived notions in favor of their incumbent model or fear regressions from upgrading—making them reluctant to invest engineering effort upfront. This playbook delivers quick, directional proof on their own cases that Gemini is better and cheaper, plus exact code diffs (`change.patch`), enticing them into deeper production validation and adoption.

* **3. Required Artifacts (Minimum-Viable Dataset vs. Ideal Setup):**
  * **Why a Minimum-Viable Dataset:** In practice, customers rarely share proprietary harness code, often lack human-verified golden datasets, and hesitate to invest engineering time before seeing initial proof.
  * **Minimum-Viable Dataset (`50–100+` cases for one scoped flow — *"One flow, one eval"*):**
    * *All Evals:* `system_instruction`, model parameters config (`temperature`, `thinking_level`/`thinking_budget`, `response_schema`, `max_output_tokens`), production inputs (`prompt` or multi-turn `messages[]`), baseline model outputs (used for blind A/B comparison, never as ground truth), and relevant `skill.md` files.
    * *Agent Evals Only (No Customer Harness Required):* Tool schemas/declarations and recorded agent trajectories (multi-step tool call arguments, tool outputs, and intermediate steps).
  * **Ideal Setup (Optional):** Live application entry point / harness in a staging sandbox, human-verified golden dataset, domain rubrics, and (for multi-step coding agents) repo snapshots + test commands (`pytest`).

* **4. Suited Scenarios & Fidelity Boundaries (Minimum-Viable vs. Ideal):**
  * **Minimum-Viable Dataset (Offline Trace Replay):**
    * *High End-to-End Fidelity:* Single-turn model evals and multi-turn agents whose tool calls exist in the recorded trace (even if called in a different order, in parallel, or via a valid shortcut). Open-ended quality is graded via blind pairwise A/B judging paired with a human-calibrated rubric drafted from `system_instruction`/`skill.md`.
    * *Directional End-to-End Signal (Turn-Level Accuracy):* Multi-turn flows where Gemini's actions diverge and change downstream inputs not captured in static traces—such as unrecorded tool calls, new RAG/search/SQL queries, live coding `edit → test` loops, or shifted multi-turn user replies. (Also cannot catch silent domain errors shared by both models or customer wrapper/proxy bugs.)
  * **Ideal Setup (Live Entry Point + Golden Data):** Delivers full production fidelity across live multi-turn tool branches, code-test execution loops, deterministic environment end states, warm cache hit rates, and wrapper/proxy plumbing (`thought_signature`, streaming, retries).

* **5. How to Get Started:**
  * **1. Set Up Your Workspace:** Clone `gemini-eval` (`git clone <repo-url> gemini-eval`) alongside a separate customer data folder (`customer-data/`) containing the scoped flow's artifacts.
  * **2. Kick Off Phase 1 (Dataset Audit, 5-Case Pilot & Baseline Eval):** Prompt Jetski with the target flow, migration pair, and goal/guardrail *(plus the PII pseudonymization recipe if needed)*. Approve **Gate 1** (input dataset & locked 60/40 `train`/`test` split) and **Gate 2** (grader & 5 pilot grades) to run the full baseline comparing the customer's current model vs. Gemini as-is (`v1`).
  * **3. Run Phase 2 (Failure-Driven Hill-Climbing, `v2` $\rightarrow$ `vN`):** If further tuning is needed, approve **Gate 3** (hill-climbing plan). Jetski's data-isolated subagent diagnoses `train` failures and tests one lever per round (Config/Prompt Hygiene $\rightarrow$ Context Caching $\rightarrow$ Model × `thinking_level` Walk $\rightarrow$ Prompt/`skill.md` Tuning $\rightarrow$ Tool Optimization), keeping only changes that beat the noise floor on unseen `test` until plateau (3 flat rounds).
  * **4. Share Final Deliverables:** Hand off the self-contained **`report.html`**, executive summary (**`narrative.md`**), and PR-ready **`change.patch`** (`[REQUIRED]` / `[TUNE]`), and guide the customer to validate the winning patch in staging.

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
  * [`references/prompt-audit.md`](./references/prompt-audit.md) — **Fills the pre-migration prompt & config audit gap:** Public migration docs cover SDK/API syntax changes but not prompt-behavior shifts. Provides the 5-part prompt-cruft audit (removing legacy step-by-step rituals, redundant tool checks, and heavy-handed `IMPORTANT!` caps that cause over-refusals or token bloat on `gemini-3.8-flash` / `gemini-4-pro`) and `GenerateContentConfig` normalization (ignoring/stripping `temperature` on Gemini 3.5+ and Gemini 4 so it is never tweaked as a hill-climbing lever, and normalizing `thinking_level` vs. `thinking_budget`).
  * [`references/cost-optimization.md`](./references/cost-optimization.md) — **Fills the operational cost-checklist & cache-debugging gap:** Public docs show how to call caching/batch APIs but not how to prioritize levers or debug silent cache misses. Provides the 7-step no-eval cost reduction order and context-caching invalidation diagnostics (prefix dynamic-token leaks, mid-session `thinking_config` key changes).
  * [`references/diff.md`](./references/diff.md) — **Fills the framework conversion traceability gap:** Documents the exact architectural, tool, schema, and Python runner mappings from the original Anthropic eval template to `gemini-eval`.

---

## Next Steps in Consideration

Right now, engineers clone `gemini-eval` directly into their workspace as an MVP. As we iterate, the following next steps are in consideration to scale adoption and continuous improvement:

* **1. Package as a Skill:**
  * Add a root `SKILL.md` entrypoint with YAML frontmatter (`name: gemini-eval`, `description: ...`) that points Jetski to the playbooks (`.md`) and Python scripts (`report/*.py`) inside this folder.
  * Allow engineers to install it once globally (e.g., `~/.gemini/config/skills/gemini-eval/`) so Jetski automatically detects and activates `gemini-eval` across all customer workspaces without cloning it each time.
* **2. Package as a Plugin:**
  * Bundle the `gemini-eval` skill, reference guides (`references/`), runner/report scripts (`report/`), and optional workspace rules or hooks into a single versioned **plugin** (`plugin.json`).
  * Enable one-click or single-command installation, version updates, and team-wide distribution so field engineers always run the latest standardized playbook and pricing/model tables.
* **3. How to Capture Usage & Field Feedback:**
  * **Automated Post-Run Retrospective:** Have Jetski prompt the engineer for a quick 1-minute reflection at the end of Phase 1 / Phase 2 (or auto-generate a `feedback.json` / retrospective snippet alongside `narrative.md`) capturing what worked, where friction occurred, and which optimization levers delivered the biggest win.
  * **Opt-In Usage & Outcome Telemetry:** Track lightweight, anonymized run metadata (migration pair, flow type, number of hill-climb rounds, winning lever, and baseline-to-final score/cost delta—with zero customer PII) or provide a one-click feedback link/issue template inside `report.html` to feed real-world learnings directly back into future playbook iterations.
