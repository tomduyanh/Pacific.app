# What Pacific needs from the model endpoint

Pacific talks to its model provider in the Gemini REST format
(`backend/embed.py`). An endpoint that implements the three calls below works
with no code changes: set `GEMINI_BASE` to its base URL. If the endpoint uses
its own format instead, `benchmarks/adapter.py` translates. Only its two
`upstream_*` functions need filling in.

All calls are `POST {base}/{model}:{method}` with a JSON body. The key arrives
in the `x-goog-api-key` header. Pacific retries 408, 429, 500, 502, 503 and
504 twice with backoff (0.4 s, 0.8 s), so those statuses should mean
"transient".

## 1. `embedContent`: one embedding

```json
{"model": "models/embedding",
 "content": {"parts": [{"text": "..."}]},
 "taskType": "RETRIEVAL_DOCUMENT"}
```
→ `{"embedding": {"values": [0.01, -0.2, ...]}}`

## 2. `batchEmbedContents`: up to 100 embeddings

```json
{"requests": [<embedContent body>, ...]}
```
→ `{"embeddings": [{"values": [...]}, ...]}` in request order.

Every vector must have the same length (`EMBED_DIM`). Startup embeds the whole
context pool through this call, so it sets cold-start time.

## 3. `generateContent`: text and vision

Text (query expansion, task summaries, at most 200 output tokens):
```json
{"contents": [{"parts": [{"text": "..."}]}],
 "generationConfig": {"maxOutputTokens": 200}}
```

Vision (live screen analysis, at most 1024 output tokens):
```json
{"contents": [{"parts": [
   {"text": "<prompt>"},
   {"inline_data": {"mime_type": "image/jpeg", "data": "<base64>"}}]}],
 "generationConfig": {"maxOutputTokens": 1024}}
```

→ `{"candidates": [{"content": {"parts": [{"text": "..."}]}}]}`

For live screen analysis the returned text must contain a JSON object with
string fields `commentary` and `screen_analysis` (plus `significant_change`,
`novelty`, `visual_change`, `filegram_events`). The prompt
(`LIVE_SCREEN_PROMPT` in `backend/vlm_screen.py`) asks for exactly this. A reply
missing either string field is rejected and counts as a failed frame.

## Latency budget

A live frame is abandoned after 20 s (`LIVE_SCREEN_MAX_LATENCY_SEC`), and the
capture loop targets one frame every 5 s. Vision latency well under 5 s keeps
the loop at its intended cadence.

## Checking an endpoint

```
BENCH_API_KEY=... python -m benchmarks.preflight
```
calls each method through Pacific's own client code and reports pass/fail and
latency.
