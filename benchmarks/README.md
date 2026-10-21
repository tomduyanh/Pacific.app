# Pacific benchmarks

Two questions, one suite:

1. **Quality:** how much of the relevant context does Pacific get into a
   token budget, compared with simpler retrieval baselines?
2. **Performance:** how does the backend behave as the pool grows, under
   concurrent load, through long sessions, crashes and endpoint outages?

Every run works on a throwaway copy of the app. The repository's `data/` is
never modified.

## Setup

```
pip install -r requirements.txt -r benchmarks/requirements.txt
```

Python 3.12 is recommended. The pinned pydantic does not build on 3.13.

## Running

```
python -m benchmarks --provider mock --quick    # 3-minute harness check, no network
python -m benchmarks --provider endpoint        # the real run (~25 min)
```

`--provider` picks the model backend:

| Provider | What it measures |
|---|---|
| `mock` | Pacific's built-in offline mode. Zero-network compute floor. Quality numbers are **not meaningful** (placeholder embeddings). |
| `endpoint` | The custom model endpoint (see below). The real run. |
| `outage` | Endpoint configured but unreachable. Used by the stress `outage` phase, and usable with `run_quality` to see how far quality drops when embeddings silently fall back. |

Individual pieces:

```
python -m benchmarks.preflight                                  # endpoint compatibility check
python -m benchmarks.quality.run_quality --provider endpoint --pool-size 44 1000
python -m benchmarks.stress.run_stress --provider endpoint --phases scale soak
python -m benchmarks.report benchmarks/results/<run> --baseline benchmarks/results/baseline-mock
```

## Connecting the endpoint

1. Copy `benchmarks/endpoint.env.example` to `benchmarks/endpoint.env` and fill it in.
2. Set the key as an environment secret: `BENCH_API_KEY`.
3. For an OpenAI-compatible server such as vLLM, keep `BENCH_USE_ADAPTER=1` and
   set the `BENCH_UPSTREAM_*` model and URL settings. `adapter.py` translates
   Pacific's Gemini-format calls and turns Qwen3 thinking off. If the endpoint
   implements `ENDPOINT_SPEC.md` (Gemini format) itself, set
   `BENCH_USE_ADAPTER=0` and point `BENCH_GEMINI_BASE` at it.
   Pacific also needs an **embedding** model. A chat or vision model alone
   cannot supply one.
4. `python -m benchmarks.preflight` must pass before a full run.

## Quality method

- **Test set:** `quality/scenarios.json` has 69 scenarios: lookups, paraphrases,
  multi-document tasks, people questions, screen-only (ambient) context, budget
  traps, keyword traps, same question in different contexts, multi-turn drift,
  and off-topic or filler turns that should produce no suggestion. Each pool
  item is graded 2 (essential), 1 (useful) or 0.
- **Methods:**
  - Pacific, through its real API.
  - Hybrid BM25 + embedding: Pacific's base formula without its personal
    signals, history or query expansion. This is the ablation.
  - Embedding only.
  - BM25 only.
  - Most recently used.
  - Pool order.
  - Random.
  - Oracle: the best possible pick under the budget, computed from the labels.
- **Budgets:** 2k, 5k, 10k and 20k tokens. Every ranking is packed with the same
  first-fit packer, so methods are compared on what would actually go into the
  context window.
- **Metrics:**
  - % of oracle.
  - Gain-weighted recall.
  - Token precision: the share of the budget spent on relevant items.
  - Essential-item hit rate.
  - Budget-aware nDCG.
  - Gate false-suggest and false-silence rates.
  - Paired bootstrap 95% CIs for Pacific minus each baseline.
- **What the user sees:** Pacific shows its top 3 suggestions regardless of
  size. The report scores that set separately from the budget-packed ranking.

## Stress phases

| Phase | What it does |
|---|---|
| `scale` | Startup, message/rescore latency, response size, RSS and per-stage timings at 44 / 1k / 5k / 10k items |
| `concurrency` | Mixed message/rescore/state load at 1–16 parallel clients: throughput, tail latency, event-loop lag |
| `live` | Replays the dashboard's live-capture loop (`frontend/src/liveScreenLoop.js`): frame cadence, skips, vision latency, frame-to-ranking delay |
| `soak` | Live capture + messages + attach/dismiss over time: memory slope, state-file and cache growth, latency drift |
| `consistency` | Concurrent attach/dismiss/detach/message, then checks state invariants |
| `crash` | SIGKILL during state writes: is `session_state.json` still valid, and does the session survive restart? |
| `outage` | Endpoint unreachable: latency, success rate, live-frame behaviour |

Per-stage server timings come from `instrumented_app.py`, which wraps the app
from outside. Product code is not modified for measurement.

## Baseline

`results/baseline-mock/` is the offline run of the current code. Reports from
later runs show changes against it.
