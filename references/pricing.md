# Gemini & Cross-Family Model Pricing Reference (`pricing.md`)

> **Last Verified:** `2026-11-18` (from public Google Cloud Vertex AI / Agent Platform & Gemini API pricing documentation). Always verify live SKUs before locking large production budgets, especially around promotional transition dates (**Dec 1, 2026** for Argon/Carbon; **Jan 1, 2027** for Gemini 3.8 Flash).

This reference fills the token-pricing gap in Google's public [`skills/gemini-api-dev/SKILL.md`](https://github.com/google-gemini/gemini-skills/blob/main/skills/gemini-api-dev/SKILL.md) and [`skills/cloud/gemini-api/SKILL.md`](https://github.com/google/skills/blob/main/skills/cloud/gemini-api/SKILL.md). Use these rates when computing pilot cost projections (`build-eval.md` §Before the first paid call), hill-climb loop budgets (`eval-hillclimb.md` Step 2), and `_state.json.prices` entries.

---

## Key Billing Rules (Vertex AI & Gemini API)

- **Thinking / Reasoning Tokens:** Output rates apply to **both** visible response tokens (`candidatesTokenCount` / `output_tokens`) and internal thinking tokens (`thoughtsTokenCount` / `thinking_tokens`).
- **Context Window Pricing (`<=200k` vs. Flat `1M`):**
  - **Flat across full 1M window (NO `>200k` surcharge cliff):** `gemini-4-carbon`, `gemini-4-argon`, `gemini-4-neon`, `gemini-4-hydrogen`, `gemini-3.8-flash`, and `gemini-2.5-flash`.
  - **Tiered at `200k` tokens (`>200k` surcharge applies to entire request):** `gemini-3.1-pro-preview` and `gemini-2.5-pro`.
- **Global vs. Non-Global (Regional) Endpoints:** Rates below are for **Global** endpoints. Regional/non-global endpoints on Vertex AI typically carry a **`~10%` surcharge** (e.g., Hydrogen `$1.65` in / `$8.25` out; Carbon/Argon intro `$2.20` in / `$11.00` out).
- **Batch API & Flex Inference (`service_tier="flex"`):** **`50%` off** standard pay-as-you-go input/output rates (Batch: up to 24h async SLA; Flex: synchronous best-effort off-peak capacity).
- **Priority PayGo:** Latency-sensitive priority lanes on Vertex AI scale up (~`1.8×` standard rate).
- **Context Caching:**
  - **Gemini 4 family:** Uses **implicit caching** natively (`4,096`-token minimum prefix threshold, **`95%` off** active input rate, no separate explicit storage fee).
  - **Gemini 3.8 Flash & older families:** **`90%` off** base input rate for cached reads (implicit caching incurs no storage fee; explicit caching incurs hourly storage fees).
- **Failed Requests:** Only successful `200` responses are billed on Vertex AI (`4xx`/`5xx` failed/blocked requests are free).

---

## 1A. Current Generation: Gemini 4 Family & Gemini 3.8 Flash (Global, USD per 1M Tokens)

