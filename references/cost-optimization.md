# Gemini Cost Optimization & Context Caching Hygiene (`cost-optimization.md`)

This reference complements [`skills/cloud/gemini-api/references/advanced_features.md`](https://github.com/google/skills/blob/main/skills/cloud/gemini-api/references/advanced_features.md) (`google/skills`) by providing:
1. The **ordered no-eval cost checklist** when the user wants to cut spend without running an eval hill-climb (`eval-hillclimb.md` Step 2, `cost-hillclimb.md` intro).
2. The **context caching health & invalidation diagnostics** required before and during `cost-hillclimb.md` Step 0 and Step 2.

---

## Part 1: Ordered No-Eval Cost Checklist

When you **do not** have an eval to detect quality regressions, apply cost levers from **lowest quality risk** to **highest quality risk** (`caching -> input trim -> agent-loop hygiene -> output -> batch -> thinking level -> model last`):

1. **Context Caching (Zero quality impact, up to 75% input savings on cached prefixes)**
   - **Implicit Caching** is enabled by default on `gemini-3.8-flash` and `gemini-4-pro` (`gemini-4-argon`). Ensure static content (system instructions, reference docs, few-shot examples, tool declarations) is placed at the **very beginning** of the request so consecutive requests share an identical token prefix.
   - **Explicit Caching** (`client.caches.create` with `types.CreateCachedContentConfig`): Use when you want guaranteed cache hits across distributed workers or need a known TTL (`ttl="3600s"`) on large static contexts (>32k tokens).
2. **Input & Tool-Result Trimming (Low quality risk)**
   - Bound raw tool outputs before appending them to conversation history (e.g., strip boilerplate HTML/DOM nodes, paginate search results to top-K snippets, cap log/stdout dumps to head + tail lines).
   - Drop or summarize stale tool-result payloads from earlier turns in long multi-turn agent trajectories once the agent has extracted the needed facts.
3. **Agent-Loop Hygiene (Low-to-medium quality risk)**
   - Allow **parallel function calling** (the default in `google-genai`) rather than forcing sequential single-tool turns.
   - Remove prompt instructions that force redundant verification rounds (e.g., *"Always re-read the entire file after editing"* or *"Run the full test suite after every single file change"*).
4. **Output & Structured Schema Conciseness (Medium quality risk)**
   - When using `response_mime_type="application/json"` with `response_schema`, remove verbose "chain-of-thought" or `"reasoning"` string fields from the JSON schema if native `ThinkingConfig` is already active — paying for reasoning in both `thoughts_token_count` and `candidates_token_count` double-bills output tokens.
   - Use concise enum keys and flat schemas where possible.
5. **Batch Prediction API (`50%` discount on input and output)**
   - For offline workloads, backfills, dataset labeling, and non-interactive eval passes, use `client.batches.create` (see [`skills/cloud/gemini-api/references/advanced_features.md` §Batch Prediction](https://github.com/google/skills/blob/main/skills/cloud/gemini-api/references/advanced_features.md)) for a flat 50% discount.
6. **Thinking / Reasoning Level Tuning (`ThinkingConfig`)**
   - Adjust `thinking_level` in `types.ThinkingConfig(thinking_level=...)`:
     - `gemini-4-pro` defaults to `HIGH`. Step down to `MEDIUM` or `LOW` for routine coding/extraction tasks.
     - `gemini-3.8-flash` defaults to `MEDIUM`. Step down to `LOW` or `MINIMAL` for classification, routing, or simple formatting.
     - `gemini-3.5-flash-lite` defaults to `MINIMAL`.
   - Because thinking tokens (`thoughts_token_count`) are billed at the output rate, stepping down one notch typically cuts total output billing by 30%–65%.
7. **Model Tier Downshift (Highest quality risk without an eval — always last)**
   - Only swap `gemini-4-pro` $\rightarrow$ `gemini-3.8-flash` or `gemini-3.8-flash` $\rightarrow$ `gemini-3.5-flash-lite` last when operating without an eval. (When you *do* have an eval, use the `cost-hillclimb.md` Step 2 staircase walk instead.)

---

## Part 2: Context Caching Health & Invalidation Diagnostics (`cost-hillclimb.md` Step 0)

Silent cache invalidation is the #1 cause of distorted cost measurements during an eval or migration. Check these rules before round 1 and after **every** model or `thinking_config` change:

### 1. How to Verify Cache Health in `usage_metadata`
Inspect `response.usage_metadata` on multi-turn or repeated-prefix requests:
- `prompt_token_count`: Total input tokens billed (cached + uncached).
- `cached_content_token_count`: Tokens matched against implicit or explicit cache.
- **Healthy cache signal**: On turn $k \ge 2$ of an agent loop (or request $k \ge 2$ sharing a large system prompt), `cached_content_token_count` should be $> 0$ and grow monotonically across turns in the same conversation as prior turns join the cached prefix.

### 2. Common Silent Cache Invalidators
If `cached_content_token_count` unexpectedly drops to `0`:
- **Dynamic content in the system instruction prefix**: Putting `Current time: 2026-10-27T15:35:00Z`, a random `request_id`, or per-user metadata at the *top* of `system_instruction` invalidates the entire prefix downstream. Move dynamic per-request variables to the **end** of the `system_instruction` or into the first `user` message turn.
- **Non-deterministic tool or schema ordering**: Building `tools=[...]` from a Python `set` or dynamically unsorted dictionary changes the serialized declaration order between processes, busting the prefix cache. Sort tool declarations deterministically.
- **Model ID or `thinking_config` changes mid-session**: Context caches are isolated **per model** (`gemini-4-pro` and `gemini-3.8-flash` never share a cache), and changing `thinking_config` mid-conversation can bust prefix reuse. Keep `model` and `thinking_config` fixed across all turns of a conversation.
- **Cold-cache distortion in `cost-hillclimb.md` Step 2**: The first request on a newly probed `(model, thinking_level)` cell is always cache-cold. Either run a warm-up request when using explicit/implicit caching or compare cells on matched cache states (`cost-hillclimb.md` §Per-cell honesty rules).

### 3. Explicit Caching Snippet (`google-genai`)
When implicit caching is noisy across concurrent eval workers, pin the static system instruction and tools with explicit caching:

```python
from google import genai
from google.genai import types

client = genai.Client()

cache = client.caches.create(
    model="gemini-3.8-flash",
    config=types.CreateCachedContentConfig(
        display_name="eval_static_prefix",
        system_instruction=STATIC_SYSTEM_PROMPT,
        tools=STATIC_TOOLS,
        ttl="3600s",
    ),
)

response = client.models.generate_content(
    model="gemini-3.8-flash",
    contents=case_user_prompt,
    config=types.GenerateContentConfig(
        cached_content=cache.name,
        thinking_config=types.ThinkingConfig(thinking_level="LOW"),
    ),
)
```
