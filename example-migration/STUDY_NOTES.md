# Anthropic Eval Framework — Study Notes & Q&A

This document compiles all the questions, answers, and architectural explanations from our study of the Anthropic Eval Framework (`/Applications/antigravity/anthropic-eval/`).

---

## Overview: How the Anthropic Eval Framework Works

The framework separates **methodology guides (`.md`)** from **execution and reporting scripts (`report/*.mjs`)**:

1. **[build-eval.md](../build-eval.md)** *(Phase 1 — Build the Eval)*:
   - **Step 0–1 (Inputs)**: Define a single flow and create a dataset (`id`, `tags`, `prompt`, `expected`). Split cases into `train` (cases you inspect while iterating on prompts) and `test` (held-out cases used to verify the final result).
   - **Step 2 (Grading)**: Pick the simplest grader that measures what matters (`pass`, sub-metrics, plus side-channel perf metrics like latency and tokens).
   - **Step 3 (Runner & Schema)**: Write per-case outputs to `<flow>/<variant>/results.jsonl`, full transcripts to `<flow>/<variant>/traces/<id>_rep<k>.json`, and any API/plumbing failures to `errors.jsonl` (so API errors are never scored as `0` model failures).
2. **[eval-audit.md](../eval-audit.md)** *(Quality & Hygiene Audit)*:
   - Checklist ensuring ground-truth labels aren't biased toward the old model, response `model` matches the requested model, and retries/timeouts are tracked cleanly.
3. **[eval-hillclimb.md](../eval-hillclimb.md)** & **[cost-hillclimb.md](../cost-hillclimb.md)** *(Phase 2 — Iterative Migration / Optimization)*:
   - Run `baseline` (old model) $\rightarrow$ `v1` (new model, unchanged prompt) $\rightarrow$ inspect `train` failures $\rightarrow$ `v2` (new model + tuned prompt) $\rightarrow$ compare held-out `test` split scores.
4. **[report/runner-scaffold.mjs](../report/runner-scaffold.mjs)** & **[report/build-report-lite.mjs](../report/build-report-lite.mjs)**:
   - `runner-scaffold.mjs` provides the CLI (`--flow`, `--variant`, `--model`, `--reps`, `--approve-harness`), crash-safe resume, and file writing. You only fill in `loadCases()`, `runCase()`, and `gradeCase()`.
   - `build-report-lite.mjs` reads the flow directory and generates a static HTML report (`report.html`) and `trajectory/scores.tsv`.

---

## Q1: Does `cases.json` represent classifications done by the existing older model, or human-annotated verified golden data?

### Answer
The `expected` field in [cases.json](./cases.json) represents **human-annotated (or human-verified) golden ground-truth data**—**not** the outputs of the older model.

### Why this matters in the Anthropic Eval Methodology
In [eval-audit.md](../eval-audit.md) (§1, *"Where did the ground truth come from?"*) and [build-eval.md](../build-eval.md) (Step 1), the framework specifically warns against using the older model's outputs as `expected` ground truth during a model migration:

> *"If the expected outputs are a model's outputs, reference-match scoring rewards **imitating that model**, not being right; this is worst in a migration, where gold derived from the incumbent makes the incumbent look best by construction and penalises a successor for every stylistic difference... Never use model A's outputs as gold when the question is A vs B."*

### Where the older model's outputs actually live
- **Human-verified Ground Truth**: Lives in [cases.json](./cases.json) under `expected` (which is why the older `baseline` model only scores `0.500`—it gets fooled by emotional traps like `ticket_02_billing_angry`).
- **Older Model (`baseline`) Outputs**: When you run `--variant baseline`, the runner saves the older model's actual responses to:
  1. [flow/baseline/results.jsonl](./flow/baseline/results.jsonl) and [flow/baseline/traces/](./flow/baseline/traces/) (for scoring against the human ground truth).
  2. [flow/baseline/ref/](./flow/baseline/ref/) (frozen baseline outputs on disk, which `runner-scaffold.mjs` automatically passes as the `ref` parameter to `gradeCase(input, run, ref, ctx)` if you ever want to do pairwise A/B judging between the old model's response and the new model's response).

---

## Q2: Who picks the grader and measurable metrics in Step 2? And who decides on the Step 3 output schema?

> **Question Details:**
> - Who picks the grader measurable metrics? Does Claude Code pick by itself based on the input golden dataset along with `.md` files, or does the user identify it?
> - Who decides on Step 3 output schema (`results.jsonl`, `traces/`, `errors.jsonl`)? Does Claude Code do it based on the `.md` file, or does the user explicitly provide it?

### Answer

#### Part A — Step 2 (Grader & Measurable Metrics): **Agent Proposes $\rightarrow$ User Approves**
Neither side does it completely alone—[build-eval.md](../build-eval.md) enforces a **"recommendation-forward interview" with a mandatory human sign-off**:

1. **Claude Code proposes the defaults based on your code + dataset**:
   - The agent reads your app's output shape and your golden dataset (`cases.json`), then follows the rules in [build-eval.md (Step 2)](../build-eval.md) to recommend:
     - **Quality metrics & grader type**: e.g., Programmatic check if the output is structured JSON/labels, Pairwise judge for open-ended model migrations, or Pointwise LLM rubric.
     - **Side-channel (`perf_fields`) menu**: The agent presents a checklist (cost, latency, output length, tool calls, `max_tokens` truncation) and asks which ones matter to your product.
2. **The User selects and gives mandatory sign-off**:
   - You pick/override the metrics from the agent's multiple-choice prompt.
   - Then, before doing a full eval run, the agent runs the grader on **~5 pilot examples**, generates `report.html`, and **must pause** for your explicit approval:
     > *"Here are five graded examples in `report.html` - open each one. Would you have scored any of these differently?"*

#### Part B — Step 3 (Output Schema: `results.jsonl`, `traces/`, `errors.jsonl`): **Decided Automatically by the Framework / Agent**
**You (the user) do NOT need to provide or design the Step 3 output schema.**

- **Fixed by the `.md` files and scaffold**: The schema for `results.jsonl`, `traces/<id>_rep<k>.json`, `errors.jsonl`, and `_state.json` is a **framework contract** defined in [report/SCHEMA.md](../report/SCHEMA.md) and [build-eval.md (Step 3)](../build-eval.md) so that [build-report-lite.mjs](../report/build-report-lite.mjs) can automatically build `report.html` and `trajectory/scores.tsv`.
- **Pre-built in `runner-scaffold.mjs`**: When Claude Code copies [report/runner-scaffold.mjs](../report/runner-scaffold.mjs), all the file formatting for `results.jsonl`, `traces/`, and `errors.jsonl` is already written in the bottom half of that script.
- **What if you already have your own eval script?** Per [build-eval.md](../build-eval.md), if you already have an existing eval script with a custom output format, Claude Code keeps your layout and writes a thin adapter so it still works with `report.html` without forcing you to rewrite your existing script.

| Decision | Who Decides? | Where It Comes From |
|---|---|---|
| **Input test cases (`cases.json`)** | Agent drafts / pulls from logs $\rightarrow$ **User must sign off** | `build-eval.md` (Step 1) |
| **Grader logic & metrics (`pass`, `latency_s`, etc.)** | Agent recommends based on dataset/app $\rightarrow$ **User picks & signs off on 5-case pilot** | `build-eval.md` (Step 2) |
| **Output file schema (`results.jsonl`, `traces/`, `errors.jsonl`)** | **Framework / Agent automatically** (user never has to specify this) | `report/SCHEMA.md` & `runner-scaffold.mjs` |

---

## Q3: What does `runner-scaffold.mjs` do? Why do we need a runner executable file to begin with? Can the user rely on Claude Code to generate the runner dynamically instead?

### Answer

#### 1. Why do we need a runner executable file to begin with?
Why can't Claude Code just call the model inside the chat session and grade the answers in its own context window?
1. **Deterministic & Isolated Execution**: When evaluating 20–100 cases across multiple reps (`--reps 3`) and multiple variants (`baseline`, `v1`, `v2`, ...), an executable script runs all cases concurrently via a worker pool (`--concurrency 4`) with exact API parameters, rather than burning your Claude Code agent's context window.
2. **Reproducibility across rounds**: During hill-climbing ([eval-hillclimb.md](../eval-hillclimb.md)), you want the **exact same test harness and grader** to run on Round 1, Round 2, and Round 10 so scores are apples-to-apples.
3. **Background Execution**: Eval passes can take minutes to hours. `eval-hillclimb.md` launches the runner script in the background (`run_in_background: true`) so your chat session stays free.
4. **Preventing Context Contamination (Data Leakage)**: Per [report/SCHEMA.md](../report/SCHEMA.md), the agent tuning your prompt must **never** see the held-out `test` split transcripts. Having a script run the cases and write to disk keeps `test` transcripts out of the agent's context.