> [!IMPORTANT]
> **Introductory vs. Standard Rates:** Always model **BOTH** the active introductory rate (for today's eval spend) **and** the upcoming standard rate (for 2027 production ROI)! Notice that starting **Jan 1, 2027**, `gemini-3.8-flash`'s standard rate (`$1.50 / $7.50`) equals **`gemini-4-hydrogen`'s flat rate (`$1.50 / $7.50`)**.

| Model ID | Rate Tier & Effective Window | Input (Global / Non-Global) | Output + Thinking (Global / Non-Global) | Cached Input Read (Discount) | Cache Storage ($/1M tok/hr) | Batch / Flex (`50%` off Global) | Context Pricing |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`gemini-4-carbon`** *(Frontier deep reasoning)* | **Introductory** *(through Nov 30, 2026)* | **`$2.00`** / `$2.20` | **`$10.00`** / `$11.00` | **`$0.10`** (`95%` off; `$0.11` regional) | Implicit only (`$0`) | `$1.00` in / `$5.00` out | Flat `1M` |
| **`gemini-4-carbon`** | **Standard** *(effective Dec 1, 2026)* | **`$4.00`** / `$4.40` | **`$20.00`** / `$22.00` | **`$0.20`** (`95%` off; `$0.22` regional) | Implicit only (`$0`) | `$2.00` in / `$10.00` out | Flat `1M` |
| **`gemini-4-argon`** *(Frontier reasoning & coding)* | **Introductory** *(through Nov 30, 2026)* | **`$2.00`** / `$2.20` | **`$10.00`** / `$11.00` | **`$0.10`** (`95%` off; `$0.11` regional) | Implicit only (`$0`) | `$1.00` in / `$5.00` out | Flat `1M` |
| **`gemini-4-argon`** | **Standard** *(effective Dec 1, 2026)* | **`$4.00`** / `$4.40` | **`$20.00`** / `$22.00` | **`$0.20`** (`95%` off; `$0.22` regional) | Implicit only (`$0`) | `$2.00` in / `$10.00` out | Flat `1M` |
| **`gemini-4-neon`** *(Balanced mid-tier)* | **Standard (Flat)** *(no intro schedule)* | **`$3.00`** / `$3.30` | **`$15.00`** / `$16.50` | **`$0.15`** (`95%` off; `$0.165` regional) | Implicit only (`$0`) | `$1.50` in / `$7.50` out | Flat `1M` |
| **`gemini-4-hydrogen`** *(Fast agentic execution)* | **Standard (Flat)** *(no intro schedule)* | **`$1.50`** / `$1.65` | **`$7.50`** / `$8.25` | **`$0.075`** (`95%` off; `$0.0825` regional) | Implicit only (`$0`) | `$0.75` in / `$3.75` out | Flat `1M` |
| **`gemini-3.8-flash`** *(Long-horizon coding/Flash)* | **Introductory** *(through Dec 31, 2026)* | **`$0.75`** | **`$3.75`** | **`$0.075`** (`90%` off) | `$0.50` *(explicit)* | `$0.375` in / `$1.875` out | Flat `1M` |
| **`gemini-3.8-flash`** | **Standard** *(effective Jan 1, 2027)* | **`$1.50`** | **`$7.50`** | **`$0.15`** (`90%` off) | `$1.00` *(explicit)* | `$0.75` in / `$3.75` out | Flat `1M` |

---

## 1B. Previous Gemini 3.x & Legacy Gemini 2.5 Models (Global, USD per 1M Tokens)

> **Note:** There is no official `gemini-3.5-pro` SKU deployed on Vertex AI — the active 3.x Pro SKU is `gemini-3.1-pro-preview`.

| Model ID | Tier / Role | Input (`<=200k` / `>200k`) | Output + Thinking (`<=200k` / `>200k`) | Cached Input Read (`<=200k` / `>200k`) | Cache Storage ($/1M tok/hr) | Batch API (`50%` off, `<=200k`) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `gemini-3.5-flash` | Multimodal & Tool Use | `$1.50` *(flat)* | `$9.00` *(flat)* | `$0.15` (`90%` off) | Explicit/implicit | `$0.75` in / `$4.50` out |
| `gemini-3.5-flash-lite` | High-Volume / Low-Latency | `$0.30` (`$0.33` regional) | `$2.50` (`$2.75` regional) | `$0.03` (`90%` off) | Explicit/implicit | `$0.15` in / `$1.25` out |
| `gemini-3.1-pro-preview` | Previous Pro Reasoning | `$2.00` / `$4.00` | `$12.00` / `$18.00` | `$0.20` / `$0.40` (`90%` off) | Explicit/implicit | `$1.00` in / `$6.00` out *(or `$2.00`/`$9.00` `>200k`)* |
| `gemini-3.1-flash-lite` | Lightweight Classification & Extraction | `$0.25` *(flat)* | `$1.50` *(flat)* | `$0.025` (`90%` off) | Explicit/implicit | `$0.125` in / `$0.75` out |
| `gemini-3-flash-preview` | Gemini 3 Flash Baseline | `$0.50` *(`$1.00` audio)* | `$3.00` *(flat)* | `$0.05` (`90%` off) | Explicit/implicit | `$0.25` in / `$1.50` out |
| `gemini-2.5-pro` *(legacy)* | Legacy Pro Baseline | `$1.25` / `$2.50` | `$10.00` / `$15.00` | `$0.125` / `$0.25` (`90%` off) | `$4.50` *(explicit)* | `$0.625` in / `$5.00` out |
| `gemini-2.5-flash` *(legacy)* | Legacy Flash Baseline | `$0.30` *(flat)* | `$2.50` *(flat)* | `$0.03` (`90%` off) | Explicit/implicit | `$0.15` in / `$1.25` out |
| `gemini-2.5-flash-lite` *(legacy)* | Legacy Lite Baseline | `$0.10` *(flat)* | `$0.40` *(flat)* | `$0.01` (`90%` off) | `$1.00` *(explicit)* | `$0.05` in / `$0.20` out |

---

## 2. Cross-Family Judge Models (Vertex AI Model Garden / Direct API)

When judging a Gemini model-under-test with a non-Gemini judge (or vice versa) to avoid self-preference bias (`build-eval.md` Step 2):

| Model ID | Role | Input ($/1M) | Output ($/1M) | Cache Read ($/1M) | Cache Write ($/1M) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `claude-opus-4-6` / `claude-opus-4-5` | Frontier Cross-Family Judge | `$5.00` | `$25.00` | `$0.50` | `$6.25` |
| `claude-sonnet-4-6` / `claude-sonnet-4-5` | Balanced Cross-Family Judge | `$3.00` | `$15.00` | `$0.30` | `$3.75` |
| `claude-haiku-4-5` | Fast / Cheap Cross-Family PR Judge | `$1.00` | `$5.00` | `$0.10` | `$1.25` |

*(Regional/multi-region Vertex Model Garden endpoints may add a minor surcharge.)*

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

## 4. Ready-to-Paste `_state.json` `prices` Maps

Because **`gemini-4-carbon` / `gemini-4-argon`** (`Dec 1, 2026`) and **`gemini-3.8-flash`** (`Jan 1, 2027`) double from introductory to standard pricing, choose the block that matches your use case — **and show both when projecting customer production budgets**.

### Option A: Active Introductory / Promotional Rates (Global, valid Nov 2026)

*Use for actual eval spend incurred before **Nov 30, 2026** (Argon/Carbon) and **Dec 31, 2026** (3.8 Flash):*

```json
"prices": {
  "gemini-4-carbon": {"in": 2.00, "out": 10.00, "cache_read": 0.10},
  "gemini-4-argon": {"in": 2.00, "out": 10.00, "cache_read": 0.10},
  "gemini-4-neon": {"in": 3.00, "out": 15.00, "cache_read": 0.15},
  "gemini-4-hydrogen": {"in": 1.50, "out": 7.50, "cache_read": 0.075},
  "gemini-3.8-flash": {"in": 0.75, "out": 3.75, "cache_read": 0.075},
  "gemini-3.5-flash": {"in": 1.50, "out": 9.00, "cache_read": 0.15},
  "gemini-3.5-flash-lite": {"in": 0.30, "out": 2.50, "cache_read": 0.03},
  "gemini-3.1-pro-preview": {"in": 2.00, "out": 12.00, "cache_read": 0.20},
  "gemini-3.1-flash-lite": {"in": 0.25, "out": 1.50, "cache_read": 0.025},
  "gemini-3-flash-preview": {"in": 0.50, "out": 3.00, "cache_read": 0.05},
  "gemini-2.5-pro": {"in": 1.25, "out": 10.00, "cache_read": 0.125},
  "gemini-2.5-flash": {"in": 0.30, "out": 2.50, "cache_read": 0.03},
  "gemini-2.5-flash-lite": {"in": 0.10, "out": 0.40, "cache_read": 0.01},
  "claude-opus-4-6": {"in": 5.00, "out": 25.00, "cache_read": 0.50},
  "claude-opus-4-5": {"in": 5.00, "out": 25.00, "cache_read": 0.50},
  "claude-sonnet-4-6": {"in": 3.00, "out": 15.00, "cache_read": 0.30},
  "claude-sonnet-4-5": {"in": 3.00, "out": 15.00, "cache_read": 0.30},
  "claude-haiku-4-5": {"in": 1.00, "out": 5.00, "cache_read": 0.10}
}
```

### Option B: Standard / Post-Introductory Rates (Global, for Dec 2026 / 2027 Production Budgeting)

*Reflects **Dec 1, 2026** standard rates for Argon/Carbon (`$4.00/$20.00`) and **Jan 1, 2027** standard rate for `gemini-3.8-flash` (`$1.50/$7.50`):*

```json
"prices": {
  "gemini-4-carbon": {"in": 4.00, "out": 20.00, "cache_read": 0.20},
  "gemini-4-argon": {"in": 4.00, "out": 20.00, "cache_read": 0.20},
  "gemini-4-neon": {"in": 3.00, "out": 15.00, "cache_read": 0.15},
  "gemini-4-hydrogen": {"in": 1.50, "out": 7.50, "cache_read": 0.075},
  "gemini-3.8-flash": {"in": 1.50, "out": 7.50, "cache_read": 0.15},
  "gemini-3.5-flash": {"in": 1.50, "out": 9.00, "cache_read": 0.15},
  "gemini-3.5-flash-lite": {"in": 0.30, "out": 2.50, "cache_read": 0.03},
  "gemini-3.1-pro-preview": {"in": 2.00, "out": 12.00, "cache_read": 0.20},
  "gemini-3.1-flash-lite": {"in": 0.25, "out": 1.50, "cache_read": 0.025},
  "gemini-3-flash-preview": {"in": 0.50, "out": 3.00, "cache_read": 0.05},
  "gemini-2.5-pro": {"in": 1.25, "out": 10.00, "cache_read": 0.125},
  "gemini-2.5-flash": {"in": 0.30, "out": 2.50, "cache_read": 0.03},
  "gemini-2.5-flash-lite": {"in": 0.10, "out": 0.40, "cache_read": 0.01},
  "claude-opus-4-6": {"in": 5.00, "out": 25.00, "cache_read": 0.50},
  "claude-opus-4-5": {"in": 5.00, "out": 25.00, "cache_read": 0.50},
  "claude-sonnet-4-6": {"in": 3.00, "out": 15.00, "cache_read": 0.30},
  "claude-sonnet-4-5": {"in": 3.00, "out": 15.00, "cache_read": 0.30},
  "claude-haiku-4-5": {"in": 1.00, "out": 5.00, "cache_read": 0.10}
}
```
