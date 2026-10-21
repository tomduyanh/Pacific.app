# Pacific benchmark report: `baseline-mock`

## Retrieval quality under a token budget

### Pool of 44 items · provider `mock` · 69 scenarios

> **Not a quality result.** This run used hash-based placeholder embeddings with no semantic content, so every embedding-dependent method is handicapped. It validates the harness only.

**Headline (5k-token budget):** Pacific packs **70%** of the best achievable relevant context, vs **69%** for the strongest baseline (Hybrid (BM25 + embedding)): +1 pts (-4 to +7). Recall 69% vs 67%; relevant share of tokens 24% vs 25%.

% of oracle (95% CI). The oracle is the best possible pick under the same budget, computed from the labels.

| Method | 2k tokens | 5k tokens | 10k tokens | 20k tokens |
|---|---|---|---|---|
| Pacific | 55% (44–66) | 70% (62–78) | 76% (68–83) | 83% (76–89) |
| Hybrid (BM25 + embedding) | 62% (51–71) | 69% (60–78) | 78% (69–86) | 84% (76–90) |
| Embedding only | 8% (4–12) | 17% (10–25) | 30% (22–39) | 47% (38–56) |
| BM25 only | 60% (49–70) | 68% (59–77) | 76% (67–84) | 82% (74–89) |
| Most recent | 9% (5–13) | 21% (13–29) | 38% (28–47) | 68% (58–77) |
| Pool order | 8% (4–12) | 13% (8–18) | 28% (20–37) | 51% (41–60) |
| Random | 12% (10–14) | 18% (16–20) | 31% (29–34) | 50% (48–53) |

Pacific minus each baseline, % of oracle (`*` = 95% CI excludes zero):

| vs | 2k | 5k | 10k | 20k |
|---|---|---|---|---|
| Hybrid (BM25 + embedding) | -6 pts (-13 to -2) * | +1 pts (-4 to +7) | -2 pts (-6 to +3) | -1 pts (-6 to +5) |
| Embedding only | +48 pts (+36 to +59) * | +53 pts (+41 to +65) * | +46 pts (+35 to +56) * | +36 pts (+26 to +47) * |
| BM25 only | -4 pts (-9 to -1) * | +2 pts (-2 to +8) | +0 pts (-3 to +4) | +1 pts (-5 to +7) |
| Most recent | +46 pts (+35 to +57) * | +49 pts (+38 to +60) * | +38 pts (+27 to +50) * | +15 pts (+5 to +26) * |
| Pool order | +48 pts (+37 to +58) * | +58 pts (+47 to +68) * | +48 pts (+35 to +60) * | +32 pts (+21 to +43) * |
| Random | +43 pts (+32 to +53) * | +52 pts (+44 to +59) * | +45 pts (+36 to +53) * | +33 pts (+26 to +39) * |

At 5k tokens:

| Method | Recall | Token precision | Essential items hit | nDCG | Tokens used |
|---|---|---|---|---|---|
| Pacific | 69% | 24% | 78% | 61% | 4,953 |
| Hybrid (BM25 + embedding) | 67% | 25% | 78% | 63% | 4,962 |
| Embedding only | 15% | 6% | 15% | 10% | 4,948 |
| BM25 only | 66% | 24% | 75% | 62% | 4,966 |
| Most recent | 21% | 9% | 16% | 9% | 4,969 |
| Pool order | 12% | 5% | 9% | 6% | 4,985 |
| Random | 18% | 7% | 17% | 11% | 4,944 |

% of oracle at 5k by scenario type:

| Type | n | Pacific | Hybrid (BM25 + embedding) | Embedding only | BM25 only | Most recent | Pool order | Random |
|---|---|---|---|---|---|---|---|---|
| ambient | 8 | 72% | 76% | 15% | 71% | 20% | 11% | 18% |
| budget_trap | 4 | 42% | 39% | 54% | 39% | 4% | 4% | 12% |
| context_pair | 8 | 71% | 82% | 32% | 72% | 29% | 20% | 20% |
| keyword_trap | 4 | 89% | 94% | 12% | 94% | 36% | 30% | 20% |
| lookup | 10 | 94% | 84% | 8% | 84% | 14% | 0% | 17% |
| multi_doc | 10 | 60% | 64% | 18% | 63% | 38% | 21% | 18% |
| multi_turn | 3 | 63% | 53% | 4% | 56% | 33% | 7% | 20% |
| paraphrase | 8 | 45% | 44% | 6% | 48% | 9% | 19% | 13% |
| people | 6 | 89% | 77% | 15% | 77% | 7% | 0% | 26% |