#### 2. What does `runner-scaffold.mjs` actually do?
[report/runner-scaffold.mjs](../report/runner-scaffold.mjs) is an **80%-complete template**. It leaves 3 functions blank for your specific app:
- `loadCases()` — how to load your test inputs
- `runCase(input, ctx)` — how to call your app/endpoint
- `gradeCase(input, run, ref, ctx)` — how to score one output

Everything else (lines 178–603) is **production eval plumbing** that people usually forget when writing an eval script from scratch:
- **Crash-Safe Incremental Resume**: Writes each row to `results.jsonl` the instant it finishes. If case 48/50 crashes, re-running the command skips the 47 finished cases and only runs the remaining 3.
- **Plumbing Errors vs. Model Failures**: If an API call times out or hits a 500 error, it writes to `errors.jsonl` instead of scoring a `0` in `results.jsonl` (which would corrupt your model accuracy).
- **Jittered Exponential Backoff & Wall-Clock Timeouts**: Automatically retries `429`/`529` rate limits with jitter and enforces a hard per-case timeout (`--timeout-s`).
- **Served-Model Assertion**: Verifies the response's `model` field matches `--model` so silent provider fallbacks don't invalidate your migration test.
- **Harness Integrity Gate (`--approve-harness`)**: Computes a SHA-256 hash of the runner and dataset in `_state.json` so an automated hill-climb agent cannot secretly edit the grading rules mid-run to "cheat" a higher score.
- **Security Hardening**: Blocks symlink/hardlink attacks (`O_NOFOLLOW`) and strips terminal escape sequences in case untrusted prompt data tries to inject paths or commands.

#### 3. Can the user rely on Claude Code to generate the runner dynamically instead of using `runner-scaffold.mjs`?
**Yes!** [build-eval.md](../build-eval.md) explicitly supports dynamic generation in your project's native language (e.g., Python) when appropriate:

- **What `build-eval.md` (lines 7 & 146) says**:
  > *"The runner is usually a plain Python script; it could be a CLI, a pytest suite, or whatever fits their stack... Run the scaffold with `node` or `bun`, whichever is on PATH. If neither is installed (common in Python-only projects), don't ask the user to install one: **write the runner in the project's language against the contract above** (`results.jsonl` rows, `traces/<id>_rep<k>.json`, `errors.jsonl`, `baseline` / `v<N>` directories) and the field reference in `shared/evals/report/SCHEMA.md`, keeping the scaffold's properties..."*

- **Why the skill includes `runner-scaffold.mjs` anyway**:
  1. **Speed & Token Savings**: When Node/Bun is available, copying `runner-scaffold.mjs` and having Claude Code only generate the ~30 lines of `loadCases` / `runCase` / `gradeCase` takes seconds instead of generating 500+ lines of boilerplate from scratch.
  2. **Zero Forgotten Edge Cases**: When an LLM writes a runner dynamically from scratch, it often forgets subtle safeguards (like separating `errors.jsonl` from `results.jsonl`, `O_NOFOLLOW` symlink checks, or `--approve-harness` hashing). `runner-scaffold.mjs` guarantees all those safeguards are present out of the box—or serves as the exact reference blueprint when Claude Code dynamically writes a Python runner.

---

## Q4: Mental Model Check — Is `anthropic-eval/` essentially agent instructions (`.md` playbooks) + a runner template (`runner-scaffold.mjs`) + a report builder (`build-report-lite.mjs`)?

> **Question Details:**
> The `anthropic-eval` folder/framework consists of rules/`.md` files explaining how an eval should be built, run, graded, and reported—more like instructions telling Claude Code how to generate all actions dynamically while asking the user to provide info along the way—and a templated `runner-scaffold.mjs` file used to build the runner executable, along with a build-report executable. Correct?

### Answer
**Yes — 99% spot-on!**

Here is the exact mental model of the three components:

1. **The `.md` files ([build-eval.md](../build-eval.md), [eval-audit.md](../eval-audit.md), [eval-hillclimb.md](../eval-hillclimb.md), [cost-hillclimb.md](../cost-hillclimb.md), [report/SCHEMA.md](../report/SCHEMA.md)) are "agent instructions / playbooks"**:
   - Instead of being a rigid software library you import, they instruct Claude Code on how to dynamically inspect your codebase, interview you at key checkpoints (with recommended defaults and mandatory sign-offs on inputs and grading), audit the eval for flaws, and run optimization loops.
2. **[report/runner-scaffold.mjs](../report/runner-scaffold.mjs) is a customizable code template**:
   - Claude Code copies it into your project and fills in the 3 app-specific functions (`loadCases`, `runCase`, `gradeCase`) while keeping all the built-in safety/resilience plumbing (`results.jsonl`, `errors.jsonl`, retries, timeouts, `--approve-harness`).
3. **One tiny distinction on [report/build-report-lite.mjs](../report/build-report-lite.mjs)**:
   - Unlike `runner-scaffold.mjs` (which is a **template** that gets edited per project), `build-report-lite.mjs` is a **ready-to-use executable CLI tool** that does **not** need to be edited or copied. Because every runner writes outputs in the same [report/SCHEMA.md](../report/SCHEMA.md) format, Claude Code simply runs `node build-report-lite.mjs <flow-dir>` as-is to generate `report.html` and `trajectory/scores.tsv`.

---

## Q5: Are there any external skills, `.md` files, or tools called to run this eval, or does the `anthropic-eval/` folder work atomically?

### Answer
**Short answer:** Yes, the `anthropic-eval/` folder **works 100% atomically** at runtime—it has zero external package dependencies. However, the `.md` guides do reference **3 sibling markdown docs** from the parent `skills/claude-api/` repository and **3 standard agent capabilities**.

#### 1. Runtime Execution: 100% Atomic & Zero Dependencies
- **[report/runner-scaffold.mjs](../report/runner-scaffold.mjs)** and **[report/build-report-lite.mjs](../report/build-report-lite.mjs)** only import built-in Node.js standard library modules (`node:fs`, `node:path`, `node:crypto`, `node:url`).
- No `npm install`, external CLI, or third-party eval library is needed to run an evaluation or generate `report.html` and `trajectory/scores.tsv`.
- *(Note: `build-eval.md` line 150 mentions an internal `build-report.mjs` "full viewer", but explicitly states: **"It is not extracted with this skill, so it is usually absent"** and automatically falls back to `build-report-lite.mjs`.)*

#### 2. Optional Sibling `.md` Files Referenced in the Text
Because this folder lives at `skills/claude-api/shared/evals/` in the `anthropics/skills` repo, the `.md` files mention three sibling reference files from the parent `skills/claude-api/` folder:
1. **`skills/claude-api/SKILL.md`** (referenced in `build-eval.md` lines 27, 116, 182): Contains the **Current Models token pricing table** (used when calculating dollar cost estimates) and **provider client snippets** (Anthropic API, Vertex AI, Bedrock, Foundry).
2. **`skills/claude-api/shared/model-migration.md`** (referenced in `eval-hillclimb.md` line 27): Checklist of breaking changes and behavioral differences between older and newer Claude models, which helps the agent propose smarter prompt edits during a model-migration hill-climb.
3. **`skills/claude-api/shared/cost-optimization.md`** (referenced in `eval-hillclimb.md` line 99): A general no-eval checklist for prompt caching and token reduction (whereas `cost-hillclimb.md`, which *is* already in `anthropic-eval/`, handles eval-driven cost optimization).

#### 3. Host Agent Tools Referenced by the `.md` Playbooks
When an AI coding assistant (like Claude Code or Antigravity) reads these `.md` files, the instructions assume the agent has 3 built-in agent tools:
1. **`AskUserQuestion`** (`build-eval.md` lines 9–11): Renders multiple-choice questions to the user (with `(Recommended)` first); falls back to plain chat questions if unavailable.
2. **`Bash`** (`eval-hillclimb.md` line 13): Runs `node run-eval.mjs` (optionally in the background) and `node build-report-lite.mjs`.
3. **`Agent` / Subagent** (`eval-hillclimb.md` line 13): Used in Step 4 of hill-climbing to spawn an isolated "analyzer subagent" to read `train` transcripts and propose prompt changes without filling up the main chat context.

---

## Q6: Customer Intake Guide — What is the bare minimum dataset to ask customers for (type, use case, volume, baseline, golden dataset)?

### Answer

#### 1. Scope: One Specific Flow (Not the Whole App)
Per [build-eval.md (Step 0)](../build-eval.md), ask the customer to pick **one single flow** to evaluate first (e.g., *just* the intent classifier, *just* the RAG summarizer, or *just* one agent workflow), plus:
- **The current system prompt + model ID** (and tool definitions, if any).
- **What one request carries besides text**: e.g., attached PDFs/images, user profile metadata, prior conversation history, or tool stubs.

#### 2. Volume of Data: How Many Examples?

