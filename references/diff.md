# Conversion Summary & Diff: `anthropic-eval/` $\rightarrow$ `gemini-eval/`

This document summarizes every architectural, playbook, runtime, model-family, and reference-skill change made to build [`/Applications/antigravity/gemini-eval/`](file:///Applications/antigravity/gemini-eval) from [`/Applications/antigravity/anthropic-eval/`](file:///Applications/antigravity/anthropic-eval).

---

## 1. Directory & File-by-File Mapping

`gemini-eval/` mirrors the exact directory structure, methodology, data contracts (`results.jsonl`, `errors.jsonl`, `traces/`, `_state.json`, `summary.json`, `change.md`, `change.patch`, `report.html`, `trajectory/scores.tsv`), and statistical rigor of `anthropic-eval/`, while translating all playbooks to **Antigravity + Gemini (and multi-model)** and converting all executable scripts from **Node.js (`.mjs`) to Python 3 (`.py`)**.

| `anthropic-eval/` Source File | `gemini-eval/` Target File | Key Changes Made |
| :--- | :--- | :--- |
| [`build-eval.md`](file:///Applications/antigravity/anthropic-eval/build-eval.md) | [`build-eval.md`](file:///Applications/antigravity/gemini-eval/build-eval.md) | Adapted entry-point discovery to `google-genai`, Vertex AI, Google ADK, and Model Garden; updated Judge Selection Menu to Gemini 3.8 Flash / Gemini 4 Pro + cross-family judges; replaced `.claude/hillclimb/` with `.antigravity/hillclimb/`; pointed CLI invocations to `python3` and `runner-scaffold.py` / `build-report-lite.py`; linked official Google Gemini skills and [`references/pricing.md`](file:///Applications/antigravity/gemini-eval/references/pricing.md). |
| [`eval-audit.md`](file:///Applications/antigravity/anthropic-eval/eval-audit.md) | [`eval-audit.md`](file:///Applications/antigravity/gemini-eval/eval-audit.md) | Preserved all 6 audit sections (input set, runner, grader, environment, statistical power, reporting); updated served-model verification (`modelVersion`), rate-limit codes (`429` / `RESOURCE_EXHAUSTED` / `503`), truncation (`MAX_TOKENS` / `max_tokens`), thinking token accounting (`thinking_tokens` / `thoughtsTokenCount`), and cache hit fields (`cachedContentTokenCount` / `cache_read_input_tokens`). |
| [`eval-hillclimb.md`](file:///Applications/antigravity/anthropic-eval/eval-hillclimb.md) | [`eval-hillclimb.md`](file:///Applications/antigravity/gemini-eval/eval-hillclimb.md) | Replaced Claude Code `AskUserQuestion` and `Agent(...)` subagent syntax with Antigravity `ask_question` and `invoke_subagent`; updated `_state.json` paths to `.antigravity/hillclimb/<flow>/`; added `thinking_tokens` to `usage`; updated model migration references to [`skills/gemini-api-dev/references/migration.md`](https://github.com/google-gemini/gemini-skills/blob/main/skills/gemini-api-dev/references/migration.md) and [`references/prompt-audit.md`](file:///Applications/antigravity/gemini-eval/references/prompt-audit.md). |
| [`cost-hillclimb.md`](file:///Applications/antigravity/anthropic-eval/cost-hillclimb.md) | [`cost-hillclimb.md`](file:///Applications/antigravity/gemini-eval/cost-hillclimb.md) | Adapted the 6-step cost-reduction search order to Gemini context caching (`cached_content` / implicit caching on `gemini-3.8-flash`), `ThinkingConfig(thinking_level="LOW"\|"MEDIUM"\|"HIGH"\|"MINIMAL")`, and the Gemini model tier staircase (`gemini-4-pro` $\rightarrow$ `gemini-3.8-flash` $\rightarrow$ `gemini-3.5-flash-lite`); linked [`references/cost-optimization.md`](file:///Applications/antigravity/gemini-eval/references/cost-optimization.md) and [`references/prompt-audit.md`](file:///Applications/antigravity/gemini-eval/references/prompt-audit.md). |
| [`report/SCHEMA.md`](file:///Applications/antigravity/anthropic-eval/report/SCHEMA.md) | [`report/SCHEMA.md`](file:///Applications/antigravity/gemini-eval/report/SCHEMA.md) | Updated path references to `.antigravity/hillclimb/<flow>/`, added `thinking_tokens` to the `usage` schema contract, and updated builder commands to `python3 build-report-lite.py`. |
| [`report/runner-scaffold.mjs`](file:///Applications/antigravity/anthropic-eval/report/runner-scaffold.mjs) | [`report/runner-scaffold.py`](file:///Applications/antigravity/gemini-eval/report/runner-scaffold.py) | Ported 1:1 from Node.js ESM to Python 3 (`asyncio` + stdlib). Preserved CLI flags, SHA-256 `--approve-harness` integrity gate (`pyproject.toml`, `uv.lock`, `requirements.txt`, `package-lock.json`), bounded concurrency, per-case wall-clock timeout, jittered backoff, served-model assertion, frozen pairwise reference helper, and `google-genai` / cross-provider helper comments. |
| [`report/build-report-lite.mjs`](file:///Applications/antigravity/anthropic-eval/report/build-report-lite.mjs) | [`report/build-report-lite.py`](file:///Applications/antigravity/gemini-eval/report/build-report-lite.py) | Ported 1:1 from Node.js ESM to Python 3 stdlib. Produces byte-identical HTML structure, CSS, interactive JS sorting/filtering, XSS-safe JSON script-tag escaping, SVG sparkline, and `trajectory/scores.tsv`. |
| [`example-migration/run-eval.mjs`](file:///Applications/antigravity/anthropic-eval/example-migration/run-eval.mjs) | [`example-migration/run-eval.py`](file:///Applications/antigravity/gemini-eval/example-migration/run-eval.py) | Ported from Node.js to Python 3 (`google-genai` SDK + `SIMULATE=1` deterministic offline simulation). Demonstrates migrating from `gemini-2.5-flash` (`baseline`) to `gemini-3.8-flash` (`v1`, `v2`). |
| [`example-migration/cases.json`](file:///Applications/antigravity/anthropic-eval/example-migration/cases.json), [`prompts.json`](file:///Applications/antigravity/anthropic-eval/example-migration/prompts.json), [`README.md`](file:///Applications/antigravity/anthropic-eval/example-migration/README.md) | [`example-migration/cases.json`](file:///Applications/antigravity/gemini-eval/example-migration/cases.json), [`prompts.json`](file:///Applications/antigravity/gemini-eval/example-migration/prompts.json), [`README.md`](file:///Applications/antigravity/gemini-eval/example-migration/README.md) | Adapted the 30-case classification benchmark and prompt progression (`baseline` $\rightarrow$ `v1` $\rightarrow$ `v2`) to `gemini-2.5-flash` $\rightarrow$ `gemini-3.8-flash` and regenerate `flow/report.html` + `flow/trajectory/scores.tsv`. |
| *(External parent references in `skills/claude-api/`)* | [`references/pricing.md`](file:///Applications/antigravity/gemini-eval/references/pricing.md), [`references/cost-optimization.md`](file:///Applications/antigravity/gemini-eval/references/cost-optimization.md), [`references/prompt-audit.md`](file:///Applications/antigravity/gemini-eval/references/prompt-audit.md) | Added local gap-filling reference docs to cover token pricing tables, `cost_usd` calculation, no-eval cost optimization, context-caching invalidation diagnostics, and pre-migration prompt/config auditing. |

---

## 2. Agent Platform & Orchestration Changes (Claude Code $\rightarrow$ Antigravity)

| Dimension | `anthropic-eval/` (Claude Code) | `gemini-eval/` (Antigravity) |
| :--- | :--- | :--- |
| **Skill Slash Commands** | `/claude-api build-eval`, `/claude-api hillclimb` | `/gemini-eval build-eval`, `/gemini-eval hillclimb` |
| **Default Working Directory** | `.claude/hillclimb/<flow>/` | `.antigravity/hillclimb/<flow>/` |
| **Interactive User Prompts** | `AskUserQuestion` tool | `ask_question` tool (`questions=[{question, options, is_multi_select}]`) |
| **Isolated Analyzer Subagent** | `Agent(subagent_type="general-purpose", prompt=...)` | `invoke_subagent(Subagents=[{TypeName: "self", Role: "Eval Trace Analyzer", Prompt: ...}])` |
| **Harness Lockfile Digest** | `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `bun.lockb`, `uv.lock`, `poetry.lock` | `pyproject.toml`, `uv.lock`, `poetry.lock`, `Pipfile.lock`, `requirements.txt`, `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lockb` |

---

## 3. Model Family, Judge Selection & Multi-Model Ecosystem

| Role | `anthropic-eval/` | `gemini-eval/` |
| :--- | :--- | :--- |
| **Frontier Tier** | `claude-opus-4-6` | `gemini-4-pro` (`gemini-4-argon`) |
| **Balanced / High-Speed Reasoning Tier** | `claude-sonnet-4-6` | `gemini-3.8-flash` (with configurable `thinking_level="LOW"\|"MEDIUM"\|"HIGH"`), `gemini-3.5-pro`, `gemini-2.5-pro` |
| **Fast / Low-Cost Tier** | `claude-haiku-4-5` | `gemini-3.8-flash` (`LOW`/`MINIMAL`), `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-2.5-flash`, `gemini-2.5-flash-lite` |
| **Judge Selection Menu (`build-eval.md` Step 2)** | Haiku 4.5 (Fast) / Sonnet 4.6 (Balanced) / Opus 4.6 (Nuanced) | **Fast PR Judge:** `gemini-3.8-flash` or `gemini-2.5-flash` (or `claude-haiku-4-5` cross-family)<br>**Balanced Default Judge:** `gemini-3.8-flash` (`HIGH` thinking) or `gemini-3.5-pro` / `gemini-2.5-pro`<br>**Nuanced Frontier Judge:** `gemini-4-pro` (or `claude-opus-4-5` / `claude-sonnet-4-5` via Vertex AI Model Garden when judging `gemini-4-pro`) |
| **Supported Provider SDKs** | `@anthropic-ai/sdk`, `AnthropicBedrock`, `AnthropicVertex`, `AnthropicFoundry` | `google-genai` (`genai.Client` for Google AI Studio & Vertex AI), Google ADK (`Runner`), Vertex AI Model Garden (`AnthropicVertex` / OpenAI-compatible endpoints) |

---

## 4. API Surface, Telemetry & Schema Normalization

To ensure `build-report-lite.py` and the full report viewer work identically across Gemini and non-Gemini models, `gemini-eval/` normalizes Gemini's `GenerateContentResponse` fields into the canonical `results.jsonl` and `traces/` schema:

| Concept | Anthropic API | Gemini API (`google-genai`) | Normalized `gemini-eval/` Field |
| :--- | :--- | :--- | :--- |
| **Served Model ID** | `response.model` | `response.model_version` | `row["model"]` (asserted against requested model prefix) |
| **Stop / Truncation Reason** | `stop_reason == "max_tokens"` | `finish_reason == "MAX_TOKENS"` | `row["stop_reason"]`, `row["status"] = "truncated"` |
| **Uncached Input Tokens** | `usage.input_tokens` | `prompt_token_count - cached_content_token_count` | `row["usage"]["input_tokens"]` |
| **Visible Output Tokens** | `usage.output_tokens` | `candidates_token_count` | `row["usage"]["output_tokens"]` |
| **Reasoning / Thinking Tokens** | *(Included in `output_tokens`)* | `thoughts_token_count` | `row["usage"]["thinking_tokens"]` |
| **Cached Input Tokens** | `usage.cache_read_input_tokens` | `cached_content_token_count` | `row["usage"]["cache_read_input_tokens"]` |
| **Reasoning Effort Control** | `thinking: {type: "adaptive"}`, `output_config: {effort: "low"\|"medium"\|"high"}` | `ThinkingConfig(thinking_level="MINIMAL"\|"LOW"\|"MEDIUM"\|"HIGH")` or `thinking_budget` | Iterated as the X-axis of `cost-hillclimb.md` Step 2 staircase walk |
| **Structured Judge Output** | `output_config: {format: {type: "json_schema", ...}}` | `response_mime_type="application/json"`, `response_schema=...` | Deterministic JSON grading without markdown-fence failures |
| **Trace Thinking Capture** | `block.type == "thinking"` | `part.thought == True` | `turn["thinking"]` in `traces/<id>_rep<k>.json` |

---

## 5. Executable Code Conversion (Node.js `.mjs` $\rightarrow$ Python 3 `.py`)

All three executable scripts were rewritten in Python 3 with zero third-party dependencies required for the scaffold and report builder:

1. **[`report/runner-scaffold.py`](file:///Applications/antigravity/gemini-eval/report/runner-scaffold.py)** (replaces `runner-scaffold.mjs`):
   - Uses `asyncio.Semaphore` for bounded concurrency and `asyncio.wait_for` for hard per-case wall-clock timeouts.
   - Implements jittered exponential backoff on `429` / `RESOURCE_EXHAUSTED` / `503` / `529`.
   - Enforces the SHA-256 `--approve-harness` integrity gate over the runner, lockfiles, and `_state.json.harness_paths`.
   - Writes atomic per-case lines to `results.jsonl`, failure diagnostics to `errors.jsonl`, and full transcripts to `traces/<id>_rep<k>.json`.
2. **[`report/build-report-lite.py`](file:///Applications/antigravity/gemini-eval/report/build-report-lite.py)** (replaces `build-report-lite.mjs`):
   - Reads `_state.json`, `baseline/`, and `v1..vN/` directories.
   - Writes `trajectory/scores.tsv` and a self-contained static `report.html` with matched-pair `test` deltas, `train - test` overfitting gap warnings, and click-through trace links.
3. **[`example-migration/run-eval.py`](file:///Applications/antigravity/gemini-eval/example-migration/run-eval.py)** (replaces `run-eval.mjs`):
   - Supports both live `google-genai` API execution and offline deterministic simulation (`SIMULATE=1`).

---

## 6. Public Skill References & Gap-Filling Files

Where `anthropic-eval/` referenced sibling files from `anthropics/skills/skills/claude-api/`, `gemini-eval/` now references both **official Google public skills** on GitHub and **local gap-filling references** in [`gemini-eval/references/`](file:///Applications/antigravity/gemini-eval/references):

| `anthropic-eval/` Reference | Official Google Public Skill Linked | Local Gap-Filling File in `gemini-eval/references/` |
| :--- | :--- | :--- |
| `skills/claude-api/SKILL.md` (Models, SDK setup, token pricing) | [`google-gemini/gemini-skills`: `skills/gemini-api-dev/SKILL.md`](https://github.com/google-gemini/gemini-skills/blob/main/skills/gemini-api-dev/SKILL.md) & [`google/skills`: `skills/cloud/gemini-api/SKILL.md`](https://github.com/google/skills/blob/main/skills/cloud/gemini-api/SKILL.md) | [`references/pricing.md`](file:///Applications/antigravity/gemini-eval/references/pricing.md) (Full $/1M token rate card for Gemini 4 / 3.8 / 3.5 / 2.5 + cross-family judges, `cost_usd` formula, and `_state.json` `prices` snippet) |
| `skills/claude-api/shared/model-migration.md` & `shared/prompt-audit.md` | [`google-gemini/gemini-skills`: `skills/gemini-api-dev/references/migration.md`](https://github.com/google-gemini/gemini-skills/blob/main/skills/gemini-api-dev/references/migration.md) | [`references/prompt-audit.md`](file:///Applications/antigravity/gemini-eval/references/prompt-audit.md) (Pre-migration `GenerateContentConfig` audit, `temperature=1.0` default, `thinking_level` vs. `thinking_budget`, and 5-part prompt-cruft audit) |
| `skills/claude-api/shared/cost-optimization.md` & `shared/prompt-caching.md` | [`google/skills`: `skills/cloud/gemini-api/references/advanced_features.md`](https://github.com/google/skills/blob/main/skills/cloud/gemini-api/references/advanced_features.md) (§Content Caching, §Batch Prediction, §Thinking) | [`references/cost-optimization.md`](file:///Applications/antigravity/gemini-eval/references/cost-optimization.md) (7-step ordered no-eval cost checklist + implicit/explicit context caching invalidation diagnostics) |