**What the user actually sees** (Pacific's top-3 suggestions, gate applied): recall 49%, token precision 37%, essential items hit 61%, 3,210 tokens on average.

**Gate:** suggested something on 50% of the 8 off-topic or filler turns (should be 0%); stayed silent on 0% of the 61 real requests.

Scenario latency (session reset + replay + rescore): mean 18 ms.

### Pool of 1000 items · provider `mock` · 69 scenarios

> **Not a quality result.** This run used hash-based placeholder embeddings with no semantic content, so every embedding-dependent method is handicapped. It validates the harness only.

**Headline (5k-token budget):** Pacific packs **59%** of the best achievable relevant context, vs **61%** for the strongest baseline (BM25 only): -1 pts (-5 to +3). Recall 58% vs 59%; relevant share of tokens 20% vs 21%.

% of oracle (95% CI). The oracle is the best possible pick under the same budget, computed from the labels.

| Method | 2k tokens | 5k tokens | 10k tokens | 20k tokens |
|---|---|---|---|---|
| Pacific | 51% (41–62) | 59% (50–68) | 61% (52–70) | 62% (53–71) |
| Hybrid (BM25 + embedding) | 60% (48–70) | 60% (50–69) | 62% (52–72) | 64% (54–73) |
| Embedding only | 0% (0–0) | 1% (0–2) | 1% (0–3) | 3% (1–6) |
| BM25 only | 58% (47–68) | 61% (50–69) | 64% (54–72) | 66% (56–75) |
| Most recent | 0% (0–0) | 0% (0–0) | 0% (0–0) | 0% (0–0) |
| Pool order | 8% (4–12) | 13% (8–18) | 28% (20–37) | 51% (41–60) |
| Random | 0% (0–1) | 1% (0–1) | 1% (1–2) | 2% (2–3) |

Pacific minus each baseline, % of oracle (`*` = 95% CI excludes zero):

| vs | 2k | 5k | 10k | 20k |
|---|---|---|---|---|
| Hybrid (BM25 + embedding) | -8 pts (-17 to -1) * | -1 pts (-5 to +4) | -1 pts (-5 to +4) | -2 pts (-6 to +3) |
| Embedding only | +51 pts (+41 to +62) * | +59 pts (+49 to +67) * | +60 pts (+50 to +69) * | +59 pts (+49 to +69) * |
| BM25 only | -6 pts (-12 to -2) * | -1 pts (-5 to +3) | -2 pts (-6 to +2) | -4 pts (-9 to +1) |
| Most recent | +51 pts (+41 to +62) * | +59 pts (+50 to +68) * | +61 pts (+52 to +70) * | +62 pts (+53 to +71) * |
| Pool order | +44 pts (+33 to +54) * | +47 pts (+35 to +57) * | +33 pts (+18 to +47) * | +11 pts (-3 to +25) |
| Random | +51 pts (+41 to +61) * | +59 pts (+49 to +67) * | +60 pts (+50 to +69) * | +60 pts (+50 to +69) * |

At 5k tokens:

| Method | Recall | Token precision | Essential items hit | nDCG | Tokens used |
|---|---|---|---|---|---|
| Pacific | 58% | 20% | 67% | 56% | 4,977 |
| Hybrid (BM25 + embedding) | 58% | 21% | 66% | 57% | 4,982 |
| Embedding only | 1% | 0% | 0% | 0% | 4,978 |
| BM25 only | 59% | 21% | 66% | 57% | 4,983 |
| Most recent | 0% | 0% | 0% | 0% | 4,935 |
| Pool order | 12% | 5% | 9% | 6% | 5,000 |
| Random | 1% | 0% | 1% | 0% | 4,979 |

% of oracle at 5k by scenario type:

| Type | n | Pacific | Hybrid (BM25 + embedding) | Embedding only | BM25 only | Most recent | Pool order | Random |
|---|---|---|---|---|---|---|---|---|
| ambient | 8 | 68% | 68% | 0% | 68% | 0% | 11% | 1% |
| budget_trap | 4 | 25% | 25% | 0% | 25% | 0% | 4% | 3% |
| context_pair | 8 | 66% | 85% | 2% | 85% | 0% | 20% | 0% |
| keyword_trap | 4 | 74% | 79% | 0% | 79% | 0% | 30% | 0% |
| lookup | 10 | 68% | 66% | 2% | 71% | 0% | 0% | 1% |
| multi_doc | 10 | 54% | 56% | 1% | 52% | 0% | 21% | 1% |
| multi_turn | 3 | 56% | 50% | 0% | 56% | 0% | 7% | 1% |
| paraphrase | 8 | 28% | 25% | 0% | 25% | 0% | 19% | 1% |
| people | 6 | 89% | 77% | 0% | 77% | 0% | 0% | 0% |

**What the user actually sees** (Pacific's top-3 suggestions, gate applied): recall 45%, token precision 34%, essential items hit 54%, 3,670 tokens on average.

**Gate:** suggested something on 50% of the 8 off-topic or filler turns (should be 0%); stayed silent on 0% of the 61 real requests.

Scenario latency (session reset + replay + rescore): mean 144 ms.

## Performance and resilience

Provider `mock`.

### Scale: latency vs context-pool size

| Pool | Startup | Message p50 / p95 (ms) | Rescore p95 (ms) | Response size | RSS | BM25 index build p50 | Event-loop lag p99 |
|---|---|---|---|---|---|---|---|
| 44 | 1.2 s | 11 / 15 | 8 | 43 KB | 76 MB | 2 ms | 6 ms |
| 1,000 | 2.3 s | 96 / 132 | 101 | 738 KB | 124 MB | 27 ms | 188 ms |
| 5,000 | 7.3 s | 468 / 595 | 589 | 3,666 KB | 322 MB | 139 ms | 672 ms |
| 10,000 | 14.6 s | 1,000 / 1,198 | 1,152 | 7,335 KB | 569 MB | 278 ms | 1,534 ms |

### Concurrency (pool 1,000, 15 s per level)

| Clients | Throughput | Message p50 / p95 / p99 (ms) | Errors | Event-loop lag p99 |
|---|---|---|---|---|
| 1 | 11.7 req/s | 89 / 139 / 154 | 0 | 140 ms |
| 2 | 12.1 req/s | 176 / 240 / 294 | 0 | 274 ms |
| 4 | 13.1 req/s | 359 / 472 / 502 | 0 | 436 ms |
| 8 | 12.3 req/s | 768 / 928 / 1,022 | 0 | 692 ms |
| 16 | 12.9 req/s | 1,510 / 1,872 / 2,110 | 0 | 1,052 ms |

### Live capture loop (120 s, pool 1,000)

- Frames: 24, outcomes {'http_503': 24}
- Interval between frames p50 / p95: 5,010 / 5,107 ms (target 5,000)
- Vision call p50 / p95: – / – ms
- Frame to updated ranking p50 / p95: – / – ms
- Messages during capture p95: 138 ms; ranking failures 0

### Soak (10 min, 10 session events/s)

- RSS 108.9 → 130.7 MB; slope over second half 88.5 MB/hour
- Session events 0 → 5622; session_state.json 0.3 → 679.8 KB
- Embedding cache entries 1005 → 1237
- Message latency 120.6 → 190.1 ms; save_session p95 35 ms

### State consistency under concurrent edits

400 operations at concurrency 16: 33 snapshots broke an invariant; 2 violations in the final state.

- attached has status 'idle': 63
- attached is also dismissed: 63

### Crash safety (SIGKILL during writes)

0/20 kills left a corrupt session_state.json; 0/20 restarts lost session events.

### Endpoint unreachable

- Startup 3.6 s; message p50 / p95 2,501 / 2,610 ms
- 10/10 messages succeeded, 10 with suggestions
- Live frame → HTTP 502