| Goal | Bare Minimum Volume | Recommended Volume | Why (from `build-eval.md` line 54 & `eval-audit.md` §5) |
|---|---|---|---|
| **Synthesizing a dataset from scratch** | **3–5 real seed examples** + 1 sentence on what makes a case "hard" | 5–10 seed examples | Claude Code can synthesize the rest (`15–30` cases) from these seeds, and the customer just reviews/approves them. |
| **First-pass Model Migration Check** (Pass/Fail Go-Live Check) | **15–25 cases** | **30–50 cases** | Below 15 cases, a single flaky case swings the score by ~7%. |
| **Hill-Climbing / Prompt Tuning** (Iterating on prompts for the new model) | **25 cases × 2 reps** (or **50+ cases × 1 rep**) | **50–100 cases** (split into `train` and held-out `test`) | The statistical noise floor is $\approx \frac{1}{\sqrt{N \times \text{reps}}}$. At 25 cases × 2 reps, the noise floor is ~$\pm 14$ points. Splitting into `train` + `test` prevents overfitting prompts to the test set. |

#### 3. Type of Data by Use Case
1. **Simple Input/Output (Classification, Extraction, Summarization, Q&A)**:
   - **Inputs**: Raw user input strings (ideally sampled from production logs or recent support tickets/bug reports, anonymized if needed) covering **both positive and negative cases** (e.g., when to trigger vs. when *not* to trigger—see `eval-audit.md` lines 79–81).
2. **Tool-Calling / Agentic Workflows**:
   - **If read-only / deterministic**: Input prompt + access to a test/staging environment or fixture files.
   - **If tools have real-world side effects** (sending emails, writing to prod DBs) or live state changes: Per `build-eval.md` line 29, ask for **historical transcripts with canned tool results** so you can stub the tools and grade whether the new model makes the right tool calls and final response.
   - **If coding / file-editing agent**: A small set of reproducible repo states/fixtures + a programmatic test/check on the **end state** (not just the chat transcript—see `build-eval.md` line 80).

#### 4. Is a "Golden Dataset" (Human-Verified Ground Truth) Mandatory?
**No, it is NOT always mandatory—it depends on the task type** (`build-eval.md` lines 80–85):
- **When Ground Truth (`expected` labels) IS Used**: Constrained / Classification / Extraction tasks where you want an exact programmatic check (`new_output == expected_ground_truth`). Here, those 15–25 labels must be human-verified, not unverified dumps from the old model.
- **When Ground Truth is NOT Needed**: Open-ended generation tasks or when the customer only has `(input, old_model_output)` logs and wants zero human labeling effort (see Q7 below on **Pairwise Blind Judging**).

#### 5. Is a Baseline Mandatory?
- **For a Model Migration (`Old Model` $\rightarrow$ `New Model`)**: **Yes, a `baseline/` variant is mandatory** (`report/SCHEMA.md` line 129).
- **However, the customer does NOT need to pre-compute baseline scores before engaging you!** They only need to provide either:
  1. **Their current prompt + old model name** (so `run-eval.mjs --variant baseline` can run the old model and freeze its outputs automatically in `baseline/ref/`), **OR**
  2. **Saved production outputs from their old model** for those 15–50 inputs (which can be loaded directly as `baseline` and frozen in `baseline/ref/<id>` for pairwise comparison against the new model).

---

## Q7: For bare minimum, can we use just the existing old model's output instead of human-verified data? And is the Pairwise Blind Judge done automatically by Claude Code?

### Answer

#### Part A: Can we use just `(input, old_model_output)` with zero human verification?
**Yes — you CAN use just `(input, old_model_output)` with zero human-verified labels**, as long as you use **Grader Type #2: Pairwise Blind Judge (`baseline/ref/`)** instead of exact reference-match!

In fact, [build-eval.md (line 81)](../build-eval.md) and [runner-scaffold.mjs (lines 495–539)](../report/runner-scaffold.mjs) have built-in support specifically for this scenario:

1. **The Right Way (Zero Human Labels Needed): Pairwise Blind Judge (`baseline/ref/`)**
   - **Do NOT treat `old_model_output` as the "correct answer key."**
   - **Treat `old_model_output` as "Candidate A" and `new_model_output` as "Candidate B."**
   - **How it works**:
     1. **Freeze Old Model Outputs**: The old model's outputs are saved into `flow/baseline/ref/<id>` (and `baseline` rows get a neutral score of `win: 0.5`).
     2. **Run New Model (`v1`)**: The runner passes both `ref` (old model output) and `run.output` (new model output) into `gradeCase(input, run, ref, ctx)`.
     3. **Blind A/B Judge**: A judge model reads the input prompt, randomizes which response is A vs. B, and scores:
        - `1.0` if the **new model** is better
        - `0.5` if they are **tied / equivalent** (parity!)
        - `0.0` if the **new model is worse** (regression)
   - **Why this works**: If both models give the same answer $\rightarrow$ automatic `tie` (parity holds). If they **disagree** $\rightarrow$ the judge evaluates *which one actually followed the system prompt better*, rather than blindly assuming the old model was right!

2. **The Wrong Way: Exact-Match (`new_output == old_output`)**
   - Why does `eval-audit.md` (line 61) warn against setting `expected = old_model_output` and running a simple `new_output == expected` check?
   - Because `old_model_output == old_model_output` is **100% by definition**. If the old model was only 80% accurate in production, and the new smarter model is 95% accurate, a naive `new == old` check will falsely penalize the new model on the 15% of cases where the new model fixed the old model's mistakes!

---

#### Part B: Is the Pairwise Blind Judge done automatically by Claude Code, and where is user input needed?
**Yes — the mechanics are handled automatically by `runner-scaffold.mjs` and Claude Code following `build-eval.md`.** You do not write any of the freezing, randomization, or judge-calling code yourself.

##### 1. What Happens Automatically (Zero User Coding)
- **Freezing & Loading `baseline/ref/<id>` (Built into `runner-scaffold.mjs`)**:
  - In `report/runner-scaffold.mjs` (lines 534–539), when `--variant baseline` runs, the script **automatically** saves every baseline output to `flow/baseline/ref/<id>`.
  - In `report/runner-scaffold.mjs` (lines 495–505), when `--variant v1` runs, the script **automatically** reads `flow/baseline/ref/<id>` from disk and passes it into `gradeCase(input, run, ref, ctx)` as the `ref` argument.
- **Writing the Blind A/B Judge in `gradeCase()` (Done by Claude Code from `build-eval.md`)**:
  - Following `build-eval.md` (lines 81–82), Claude Code automatically generates the `gradeCase()` function that sets `win = 0.5` on `baseline` rows, randomizes Candidate A vs. Candidate B on every case, calls the Judge model with structured JSON output (`winner: "A" | "B" | "tie" | "both_bad"` + `explanation`), and records `judge_model` and `judge_usage`.

##### 2. Where and What User Input IS Needed (4 Quick Checkpoints)
Even though Claude Code writes all the code, `build-eval.md` requires Claude Code to pause and ask you at **4 checkpoints**:

