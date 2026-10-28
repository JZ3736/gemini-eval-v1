# Gemini & Cross-Family Model Pricing Reference (`pricing.md`)

This reference fills the token-pricing gap in Google's public [`skills/gemini-api-dev/SKILL.md`](https://github.com/google-gemini/gemini-skills/blob/main/skills/gemini-api-dev/SKILL.md) and [`skills/cloud/gemini-api/SKILL.md`](https://github.com/google/skills/blob/main/skills/cloud/gemini-api/SKILL.md). Use these rates when computing pilot cost projections (`build-eval.md` §Before the first paid call), hill-climb loop budgets (`eval-hillclimb.md` Step 2), and `_state.json.prices` entries.

---

## 1. Gemini Model Family Rate Card (USD per 1M Tokens)

> **Note:** Output prices apply to **both** visible response tokens (`candidatesTokenCount` / `output_tokens`) and reasoning tokens (`thoughtsTokenCount` / `thinking_tokens`). Prompts exceeding 200k input tokens are billed at the `> 200k` long-context tier across all tokens in that request.

| Model ID | Tier / Role | Input (`<=200k` / `>200k`) | Output + Thinking (`<=200k` / `>200k`) | Cached Input Read (`<=200k` / `>200k`) | Cache Storage ($/1M tok/hr) | Batch API (`50%` off) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `gemini-4-pro` (`gemini-4-argon`) | Frontier Reasoning & Coding | `$1.25` / `$2.50` | `$10.00` / `$15.00` | `$0.3125` / `$0.625` | `$4.50` | `$0.625` in / `$5.00` out |
| `gemini-3.8-flash` | High-Speed Reasoning & Agentic Workhorse | `$0.15` / `$0.30` | `$0.60` / `$1.20` | `$0.0375` / `$0.075` | `$1.00` | `$0.075` in / `$0.30` out |
| `gemini-3.5-pro` | General Pro Reasoning | `$1.25` / `$2.50` | `$10.00` / `$15.00` | `$0.3125` / `$0.625` | `$4.50` | `$0.625` in / `$5.00` out |
| `gemini-3.5-flash` | Fast Multimodal & Tool Use | `$0.15` / `$0.30` | `$0.60` / `$1.20` | `$0.0375` / `$0.075` | `$1.00` | `$0.075` in / `$0.30` out |
| `gemini-3.5-flash-lite` | High-Volume / Low-Latency | `$0.075` / `$0.15` | `$0.30` / `$0.60` | `$0.01875` / `$0.0375` | `$1.00` | `$0.0375` in / `$0.15` out |
| `gemini-3.1-flash-lite` | Ultra-Cheap Classification & Extraction | `$0.075` / `$0.15` | `$0.30` / `$0.60` | `$0.01875` / `$0.0375` | `$1.00` | `$0.0375` in / `$0.15` out |
| `gemini-2.5-pro` *(legacy)* | Legacy Pro Baseline | `$1.25` / `$2.50` | `$10.00` / `$15.00` | `$0.3125` / `$0.625` | `$4.50` | `$0.625` in / `$5.00` out |
| `gemini-2.5-flash` *(legacy)* | Legacy Flash Baseline | `$0.15` / `$0.30` | `$0.60` / `$1.20` | `$0.0375` / `$0.075` | `$1.00` | `$0.075` in / `$0.30` out |
| `gemini-2.5-flash-lite` *(legacy)* | Legacy Lite Baseline | `$0.075` / `$0.15` | `$0.30` / `$0.60` | `$0.01875` / `$0.0375` | `$1.00` | `$0.0375` in / `$0.15` out |

---

## 2. Cross-Family Judge Models (Vertex AI Model Garden / Direct API)

When judging a Gemini model-under-test with a non-Gemini judge (or vice versa) to avoid self-preference bias (`build-eval.md` Step 2):

| Model ID | Role | Input ($/1M) | Output ($/1M) | Cache Read ($/1M) | Cache Write ($/1M) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `claude-opus-4-6` / `claude-opus-4-5` | Frontier Cross-Family Judge | `$5.00` | `$25.00` | `$0.50` | `$6.25` |
| `claude-sonnet-4-6` / `claude-sonnet-4-5` | Balanced Cross-Family Judge | `$3.00` | `$15.00` | `$0.30` | `$3.75` |
| `claude-haiku-4-5` | Fast / Cheap Cross-Family PR Judge | `$1.00` | `$5.00` | `$0.10` | `$1.25` |

---

## 3. Exact `cost_usd` Derivation Formula

In the Google GenAI SDK (`google-genai`) and Vertex AI `generateContent`, `response.usage_metadata` reports:
- `prompt_token_count`: **Total** input tokens (includes `cached_content_token_count`).
- `cached_content_token_count`: Portion of `prompt_token_count` served from implicit or explicit context cache.
- `candidates_token_count`: Visible output tokens.
- `thoughts_token_count`: Internal reasoning tokens (billed at the output token rate).

When normalizing into `results.jsonl`:
```python
cached_in = usage_metadata.cached_content_token_count or 0
total_in = usage_metadata.prompt_token_count or 0
uncached_in = max(0, total_in - cached_in)
out_tokens = usage_metadata.candidates_token_count or 0
think_tokens = usage_metadata.thoughts_token_count or 0

usage = {
    "input_tokens": uncached_in,
    "output_tokens": out_tokens,
    "thinking_tokens": think_tokens,
    "cache_read_input_tokens": cached_in,
    "cache_creation_input_tokens": 0,
}
```

Per-row dollar cost (`cost_usd`):
$$\text{cost\_usd} = \frac{\text{uncached\_in} \times P_{\text{in}} + \text{cached\_in} \times P_{\text{cache\_read}} + (\text{out\_tokens} + \text{think\_tokens}) \times P_{\text{out}}}{1,000,000}$$

If the eval is model-graded (`judge_model` and `judge_usage` present on the row), compute the judge call's cost with the same formula against `judge_model`'s rates and add both together.

---

## 4. Ready-to-Paste `_state.json` `prices` Map

Include this block in `.antigravity/hillclimb/<flow>/_state.json` so report builders can derive `cost_usd` across every model tier:

```json
"prices": {
  "gemini-4-pro": {"in": 1.25, "out": 10.0, "cache_read": 0.3125},
  "gemini-4-argon": {"in": 1.25, "out": 10.0, "cache_read": 0.3125},
  "gemini-3.8-flash": {"in": 0.15, "out": 0.60, "cache_read": 0.0375},
  "gemini-3.5-pro": {"in": 1.25, "out": 10.0, "cache_read": 0.3125},
  "gemini-3.5-flash": {"in": 0.15, "out": 0.60, "cache_read": 0.0375},
  "gemini-3.5-flash-lite": {"in": 0.075, "out": 0.30, "cache_read": 0.01875},
  "gemini-3.1-flash-lite": {"in": 0.075, "out": 0.30, "cache_read": 0.01875},
  "gemini-2.5-pro": {"in": 1.25, "out": 10.0, "cache_read": 0.3125},
  "gemini-2.5-flash": {"in": 0.15, "out": 0.60, "cache_read": 0.0375},
  "gemini-2.5-flash-lite": {"in": 0.075, "out": 0.30, "cache_read": 0.01875},
  "claude-opus-4-5": {"in": 5.00, "out": 25.00, "cache_read": 0.50},
  "claude-sonnet-4-5": {"in": 3.00, "out": 15.00, "cache_read": 0.30},
  "claude-haiku-4-5": {"in": 1.00, "out": 5.00, "cache_read": 0.10}
}
```
