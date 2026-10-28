# Pre-Migration Prompt & Request Config Audit (`prompt-audit.md`)

This reference complements [`skills/gemini-api-dev/references/migration.md`](https://github.com/google-gemini/gemini-skills/blob/main/skills/gemini-api-dev/references/migration.md) (`google-gemini/gemini-skills`) by providing the **prompt-cruft and request-parameter audit checklist** required in `cost-hillclimb.md` Step 1 and `eval-hillclimb.md` Step 0.

Why this audit comes before any model comparison: newer Gemini models (`gemini-3.8-flash` and `gemini-4-pro` / `gemini-4-argon`) follow instructions **much more literally** than legacy models (`gemini-1.5-*`, `gemini-2.0-*`, `gemini-2.5-*`). Compensatory prompt workarounds written to force older models to behave will cause newer models to over-think, over-call tools, or fail schema validation.

---

## 1. Request Configuration Audit (`GenerateContentConfig`)

Before running baseline vs. candidate comparisons, audit every API call in the flow for legacy parameters:

| Legacy Pattern | Problem on Gemini 3.8 / Gemini 4 | Modern Replacement (`google-genai`) |
| :--- | :--- | :--- |
| `import google.generativeai as genai` | Deprecated legacy SDK; lacks `ThinkingConfig` levels and unified Vertex/Developer client. | `from google import genai` and `from google.genai import types` (`google-genai >= 2.30.1`). |
| Fixed integer `thinking_budget=16384` (or `thinking_budget=0` on Pro) | Legacy 2.5 parameter; `gemini-4-pro` cannot disable thinking (`0` errors or is ignored), and fixed high budgets inflate cost on easy cases. | Use `types.ThinkingConfig(thinking_level="LOW" \| "MEDIUM" \| "HIGH" \| "MINIMAL")` so the model scales reasoning dynamically within the tier. |
| `temperature=0.0` (or `0.1`–`0.3`) carried over from Gemini 1.5/2.0 | Degrades reasoning quality and causes repetitive tool-call loops on Gemini 3+ / 4 thinking models. | Remove the override or set `temperature=1.0` (the recommended default for all Gemini 3.8 and Gemini 4 models). |
| Prose-only JSON enforcement (`"Respond ONLY with valid JSON, no ```json fences"`) | Brittle; models occasionally wrap JSON in markdown fences or leave unescaped quotes in explanation strings. | Set `response_mime_type="application/json"` and pass a Pydantic model or `types.Schema` to `response_schema`. |
| Hard-coded low `max_output_tokens` (e.g., `max_output_tokens=1024`) | `max_output_tokens` covers **both** `thoughts_token_count` and `candidates_token_count`. A low cap truncates visible output (`finishReason="MAX_TOKENS"`) when the model thinks. | Raise `max_output_tokens` to accommodate both thinking + output, or lower `thinking_level` (`"LOW"` / `"MINIMAL"`). |

---

## 2. Prompt Scaffolding & Token-Inflation Audit

Scan the system instruction, skill files, and tool descriptions for these five categories of dated prompt cruft:

### A. Visible Chain-of-Thought Rituals
- **Symptom**: Instructions like *"Before answering, always write out a `<thinking>` or `<step_by_step_plan>` block explaining your reasoning in detail."*
- **Why it hurts now**: `gemini-3.8-flash` and `gemini-4-pro` already perform native reasoning (`thoughts_token_count`). Forcing a second visible CoT block doubles output token spend and latency without improving accuracy.
- **Fix**: Delete manual `<thinking>` / step-by-step output rituals when native thinking is enabled.

### B. Turn-Inflating Tool Rituals
- **Symptom**: Rules written for older models that lost track of state, such as:
  - *"First write a plan file to disk before running any command."*
  - *"After every edit to a file, read the entire file back to verify your edit."*
  - *"Run the full test suite after every single edit."*
- **Why it hurts now**: `gemini-3.8-flash` and `gemini-4-pro` follow these literally on every turn, multiplying agentic turns and re-billing the entire context prefix on each extra round.
- **Fix**: Replace mandatory per-step rituals with outcome-based guidance (*"Verify your changes by running the relevant tests once your edits are complete"*).

### C. Conflicting Output-Format Instructions
- **Symptom**: System prompt says *"Wrap your JSON in a ` ```json ` code block"* while the API config sets `response_mime_type="application/json"`, or system prompt demands a rigid markdown template that contradicts the grader's parser.
- **Why it hurts now**: Creates format-check failures (`0` scores) that look like capability regressions.
- **Fix**: Align prompt formatting instructions with `response_schema` and the grader's exact parser.

### D. Over-Defensive Negative Constraints & Anti-Laziness Shouting
- **Symptom**: Repeated ALL-CAPS blocks (*"CRITICAL: DO NOT BE LAZY! NEVER OMIT CODE! ALWAYS CHECK 3 TIMES!"*) added over months of patching older models.
- **Why it hurts now**: Causes over-verbosity, refusal over-triggering, or unnecessary tool calls on simple queries.
- **Fix**: Consolidate duplicate constraints into a single, neutral, specific rule.

### E. Hard-Coded Model Identity or Cutoff Claims
- **Symptom**: System prompt states *"You are Gemini 1.5 Pro with a knowledge cutoff of..."*
- **Why it hurts now**: Confuses self-knowledge or tool-search triggers when running on `gemini-3.8-flash` or `gemini-4-pro`.
- **Fix**: Use model-agnostic role descriptions.

---

## 3. Running the Step 1 Audit Probe (`cost-hillclimb.md` Step 1)

1. **Fix broken/legacy API config first** (e.g., `google-genai` SDK, `thinking_level`, `temperature=1.0`, sufficient `max_output_tokens`) so the new model runs cleanly.
2. **Diff the prompt cleanup separately**: Save the cleaned prompt as `v1` (with `change.md` listing the removed cruft and `change.patch` showing the exact diff) and run it on the eval before starting the Step 2 `model × thinking_level` staircase walk.
3. **Check the engagement census (`cost-hillclimb.md` Step 3)**: Verify in the `traces/` files that removing a ritual actually reduced `tool_calls` or `output_tokens` / `thinking_tokens`.