| When | What Claude Code Asks You | What You (or the Customer) Provide |
|---|---|---|
| **Checkpoint 1: Step 1 (Data Origin)** (`build-eval.md:L45`) | *"Where did these expected/reference outputs come from — human-written, human-verified, or a model's outputs (which model)?"* | Tell Claude Code: **"They are unverified outputs from our old model (`<model-name>`)."** *(This is the trigger that tells Claude Code to use Pairwise Blind Judging instead of exact-match!)* |
| **Checkpoint 2: Step 1 Sign-Off (Inputs)** (`build-eval.md:L60`) | *"Here are the N inputs I'm proposing to use. Are these representative?"* | Skim the inputs table and reply **"Yes"** (or point out any bad/irrelevant rows to drop). |
| **Checkpoint 3: Step 2 (Judge Model & Criteria)** (`build-eval.md:L70, L82`) | Multiple-choice prompt asking: 1) Which side-channel metrics matter (latency, cost, tokens)? 2) Which Judge model to use (`Haiku`, `Sonnet`, or `Opus`)? 3) Is the drafted judge rubric accurate? | Click your choice for **Judge model** (e.g., `Sonnet` or `Opus`, making sure the judge isn't the exact same model being tested) and approve/tweak the 3–5 bullet rubric Claude Code drafted from your system prompt. |
| **Checkpoint 4: Step 2 Sign-Off (5-Case Pilot)** (`build-eval.md:L97`) | Claude Code runs 5 pilot cases, generates `report.html`, and asks: *"Here are 5 graded examples in `report.html`. Would you have scored any of these differently?"* | Open `report.html`, read the 5 judge explanations, and reply **"Yes, looks good"** (or tell Claude Code if the judge was too strict/lenient on one of the 5 cases so it can adjust the judge prompt before running all N cases). |

---

## Q8: If I have the bare-minimum data (system prompt, tool descriptions, and `(input, old_model_output)` test cases), what are the exact steps to start the eval and let Claude Code drive?

### Answer
You do **not** need to pre-format the customer's data into `cases.json` or write any code yourself. Here is the end-to-end workflow from the **User's perspective**:

#### Step 1: Drop the Raw Customer Files into a Folder
Create a folder for the customer's project (e.g., `/Applications/antigravity/anthropic-eval/customer-x/`) and drop their raw files inside in **whatever format they already have**:
- Their **system prompt & tool descriptions** (e.g., `prompt.txt`, `tools.json`, or their actual Python/TS source file).
- Their **raw test cases + old model outputs** (e.g., a `.csv`, `.xlsx`, `.json`, or `.jsonl` export from production logs).

#### Step 2: Make Sure Argolis / Vertex AI Auth is Active
In your terminal, make sure `gcloud` is authenticated so the runner (and LLM judge) can call Vertex AI Model Garden:
```bash
gcloud auth application-default login   # or gcloud auth login
export VERTEX_PROJECT_ID="your-argolis-project-id"
export VERTEX_REGION="us-east5"
```

#### Step 3: Send One Starter Prompt to Claude Code / Antigravity
You don't run the `.mjs` scripts manually—you just tell the agent to read `build-eval.md` and point it at your folder:
> *"Read `/Applications/antigravity/anthropic-eval/build-eval.md` (and `/Applications/antigravity/anthropic-eval/eval-audit.md`) and follow its exact workflow for the files in `/Applications/antigravity/anthropic-eval/customer-x/`.
> We are migrating from `<old-claude-model>` to `<new-claude-model>` on Vertex AI Model Garden (`$VERTEX_PROJECT_ID`, `$VERTEX_REGION`). The dataset contains production inputs and unverified outputs from the old model."*

#### Step 4: What Happens Next (Agent vs. User Checkpoints)
Once you send that prompt, **the agent does all the heavy lifting automatically** and only pauses at the checkpoints defined in `build-eval.md`:
1. **Agent automatically converts data & audits it** $\rightarrow$ **Your action (Checkpoint 1)**: Reply *"Yes, approved."*
2. **Agent proposes Pairwise Blind Judge + Side-Channel Metrics** $\rightarrow$ **Your action (Checkpoint 2)**: Click/confirm the judge model and drafted rubric.
3. **Agent generates `run-eval.mjs` from `runner-scaffold.mjs` & runs a 5-case Pilot** $\rightarrow$ **Your action (Checkpoint 3)**: Open `report.html`, check the 5 graded examples, and reply *"Looks good, run the full evaluation."*
4. **Agent runs the full evaluation (`baseline` vs. `v1`) & generates the final `report.html`**.
5. *(Optional)* **Step 5 — Hill-Climb to Fix Any Regressions**: Tell the agent: *"Now follow `/Applications/antigravity/anthropic-eval/eval-hillclimb.md` to tune the system prompt for `<new-claude-model>` and recover the score."*

---

## Q9: At Checkpoint 2 ("confirm the judge model and rubric"), does the customer have to provide a rubric? And what do `--approve-harness` and "approves the tool call" mean?

### Answer

#### 1. Do we have to ask the customer to provide a rubric as bare-minimum data?
**No!** You do **not** need to ask the customer to write a rubric.
- **Where the rubric comes from**: Claude Code **automatically generates the rubric** by reading the customer's **System Prompt** and **Tool Descriptions** (plus sampling a few of their `(input, old_model_output)` pairs).
- For example, if the customer's system prompt already says *"Respond in under 3 paragraphs, use only data from `search_kb`, and never guess account balances,"* Claude Code extracts those exact rules and turns them into a checklist rubric for the Pairwise Judge.
- At Checkpoint 2, Claude Code simply shows you the rubric it extracted and asks: *"Here is the rubric I derived from the system prompt—OK to use?"* You just click/say **Yes** (or add a rule if the customer mentioned a business goal that wasn't written in their old prompt).

#### 2. What is `--approve-harness` for, and what does "approves the tool call" mean?
This comes from how **Claude Code / Antigravity executes terminal commands** during an automated multi-round optimization loop ([eval-hillclimb.md:L13](../eval-hillclimb.md) & [runner-scaffold.mjs:L216-L237](../report/runner-scaffold.mjs)):

##### A. What does "approves the tool call" mean?
When an AI coding agent wants to run a shell command on your machine (using its `Bash` / `run_command` tool, like `node run-eval.mjs --flow flow --variant v1`), your IDE shows a permission prompt asking you to **Allow / Approve** that terminal command.
- When running 5–10 rounds of prompt tuning (`v1`, `v2`, `v3`...), users typically click **"Always allow `node run-eval.mjs ...` for this session"** so the agent can run all 10 rounds unattended.

##### B. Why `--approve-harness` exists (Anti-Cheating & Security Gate)
Once you tell the IDE *"Always allow `node run-eval.mjs` to run unattended,"* a risk appears:
- What if on Round 3, while trying to raise the score, the AI agent edits **`run-eval.mjs` (the grader)** or **`cases.json` (the test cases)** instead of editing `prompts.json`—making the grader pass everything to "cheat" a 100% score? (Or worse, what if a prompt-injection inside a customer's log tricks the agent into adding malicious code to `run-eval.mjs`?)
- Because `node run-eval.mjs` was already auto-allowed for the session, it would execute automatically without asking you!

**How `--approve-harness` solves this:**
1. On the very first run, you run (or approve) `node run-eval.mjs ... --approve-harness`.
2. `run-eval.mjs` computes a **SHA-256 hash** of itself (`run-eval.mjs`) and `cases.json`, and saves that hash in `flow/_state.json` (`"harness_sha": "2e3f7f7bd19c..."`).
3. On every subsequent round (`v1`, `v2`, `v3`), the agent runs `node run-eval.mjs` **without** `--approve-harness`.
4. Before calling any models, `run-eval.mjs` recalculates the SHA-256 hash of `run-eval.mjs` and `cases.json`:
   - If the agent only edited `prompts.json` (the system prompt) $\rightarrow$ **Hashes match!** The eval runs smoothly.
   - If the agent touched `run-eval.mjs` (the grader) or `cases.json` (the dataset) $\rightarrow$ **Hash mismatch!** The script immediately aborts (`exit 2`) with:
     > `harness changed since last approved run... Re-run with --approve-harness after reviewing the diff.`

In short: **`--approve-harness` locks the test and the grader** so that during automated prompt-tuning, only the prompt/model can change—never the test or the grading rules.

---

## Q10: What is the methodology used in `eval-hillclimb.md`? Does it only modify prompts, or what else? How many iterations does it run, and how does Claude Code handle it step by step?

### Answer

#### 1. What Levers Does Hill-Climbing Modify? (Not Just Prompts!)
Per [eval-hillclimb.md (Step 1, lines 66–82)](../eval-hillclimb.md), modifying the system prompt is only one of **5 levers** Claude Code can iterate on (you tell it which ones are in-bounds vs. off-limits before starting):
1. **System Prompts**: Adding missing rules, clarifying decision boundaries, or cutting contradictory/fluffy instructions.
2. **Skills / Instruction Files**: Editing `.md` files or few-shot examples the agent loads dynamically.
3. **Tool Descriptions & Schemas**: Rewriting tool docstrings or parameter descriptions so the new model knows *when* and *how* to call (or not call) a tool.
4. **Model Choice & API Parameters**: Changing the model tier (`Haiku` / `Sonnet` / `Opus`), `effort` (`low` / `medium` / `high`), extended `thinking` budgets, `max_tokens`, or prompt caching ([cost-hillclimb.md](../cost-hillclimb.md) walks a `model × effort` staircase automatically).
5. **Agent Loop / Application Code**: Modifying context assembly, routing logic, or writing a deterministic helper function/script instead of adding more prose to the prompt.

#### 2. How Many Iterations (Rounds) Does It Run?
Per [eval-hillclimb.md (Step 2, lines 88–97 & line 118)](../eval-hillclimb.md), a typical hill-climb plans for **~5 to 8 rounds max**, governed by the stopping rule you select at the start:
1. **Until Plateau *(Recommended default)***:
   - Runs autonomously until the target metric improves by less than the statistical noise floor for **$K \ge 3$ consecutive rounds** (or if a guardrail metric regresses).
   - If the score stalls for **2–3 rounds**, it triggers **Step 4.5 (Stall Categorization)** instead of blindly grinding more prompt edits.
2. **Fixed $N$ Rounds**: Runs $N$ rounds (e.g., 3, 5, or 8 rounds), then pauses to check in with you.
3. **One Round at a Time**: Proposes 1 change, runs `v1`, shows you the diff and score, and waits for your approval before trying `v2`.

#### 3. How Claude Code Executes Hill-Climbing Step by Step
The playbook uses a strict **Two-Agent Data-Isolation Architecture** so the agent cannot "cheat" or overfit to the test set:
- **Outer Agent (Main Session)**: Only ever reads **summary scores** (`scores.tsv`). It **never** opens any conversation transcripts.
- **Inner Analyzer Subagent (Fresh per Round)**: Spawned via the subagent tool each round and handed **only the `train` split transcripts**. It never sees the held-out `test` split.

##### Step-by-Step Execution Flow:
1. **Step 0 & 0.5 — Audit & Noise-Floor Check** (`lines 17–50`): Verifies the eval works and calculates the **noise floor** ($\approx \frac{1}{\sqrt{n \times \text{reps}}}$) so it doesn't chase random 2% fluctuations that are just noise.
2. **Step 1 & 2 — Goal, Scope Table & Budget Sign-Off** (`lines 53–121`): Asks you for the primary goal (e.g., *"Move to `<new-model>` and recover accuracy"*), builds a two-column **"Will Change" vs. "Won't Touch"** scope table, estimates total loop token cost, and waits for your **Yes**.
3. **Step 3 — Train/Test Split & Baseline** (`lines 124–220`): Splits `cases.json` randomly (stratified by `tags[0]`) into `train_ids` and `test_ids` in `_state.json`, runs `baseline` across all cases, and records the starting score.
4. **Step 4 — The Iterative Loop (`v1`, `v2`, `v3`...)** (`lines 223–276`):
   - **A. Analyze (via Subagent)**: Spawns a fresh **Analyzer Subagent** and passes *only* the `train` transcripts (`vN/traces/<train_id>_rep0.json`) and `train` scores. The subagent finds the single biggest root-cause failure pattern on `train` and proposes **one unified change**.
   - **B. Apply & Snapshot**: The main agent strips out any vague "fluff" (*"be careful"*, *"think step by step"*), applies the change, saves the rationale to `vN/change.md`, and saves the git diff to `vN/change.patch`.
   - **C. Run (in Background)**: Launches `node run-eval.mjs --variant vN` across **all** cases (`train` + `test`).
   - **D. Record, Decide & Keep/Revert**:
     - Rebuilds `report.html`, `trajectory/scores.tsv`, and `narrative.md`.
     - If `train` **and** `test` both improve $\rightarrow$ **Keep** as the new `best` variant!
     - If `train` goes up but `test` stays flat/drops $\rightarrow$ **Overfit!** Revert the change and try a different angle.
     - If `train` regresses $\rightarrow$ **Revert immediately** before the next round.
5. **Step 4.5 — When the Loop Stalls (2–3 Flat Rounds)** (`lines 279–301`): Buckets remaining `train` failures into 5 root causes (**Artifact gap**, **Grader bug/disagreement**, **Harness/infra error**, **Structural/routing issue**, or **Variance**) and fixes the actual bottleneck (or runs a one-shot "breadth pass" for long-tail edge cases).
6. **Step 5 — Final Report & Handover** (`lines 304–319`): Leaves your codebase at the winning `vN` state, generates the final `report.html` and `narrative.md` with confidence intervals, 2–3 side-by-side **before/after transcript pairs**, and tags each diff hunk as `[REQUIRED]` vs. `[TUNE]`.

---

## Q11: In the bare-minimum customer scenario (only system prompt, `(input, old_model_output)` pairs, and model parameters), which levers can hill-climbing actually modify?

### Answer
Claude Code can only iterate on artifacts that exist in the evaluation scope:
- **#2 (Skills / Instruction files)** and **#5 (Agent Loop / Application Code)** only apply when you are running the eval inside a customer's full repository that actually uses `SKILL.md` files or custom agent-loop code.
- In the **bare-minimum customer scenario** (where the customer only hands over their **System Prompt**, **Model Parameters** / **Tool Schemas**, and **`(input, old_model_output)`** dataset), the hill-climbing playbook automatically scopes itself to just the levers present in that data:

| Lever in `eval-hillclimb.md` | Available in Bare-Minimum Scenario? | What Hill-Climbing Actually Edits |
|---|---|---|
| **1. System Prompt** | **Yes (Primary Lever)** | Rewriting instructions, adding/refining rules, adding few-shot examples into the prompt, fixing formatting instructions (e.g., raw JSON vs. markdown fences). |
| **3. Tool Descriptions & Schemas** | **Yes (If tools are in the prompt/payload)** | Clarifying tool `description` fields, parameter descriptions, or structured output JSON schemas (`output_config`). |
| **4. Model & API Parameters** | **Yes** | Tuning `model` tier (`Haiku` / `Sonnet` / `Opus`), `thinking` / `effort` level (`low` / `medium` / `high`), `max_tokens`, `temperature`. |
| **2. Skill / Instruction Files** | **No** *(unless customer provides them)* | Skipped. |
| **5. Agent Loop / App Code** | **No** *(unless customer provides their codebase)* | Skipped (the runner calls the Vertex AI Claude endpoint directly with the prompt + parameters). |

---

## Q12: Does `eval-hillclimb.md` use an external prompt-optimization framework like GEPA / DSPy? If not, how is it smart enough to know which direction to optimize?

### Answer
**No — it does NOT import an external optimization framework like GEPA, DSPy (MIPROv2), or TextGrad.**

Instead, [eval-hillclimb.md](../eval-hillclimb.md) and [cost-hillclimb.md](../cost-hillclimb.md) turn **Claude Code itself into a Trace-Driven Reflective Optimizer** (conceptually very similar to how GEPA uses reflective trace analysis, but implemented natively via subagents and on-disk state rather than an external Python library).

Here are the **6 built-in mechanisms** that make it optimize intelligently rather than guessing randomly:

#### 1. Failure-Cluster Math ("Gain Ceiling" Calculation)
Instead of guessing a random prompt tweak, the **Analyzer Subagent** is required to cluster `train` failures by root-cause behavior and calculate the maximum possible score gain before proposing anything (`eval-hillclimb.md` lines 233, 237):
> *"Find the cases doing worst on `<metric>`, plus a couple doing best for contrast; name the single behavior that most often costs it... **Say how many cases show the behavior and how much `<metric>` it costs across them — a fix can gain no more than that.**"*
- For example, if 5 cases fail because the new model wraps JSON in markdown fences (`-50%` score impact) and 1 case fails on priority wording (`-10%` impact), the analyzer mathematically targets the `-50%` behavior cluster first.

#### 2. Contrastive Transcript Diffing (Reading `thinking` + `tool_calls` + Judge `explanation`)
Standard black-box optimizers only see final scores. In Step 4 (`eval-hillclimb.md` lines 195, 227), the Analyzer Subagent reads:
- **Contrastive pairs within a round**: Worst-scoring `train` transcripts vs. best-scoring `train` transcripts (including the model's internal `thinking` block, tool call arguments, and the LLM Judge's `explanation` of *why* it deducted points).
- **Cross-round transcript diffs**: Diffing `baseline/traces/case_17_rep0.json` against `v2/traces/case_17_rep0.json` to see exactly how a prompt edit altered the model's reasoning chain.

#### 3. Cross-Round Trajectory Matrix (`trajectory/scores.tsv`) & Memory (`narrative.md`)
- Every round, the analyzer reads the `train` rows of `trajectory/scores.tsv` (`eval-hillclimb.md` lines 195, 227), which is a matrix of `cases × rounds` (`baseline`, `v1`, `v2`, `v3`...).
- This lets the analyzer spot **oscillations** (e.g., *"v2 fixed cases 1–3 but broke cases 4–5"*) and **stubborn cases** (*"case 7 has scored 0.0 across all 4 rounds"*).
- Meanwhile, `narrative.md` (`line 263`) maintains a running history of every hypothesis tried (`vN/change.md`) and its outcome so the agent never repeats a failed direction.

#### 4. Evolutionary "Keep or Revert" Selection on Held-Out `test`
Like evolutionary optimizers, the loop maintains a single champion (`_state.json.best`) and enforces strict selection rules (`eval-hillclimb.md` line 273):
- **One hypothesis per round**: Never bundle unrelated edits together, so you know *which* edit caused the score change.
- **Automatic Revert on Overfit/Regression**:
  - If `train` goes up **and** `test` goes up $\rightarrow$ **Keep** (`vN` becomes the new parent for `vN+1`).
  - If `train` goes up but `test` stays flat or drops $\rightarrow$ **Overfit detected!** Revert `vN` and try a different direction.
  - If a guardrail metric (like latency or cost) regresses outside noise $\rightarrow$ **Revert**.

#### 5. Anti-Memorization & "De-Fluff" Filters
When LLMs optimize prompts naively, they tend to paste test-case words into the prompt or add useless platitudes (*"be very careful"*, *"think step by step"*). `eval-hillclimb.md` (`lines 231, 241`) forces two checks before any edit is applied:
- **Generalize, don't memorize**: Describe the general failure *behavior*, never the specific nouns/content of the `train` case.
- **Mandatory De-Fluff pass**: Strip out any sentence that has no concrete operational rule.

#### 6. Mode-Switching When Stalled (Step 4.5 Categorization & Breadth Pass)
If single-behavior hill-climbing stalls for 2–3 rounds, the playbook **changes optimization strategy** (`eval-hillclimb.md` lines 279–300):
- It buckets all remaining `train` failures into 5 categories: **Artifact Gap**, **Grader Disagreement** (the rubric itself is flawed!), **Harness/Infra Bug**, **Structural/Routing Issue** (the prompt is too long/buried so the model misses the rule), or **Run-to-Run Variance**.
- If it finds a "long tail" (e.g., 10 tiny edge cases that each only happen once), it switches from single-change hill-climbing to a **one-shot Breadth Pass** (`line 299`) to address all independent long-tail gaps in parallel.

#### Summary Table: Anthropic Hill-Climb vs. GEPA / DSPy

| Feature | External Frameworks (GEPA / DSPy MIPRO) | Anthropic `eval-hillclimb.md` Playbook |
|---|---|---|
| **How it runs** | Python library maintaining a population/Pareto frontier of candidate prompts | Claude Code Orchestrator + per-round Analyzer Subagent reading `traces/` & `scores.tsv` |
| **How it knows which direction to optimize** | LLM reflection on execution traces + genetic crossover/mutation | Subagent clusters `train` failures by max score impact + contrastive diffing of `thinking`/tool traces + `narrative.md` memory |
| **How it prevents overfitting** | Validation split + Pareto frontier selection | Strict data wall (Subagent only sees `train` traces; Outer agent selects winner on held-out `test`) + "Keep or Revert" gate |
| **What it can edit** | Prompt strings & few-shot demonstrations | Prompts, tool schemas, API params (`effort`/`thinking`), skill files, or app code |

---

## Q13: If a customer wants to provide their full application code, agent loop, skills, and instruction files for hill-climbing, do they copy their entire source code into `anthropic-eval/`?

### Answer
**Actually, it works the other way around — which is much cleaner!**

Instead of copying a customer's entire application codebase *into* `anthropic-eval/`, **`anthropic-eval/` stays in one place as your reusable toolkit**, and you point Claude Code at the **customer's own repo/folder** (e.g., `/Applications/antigravity/my-agent/` or `/Applications/antigravity/customer-repo/`).

#### 1. Where the Files Live (Directory Layout)
```text
/Applications/antigravity/
├── anthropic-eval/                  <-- Your reusable eval toolkit (never changes)
│   ├── build-eval.md
│   ├── eval-audit.md
│   ├── eval-hillclimb.md
│   ├── cost-hillclimb.md
│   └── report/
│       ├── runner-scaffold.mjs
│       └── build-report-lite.mjs
│
└── customer-agent-repo/             <-- Customer's cloned git repo (Python, TS, ADK, etc.)
    ├── app/                         <-- Customer's real agent loop, tools, code
    ├── skills/                      <-- Customer's real SKILL.md / instruction files
    ├── eval/
    │   ├── cases.json               <-- Test cases
    │   └── run-eval.mjs             <-- Copied from runner-scaffold.mjs (or run_eval.py)
    └── .claude/hillclimb/<flow>/    <-- Generated eval results, traces/, report.html, change.patch
```

**Why you keep the customer's repo separate instead of copying it into `anthropic-eval/`:**
1. **Dependencies & Virtual Environments Stay Intact**: The customer's agent already has its own `.venv`, `pyproject.toml`, `package.json`, and relative module imports.
2. **Git Diffs (`change.patch`) Work Out of the Box**: During hill-climbing ([eval-hillclimb.md:L241](../eval-hillclimb.md)), Claude Code edits the customer's real source files (`app/agent.py`, `skills/SKILL.md`, etc.) and runs `git diff` to save `vN/change.patch`. When the hill-climb finishes, the winning changes are already a clean git diff in the customer's repo that you can hand back to them as a PR!

#### 2. How `runCase()` Connects to the Customer's Agent Code
When the customer provides their full agent codebase, [build-eval.md (lines 165–170)](../build-eval.md) instructs Claude Code **not** to just call the raw Claude API with a system prompt string—because that would bypass the customer's agent loop, skill loader, and tool wiring.

Instead, Claude Code wires `runCase()` to invoke the customer's **real entry point** in one of 3 ways:
1. **Direct Function / CLI Import** *(if same language or via subprocess)*:
   - If the customer's agent is in Python (like `/Applications/antigravity/my-agent/`), Claude Code either writes a Python runner (`run_eval.py`) that imports their agent directly (`from app.agent import root_agent`) **or** has `run-eval.mjs` call `python3 -m app.run_case` and return the transcript + token usage JSON.
2. **Local HTTP Server / Endpoint**:
   - The customer's agent spins up locally (`localhost:8000/chat`), and `runCase()` sends each test case to the local endpoint and records the full multi-turn tool trajectory and token usage.
3. **Thin Test-Mode Wrapper (When Tools Have Real-World Side Effects)** (`build-eval.md` lines 29, 169):
   - If the customer's agent calls tools that write to production databases, charge credit cards, or send emails, Claude Code creates a thin test wrapper that **mocks only those external side-effect functions** (returning canned tool outputs from the customer's logs) while still running 100% of the customer's real agent loop, context assembly, and `SKILL.md` loading.

#### Summary: Two Ways Customers Can Work With You

| Customer Engagement Type | What Customer Gives You | Where You Put It | What Gets Evaluated & Hill-Climbed |
|---|---|---|---|
| **Type A: "Bare Minimum" (Prompt / I-O Migration)** | System prompt + tool schemas + `(input, old_output)` logs | A lightweight folder like `anthropic-eval/example-migration/` | Raw Vertex AI Claude endpoint (`System Prompt`, `Tool Schemas`, `Model & API Params`) |
| **Type B: "Full Agent / Codebase" Migration** | Their git repo (or a zip of their agent folder) + 15–30 test inputs (and mock tool fixtures if needed) | Clone/unzip as its own folder `/Applications/antigravity/<customer-repo>/` and reference `/Applications/antigravity/anthropic-eval/*.md` | The entire agent end-to-end (`System Prompt`, `SKILL.md` files, `Tool code/schemas`, `Agent loop code`, `Model & API Params`) |

---

## Q14: How to Adapt This Framework for Antigravity & the Full Gemini Model Family (including `gemini-3.8-flash` & `gemini-4-pro`, plus Non-Gemini Models)?

### Answer
Because ~85% of the framework in `anthropic-eval/` is **model-agnostic evaluation science** (train/test isolation, noise-floor math, `results.jsonl` / `traces/` / `errors.jsonl` schema, and `build-report-lite.mjs`), you keep the core engine intact and only swap out **6 Claude-Code / Anthropic-specific coupling points**.

---

### Part 1: The 6 Areas to Change

#### 1. Agent Tool Names (Claude Code $\rightarrow$ Antigravity Tools)
Replace Claude Code's internal tool names in the `.md` playbooks with Antigravity's native tools:

| Claude Code Concept in `.md` | Antigravity Equivalent to Replace With | Where It Appears |
|---|---|---|
| `AskUserQuestion` | `ask_question` tool | `build-eval.md:L9–11`, `eval-hillclimb.md:L11, L55, L88` |
| `Bash` with `run_in_background: true` | `run_command` (with `WaitMsBeforeAsync` + reactive background task wakeup) | `eval-hillclimb.md:L13` |
| `Agent` / `Task` tool (for spawning the per-round Analyzer Subagent) | `invoke_subagent` (using `TypeName: "self"` or a defined `eval_analyzer` subagent with `Model: "pro"` or `"inherit"`) | `eval-hillclimb.md:L13, L227, L283` |
| `.claude/hillclimb/<flow>/` default folder | `.antigravity/hillclimb/<flow>/` (or `eval_runs/<flow>/`) | All `.md` files + `runner-scaffold.mjs:L181` |

---

#### 2. Full Gemini Model Family, Judge Tiers & Cross-Model Support
In `build-eval.md` (line 82), `eval-hillclimb.md`, and `cost-hillclimb.md`, update the model catalog and Judge Selection Menu to cover the **complete Gemini model family** (from legacy migration sources up to the latest **`gemini-3.8-flash`** and **`gemini-4-pro`**) alongside Vertex AI Model Garden models:

##### A. Full Gemini Model Family Matrix (Targets & Migration Paths)

| Generation / Tier | Model IDs | Primary Role in Evaluations & Migrations |
|---|---|---|
| **Latest Frontier (Gemini 4 & 3.8)** | **`gemini-4-pro`**<br>**`gemini-3.8-flash`**<br>`gemini-3.8-flash-lite` | **Primary Migration Targets** for next-gen reasoning, coding, agentic workflows (`gemini-4-pro`) and high-speed, low-cost production workloads (`gemini-3.8-flash`). |
| **Gemini 3 / 3.5 Series** | `gemini-3.5-pro`, `gemini-3.5-flash`<br>`gemini-3.0-pro`, `gemini-3.0-flash` | Mid-generation targets or incumbent baselines migrating to `gemini-3.8-flash` / `gemini-4-pro`. |
| **Gemini 2.5 Series** | `gemini-2.5-pro`<br>`gemini-2.5-flash`<br>`gemini-2.5-flash-lite` | Common current production baselines migrating to `gemini-3.8-flash` or `gemini-4-pro` (or targets when migrating from 1.5/2.0). |
| **Legacy Gemini (1.5 & 2.0)** | `gemini-2.0-flash`, `gemini-2.0-flash-lite`<br>`gemini-1.5-pro`, `gemini-1.5-flash` | **Legacy Migration Sources (`baseline`)** being retired or upgraded to newer Gemini tiers. |
| **Non-Gemini (Vertex Model Garden)** | `claude-opus-4-5`, `claude-sonnet-4-5`, `claude-haiku-4-5`<br>`claude-3-5-sonnet`, `claude-3-5-haiku`<br>`llama-4-*`, `deepseek-*`, `mistral-*` | Cross-family migrations (e.g., Claude $\rightarrow$ `gemini-4-pro` / `gemini-3.8-flash`) or newer-to-newer Model Garden migrations. |

##### B. Updated Judge Model Selection Menu (`build-eval.md:L82`)
When `build-eval.md` asks the user to choose a Judge Model for **Pointwise Rubric** or **Pairwise Blind Comparison**:
1. **Fast / High-Volume PR Judge**: **`gemini-3.8-flash`** *(or `gemini-2.5-flash` / `claude-haiku-4-5`)* — ultra-fast and cheap enough to run on every PR or large dataset.
2. **Balanced Default Judge**: **`gemini-3.8-flash` (with high thinking budget)** or **`gemini-3.5-pro` / `gemini-2.5-pro`**.
3. **Nuanced / Frontier Reasoning Judge**: **`gemini-4-pro`** *(or `claude-opus-4-5` / `claude-sonnet-4-5`)* — when grading subtle reasoning, legal/medical accuracy, or complex multi-step agent trajectories.
4. **Strict Anti-Self-Bias Rule**: *Never use the exact model-under-test as its own judge.*
   - If evaluating a migration to **`gemini-3.8-flash`**, use **`gemini-4-pro`** (or `claude-sonnet-4-5`) as the judge.
   - If evaluating a migration to **`gemini-4-pro`**, use **`claude-opus-4-5` / `claude-sonnet-4-5`** (or `gemini-3.5-pro`) as the judge so `gemini-4-pro` never grades its own outputs.

##### C. Model × Effort Staircase for `cost-hillclimb.md`
Update the cost-optimization staircase in `cost-hillclimb.md` to walk down the Gemini family and thinking levels:
- `gemini-4-pro (thinking: HIGH)` $\rightarrow$ `gemini-4-pro (thinking: MEDIUM/LOW)` $\rightarrow$ `gemini-3.8-flash (thinking: HIGH)` $\rightarrow$ `gemini-3.8-flash (thinking: LOW / 0)` $\rightarrow$ `gemini-3.8-flash-lite`.

---

#### 3. API Parameters & Response Field Mapping (`build-eval.md` & `cost-hillclimb.md`)
Update the model parameter vocabulary across the `.md` files so the agent knows how to tune **both Gemini (`3.8-flash`, `4-pro`, `2.5-*`) and non-Gemini models**:

| Concept | Anthropic / Claude API Name | Gemini / Vertex GenAI Equivalent | OpenAI / Model Garden OpenAPI Equivalent |
|---|---|---|---|
| **Structured JSON Output (for Grader/Judge)** | `output_config.format` | `response_mime_type: "application/json"` + `response_schema` | `response_format: { type: "json_schema", ... }` |
| **Reasoning / Thinking Lever** | `thinking: { budget_tokens }` / `effort` | `thinking_config: { thinking_budget }` or `thinking_level` (`LOW`/`MEDIUM`/`HIGH`) | `reasoning_effort` (`low`/`medium`/`high`) |
| **Truncation Check (`status: "truncated"`)** | `stop_reason === "max_tokens"` | `finishReason === "MAX_TOKENS"` | `finish_reason === "length"` |
| **Safety / Refusal Check** | `stop_reason === "refusal"` | `finishReason === "SAFETY"` / `"RECITATION"` / `"PROHIBITED_CONTENT"` | `finish_reason === "content_filter"` |
| **Extended Thinking in `traces/`** | Content block `type: "thinking"` | Part with `thought: true` | `reasoning_content` |
| **Token Usage Accounting** | `input_tokens`, `output_tokens`, `cache_read_input_tokens` | `promptTokenCount`, `candidatesTokenCount`, `thoughtsTokenCount`, `cachedContentTokenCount` | `prompt_tokens`, `completion_tokens` |

---

#### 4. `runner-scaffold.mjs` — Two Small Code Updates
`report/runner-scaffold.mjs` only has **two places** that assume Anthropic conventions:

1. **Served-Model Identity Check (`lines 485–494`)**:
   - Update the normalization regex to accept all Gemini model families (`gemini-4-pro`, `gemini-3.8-flash`, `gemini-2.5-*`, `publishers/google/models/...`, `-001`, `-preview-*`, `-exp-*`) as well as Vertex Model Garden `@YYYYMMDD` suffixes.
2. **Truncation Detection (`line 522`)**:
   - Normalize across providers:
     ```js
     const isTruncated = ['max_tokens', 'MAX_TOKENS', 'length'].includes(run.stop_reason);
     status: run.status ?? (isTruncated ? 'truncated' : 'ok')
     ```

---

#### 5. Add a `model-migration.md` Reference Playbook (for Gemini & Cross-Model Migrations)
Create `references/model-migration.md` covering common migration behavioral shifts:
- **Older Gemini (`1.5` / `2.0` / `2.5`) $\rightarrow$ `gemini-3.8-flash` & `gemini-4-pro`**:
  - Adjusting `thinking_config` (`thinking_budget` / `thinking_level`) so latency-sensitive tasks on `gemini-3.8-flash` don't over-think, while complex tasks on `gemini-4-pro` allocate sufficient thinking budget.
  - Prompt conciseness: newer `gemini-3.8-flash` and `gemini-4-pro` follow instructions much more literally; old heavy-handed prompt workarounds ("IMPORTANT! DO NOT EVER...") from 1.5/2.0 can cause over-refusals or rigid formatting and should be simplified during hill-climbing.
- **Claude / GPT $\rightarrow$ `gemini-3.8-flash` & `gemini-4-pro`**:
  - Moving from prompt-enforced JSON to Gemini `response_schema` (or adding explicit no-markdown-fence instructions).
  - System instruction placement (`systemInstruction` field vs. user-turn prefixing) and tool-calling declaration differences.

---

#### 6. Package It as a Native Antigravity Skill (`SKILL.md`)

```text
antigravity-eval/
├── SKILL.md                        <-- Entrypoint with YAML frontmatter (routes to the right guide)
├── references/
│   ├── build-eval.md               <-- Adapted from build-eval.md (uses ask_question, Gemini + multi-model)
│   ├── eval-audit.md               <-- Adapted from eval-audit.md (100% model-agnostic)
│   ├── eval-hillclimb.md           <-- Adapted from eval-hillclimb.md (uses invoke_subagent, run_command)
│   ├── cost-hillclimb.md           <-- Adapted for Gemini 4 Pro -> 3.8 Flash staircase
│   └── model-migration.md          <-- Playbook for Legacy/Claude/GPT -> Gemini 3.8 Flash & Gemini 4 Pro
└── report/
    ├── SCHEMA.md                   <-- Unchanged data contract
    ├── providers.mjs               <-- Universal Vertex AI caller (Gemini, Claude, Llama/OpenAI endpoints)
    ├── runner-scaffold.mjs         <-- Updated with multi-provider stop_reason & model-ID check
    └── build-report-lite.mjs       <-- 100% unchanged! Works with any model's results.jsonl
```

With `report/providers.mjs` normalizing Vertex AI responses across Gemini (`generateContent`), Claude (`rawPredict`), and OpenAI-compatible Model Garden endpoints, you can benchmark any migration with a single flag:
```bash
node run-eval.mjs --flow flow --variant baseline --model gemini-2.5-pro --approve-harness
node run-eval.mjs --flow flow --variant v1       --model gemini-3.8-flash
node run-eval.mjs --flow flow --variant v2       --model gemini-4-pro
```

---

## Q15: If I were to distribute `gemini-eval/` to all Gemini AI engineers so everyone can use this playbook to help customers run evals, what are the formats to make it portable, atomic, and repeatable?

### Answer
To distribute [`/Applications/antigravity/gemini-eval/`](file:///Applications/antigravity/gemini-eval) across all Gemini AI engineers so they can drop it into any customer engagement with zero friction, you can package it into **five complementary formats** ranked from fastest-to-adopt to most enterprise-integrated:

---

### 1. Universal Agent Skill Package (`SKILL.md` + `npx skills` / Antigravity Skill Bundle) — *Best for Agentic IDEs*
Make `gemini-eval` an installable **Agent Skill** that works across Antigravity, Gemini CLI, Cursor, and Claude Code:
- **What to add**: A top-level `SKILL.md` inside `gemini-eval/` with YAML frontmatter (`name: gemini-eval`, `description: ...`) and a routing table pointing to [`build-eval.md`](file:///Applications/antigravity/gemini-eval/build-eval.md), [`eval-audit.md`](file:///Applications/antigravity/gemini-eval/eval-audit.md), [`eval-hillclimb.md`](file:///Applications/antigravity/gemini-eval/eval-hillclimb.md), and [`cost-hillclimb.md`](file:///Applications/antigravity/gemini-eval/cost-hillclimb.md).
- **How engineers install it**:
  - **Antigravity / Jetski**: Drop or symlink into `~/.gemini/config/skills/gemini-eval/` (global across all customer workspaces) or `.agent/skills/gemini-eval/` (per-repo).
  - **GitHub / Public Skills CLI**: Publish to a GitHub repo (or PR into [`google-gemini/gemini-skills`](https://github.com/google-gemini/gemini-skills) / [`google/skills`](https://github.com/google/skills)) so any engineer runs a single one-liner:
    ```bash
    npx skills add <org>/gemini-eval
    ```
- **Why it's atomic & repeatable**: Self-contained folder (playbooks + `references/` + stdlib Python scripts); the agent automatically loads `SKILL.md` whenever an engineer asks *"build an eval"*, *"audit this customer's eval"*, or *"hillclimb this migration to Gemini 3.8 Flash"*.

---

### 2. Zero-Install Python CLI via `uvx` / `pipx` (`gemini-eval-kit` Wheel) — *Best for Customer Repos*
Because [`runner-scaffold.py`](file:///Applications/antigravity/gemini-eval/report/runner-scaffold.py) and [`build-report-lite.py`](file:///Applications/antigravity/gemini-eval/report/build-report-lite.py) are already 100% Python stdlib, wrap the folder in a tiny `pyproject.toml` package:
- **How engineers use it without polluting a customer's virtualenv**:
  ```bash
  # Scaffold a new eval flow in the customer's repo
  uvx gemini-eval init --flow support-triage

  # Build the HTML report + trajectory TSV from any flow directory
  uvx gemini-eval report .antigravity/hillclimb/support-triage/

  # Run the demo migration offline in 2 seconds to show a customer what the deliverable looks like
  uvx gemini-eval demo
  ```
- **Why it's atomic & repeatable**:
  - **Relative-path independence**: Packaging it as a CLI or resolving paths via `Path(__file__).resolve().parent` eliminates hardcoded machine paths.
  - Engineers can also `pip install` or `uv add --dev` it into a customer's CI/CD pipeline so every PR runs the exact same report builder and `--verify` check.

---

### 3. Antigravity Plugin + Slash Commands (`/eval-build`, `/eval-audit`, `/eval-climb`, `/eval-cost`) — *Best UX for Field Engineers*
Package `gemini-eval` as an **Antigravity Customization Plugin** (under `~/.gemini/jetski/plugins/gemini-eval/`):
- **Bundled Workflows (Slash Commands)**:
  - `/eval-build`: Triggers [`build-eval.md`](file:///Applications/antigravity/gemini-eval/build-eval.md) Step 0–4 with interactive `ask_question` gates.
  - `/eval-audit`: Runs the 6-part [`eval-audit.md`](file:///Applications/antigravity/gemini-eval/eval-audit.md) checklist on an existing customer benchmark and outputs a severity-ranked health table.
  - `/eval-climb`: Launches the [`eval-hillclimb.md`](file:///Applications/antigravity/gemini-eval/eval-hillclimb.md) loop using isolated `invoke_subagent` trace analyzers.
  - `/eval-cost`: Runs the [`cost-hillclimb.md`](file:///Applications/antigravity/gemini-eval/cost-hillclimb.md) staircase walk (`model × thinking_level`) using [`references/pricing.md`](file:///Applications/antigravity/gemini-eval/references/pricing.md).
- **Why it's repeatable**: Every AI engineer gets the exact same interactive prompts, pre-registration gates, and subagent isolation without having to remember which `.md` file to point the agent at.

---

### 4. Interactive Colab / Vertex AI Workbench "Customer Workshop" Notebook — *Best for Live Customer Engagements*
Many enterprise customers cannot install CLI tools or grant a coding agent direct repo access on Day 1, but they *can* open a Colab Enterprise or Vertex AI Workbench notebook:
- **What it contains**:
  - A single `.ipynb` generated from [`example-migration/`](file:///Applications/antigravity/gemini-eval/example-migration) that embeds [`runner-scaffold.py`](file:///Applications/antigravity/gemini-eval/report/runner-scaffold.py) and [`build-report-lite.py`](file:///Applications/antigravity/gemini-eval/report/build-report-lite.py) inline, renders `report.html` directly inside an `IPython.display.IFrame`, and lets the customer swap in their own JSON/CSV cases and Vertex AI project ID.
- **Why it's portable**: Runs in browser in 60 seconds with `SIMULATE=1` for live demos, then switches to live Vertex AI / Gemini API with one toggle.

---

### 5. `agents-cli` (`google-agents-cli`) Template Integration — *Best for ADK & Agent Engine Customers*
For engineers already using Google's `agents-cli` (`scaffold` / `eval` skills):
- Ship `gemini-eval` as a template preset (`agents-cli eval init --recipe=hillclimb`) so any ADK agent project gets:
  - `.antigravity/hillclimb/<flow>/_state.json` pre-populated with [`references/pricing.md`](file:///Applications/antigravity/gemini-eval/references/pricing.md) rates,
  - `eval/run_eval.py` pre-wired to `google.adk.Runner` + `runner-scaffold.py`,
  - A GitHub Actions / Cloud Build step that runs `build-report-lite.py` and uploads `report.html` as a build artifact on every PR.

---

### Summary Checklist to Make the Folder 100% Portable Before Sharing
1. **Add a root `SKILL.md`** with YAML frontmatter so skill loaders (Antigravity, `npx skills`, Gemini CLI) auto-discover the 4 playbooks and 4 `references/` files.
2. **Replace the hardcoded `/Applications/antigravity/gemini-eval/report` path** in [`build-eval.md:L160`](file:///Applications/antigravity/gemini-eval/build-eval.md#L160) and [`eval-hillclimb.md:L284`](file:///Applications/antigravity/gemini-eval/eval-hillclimb.md#L284) with `<SKILL_DIR>/report`.
3. **Add a version stamp (`VERSION` or `pyproject.toml`)** and a date stamp on [`references/pricing.md`](file:///Applications/antigravity/gemini-eval/references/pricing.md) so engineers know which Gemini model generation and rate card their local copy has.

---

## Q16: For Option 1 (Universal Agent Skill Package), does it also include the `.py` executables?

### Answer
**Yes — 100%.** The Universal Agent Skill standard (used by Antigravity, Gemini CLI, `npx skills`, and Claude Code) is designed specifically to bundle **both markdown instructions and executable scripts/assets** inside a single skill folder.

#### 1. How a Skill Package Carries the `.py` Executables
When an engineer installs the skill (e.g., into `~/.gemini/config/skills/gemini-eval/` or via `npx skills add <org>/gemini-eval`), the **entire directory tree** is copied verbatim to their local disk:

```text
gemini-eval/
├── SKILL.md                      # Entrypoint with YAML frontmatter + routing instructions
├── build-eval.md                 # Playbook 1
├── eval-audit.md                 # Playbook 2
├── eval-hillclimb.md             # Playbook 3
├── cost-hillclimb.md             # Playbook 4
├── references/                   # Local reference & gap-filling docs
│   ├── pricing.md
│   ├── cost-optimization.md
│   ├── prompt-audit.md
│   └── diff.md
├── report/                       # Bundled Python executables + schema
│   ├── SCHEMA.md
│   ├── runner-scaffold.py        # <-- Included & copied into customer repo on Step 3
│   └── build-report-lite.py      # <-- Included & executed directly from the skill folder
└── example-migration/            # Bundled runnable Python reference example
    ├── run-eval.py               # <-- Included & runnable immediately with SIMULATE=1
    ├── cases.json
    ├── prompts.json
    └── flow/...
```

#### 2. How the Agent Finds and Runs the `.py` Files Automatically
1. **Skill Path Injection**: When Antigravity (or another skill-compatible agent) loads `gemini-eval/SKILL.md`, the agent knows the exact absolute path to that `SKILL.md` file on the engineer's machine (as seen in the system prompt's `<skills>` block, e.g., `/Users/<engineer>/.gemini/config/skills/gemini-eval/SKILL.md`).
2. **Executing `build-report-lite.py` In-Place**: The playbook instructs the agent to resolve `report/build-report-lite.py` **relative to the skill directory** (`<SKILL_DIR>/report/build-report-lite.py`) and run it with `python3` against the customer's `.antigravity/hillclimb/<flow>/` folder.
3. **Scaffolding `runner-scaffold.py`**: When starting a new eval in a customer repo, the agent copies `<SKILL_DIR>/report/runner-scaffold.py` directly into the customer's repo and fills in `load_cases`, `run_case`, and `grade_case`.
4. **Zero Dependency Friction**: Because both [`runner-scaffold.py`](file:///Applications/antigravity/gemini-eval/report/runner-scaffold.py) and [`build-report-lite.py`](file:///Applications/antigravity/gemini-eval/report/build-report-lite.py) only use the Python 3 standard library, they work out of the box on any engineer's laptop without needing a `pip install` step inside the skill folder.
