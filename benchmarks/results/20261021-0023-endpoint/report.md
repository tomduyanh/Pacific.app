# Pacific benchmark report: `20261021-0023-endpoint`

Compared against baseline run `baseline-mock`.

## Retrieval quality under a token budget

### Pool of 44 items · provider `endpoint` · 69 scenarios

**Headline (5k-token budget):** Pacific packs **81%** of the best achievable relevant context, vs **85%** for the strongest baseline (Embedding only): -4 pts (-11 to +2). Recall 79% vs 82%; relevant share of tokens 31% vs 34%.

% of oracle (95% CI). The oracle is the best possible pick under the same budget, computed from the labels.

| Method | 2k tokens | 5k tokens | 10k tokens | 20k tokens |
|---|---|---|---|---|
| Pacific | 71% (62–80) | 81% (74–87) | 86% (80–92) | 93% (90–97) |
| Hybrid (BM25 + embedding) | 66% (55–76) | 71% (62–80) | 83% (75–90) | 96% (92–98) |
| Embedding only | 72% (63–81) | 85% (80–90) | 91% (87–95) | 98% (96–99) |
| BM25 only | 60% (49–70) | 68% (59–77) | 76% (67–84) | 82% (74–89) |
| Most recent | 9% (5–13) | 21% (13–29) | 38% (28–47) | 68% (58–77) |
| Pool order | 8% (4–12) | 13% (8–18) | 28% (20–37) | 51% (41–60) |
| Random | 12% (10–14) | 18% (16–20) | 31% (29–34) | 50% (48–53) |

Pacific minus each baseline, % of oracle (`*` = 95% CI excludes zero):

| vs | 2k | 5k | 10k | 20k |
|---|---|---|---|---|
| Hybrid (BM25 + embedding) | +5 pts (-1 to +13) | +10 pts (+3 to +18) * | +3 pts (-2 to +9) | -2 pts (-4 to -1) * |
| Embedding only | -1 pts (-11 to +9) | -4 pts (-11 to +2) | -5 pts (-11 to +0) | -4 pts (-8 to -1) * |
| BM25 only | +12 pts (+4 to +20) * | +13 pts (+7 to +21) * | +10 pts (+4 to +18) * | +11 pts (+4 to +19) * |
| Most recent | +63 pts (+53 to +72) * | +60 pts (+49 to +70) * | +48 pts (+37 to +60) * | +26 pts (+16 to +37) * |
| Pool order | +64 pts (+55 to +73) * | +68 pts (+59 to +77) * | +58 pts (+46 to +69) * | +42 pts (+31 to +54) * |
| Random | +59 pts (+50 to +68) * | +63 pts (+56 to +70) * | +55 pts (+47 to +61) * | +43 pts (+39 to +47) * |

At 5k tokens:

| Method | Recall | Token precision | Essential items hit | nDCG | Tokens used |
|---|---|---|---|---|---|
| Pacific | 79% | 31% | 85% | 71% | 4,955 |
| Hybrid (BM25 + embedding) | 69% | 25% | 78% | 66% | 4,960 |
| Embedding only | 82% | 34% | 90% | 82% | 4,954 |
| BM25 only | 66% | 24% | 75% | 62% | 4,966 |
| Most recent | 21% | 9% | 16% | 9% | 4,969 |
| Pool order | 12% | 5% | 9% | 6% | 4,985 |
| Random | 18% | 7% | 17% | 11% | 4,944 |

% of oracle at 5k by scenario type:

| Type | n | Pacific | Hybrid (BM25 + embedding) | Embedding only | BM25 only | Most recent | Pool order | Random |
|---|---|---|---|---|---|---|---|---|
| ambient | 8 | 74% | 82% | 81% | 71% | 20% | 11% | 18% |
| budget_trap | 4 | 58% | 39% | 79% | 39% | 4% | 4% | 12% |
| context_pair | 8 | 80% | 82% | 83% | 72% | 29% | 20% | 20% |
| keyword_trap | 4 | 100% | 94% | 94% | 94% | 36% | 30% | 20% |
| lookup | 10 | 96% | 86% | 98% | 84% | 14% | 0% | 17% |
| multi_doc | 10 | 73% | 62% | 74% | 63% | 38% | 21% | 18% |
| multi_turn | 3 | 88% | 56% | 67% | 56% | 33% | 7% | 20% |
| paraphrase | 8 | 72% | 48% | 86% | 48% | 9% | 19% | 13% |
| people | 6 | 89% | 77% | 93% | 77% | 7% | 0% | 26% |

**What the user actually sees** (Pacific's top-3 suggestions, gate applied): recall 62%, token precision 44%, essential items hit 75%, 3,994 tokens on average.

**Gate:** suggested something on 50% of the 8 off-topic or filler turns (should be 0%); stayed silent on 0% of the 61 real requests.

Scenario latency (session reset + replay + rescore): mean 1882 ms.

### Pool of 1000 items · provider `endpoint` · 69 scenarios

**Headline (5k-token budget):** Pacific packs **68%** of the best achievable relevant context, vs **71%** for the strongest baseline (Embedding only): -3 pts (-14 to +7). Recall 66% vs 68%; relevant share of tokens 25% vs 28%.

% of oracle (95% CI). The oracle is the best possible pick under the same budget, computed from the labels.

| Method | 2k tokens | 5k tokens | 10k tokens | 20k tokens |
|---|---|---|---|---|
| Pacific | 68% (58–77) | 68% (59–75) | 73% (65–81) | 79% (72–85) |
| Hybrid (BM25 + embedding) | 65% (53–74) | 65% (55–74) | 67% (57–76) | 70% (60–79) |
| Embedding only | 61% (52–69) | 71% (63–78) | 73% (66–80) | 75% (68–82) |
| BM25 only | 58% (47–68) | 61% (50–69) | 64% (54–72) | 66% (56–75) |
| Most recent | 0% (0–0) | 0% (0–0) | 0% (0–0) | 0% (0–0) |
| Pool order | 8% (4–12) | 13% (8–18) | 28% (20–37) | 51% (41–60) |
| Random | 0% (0–1) | 1% (0–1) | 1% (1–2) | 2% (2–3) |

Pacific minus each baseline, % of oracle (`*` = 95% CI excludes zero):

| vs | 2k | 5k | 10k | 20k |
|---|---|---|---|---|
| Hybrid (BM25 + embedding) | +3 pts (-3 to +10) | +2 pts (-2 to +7) | +6 pts (+0 to +13) * | +9 pts (+2 to +17) * |
| Embedding only | +7 pts (-5 to +19) | -3 pts (-14 to +7) | +0 pts (-10 to +9) | +4 pts (-4 to +11) |
| BM25 only | +10 pts (+3 to +18) * | +7 pts (+2 to +13) * | +10 pts (+3 to +17) * | +12 pts (+5 to +21) * |
| Most recent | +68 pts (+58 to +77) * | +68 pts (+59 to +75) * | +73 pts (+65 to +81) * | +79 pts (+72 to +85) * |
| Pool order | +60 pts (+50 to +69) * | +55 pts (+44 to +64) * | +45 pts (+31 to +58) * | +28 pts (+15 to +40) * |
| Random | +68 pts (+58 to +77) * | +67 pts (+58 to +75) * | +72 pts (+64 to +79) * | +76 pts (+69 to +83) * |

At 5k tokens:

| Method | Recall | Token precision | Essential items hit | nDCG | Tokens used |
|---|---|---|---|---|---|
| Pacific | 66% | 25% | 75% | 63% | 4,980 |
| Hybrid (BM25 + embedding) | 64% | 24% | 72% | 62% | 4,975 |
| Embedding only | 68% | 28% | 81% | 70% | 4,980 |
| BM25 only | 59% | 21% | 66% | 57% | 4,983 |
| Most recent | 0% | 0% | 0% | 0% | 4,935 |
| Pool order | 12% | 5% | 9% | 6% | 5,000 |
| Random | 1% | 0% | 1% | 0% | 4,979 |

% of oracle at 5k by scenario type:

| Type | n | Pacific | Hybrid (BM25 + embedding) | Embedding only | BM25 only | Most recent | Pool order | Random |
|---|---|---|---|---|---|---|---|---|
| ambient | 8 | 75% | 79% | 70% | 68% | 0% | 11% | 1% |
| budget_trap | 4 | 36% | 25% | 79% | 25% | 0% | 4% | 3% |
| context_pair | 8 | 74% | 85% | 62% | 85% | 0% | 20% | 0% |
| keyword_trap | 4 | 94% | 94% | 65% | 79% | 0% | 30% | 0% |
| lookup | 10 | 81% | 81% | 88% | 71% | 0% | 0% | 1% |
| multi_doc | 10 | 61% | 57% | 56% | 52% | 0% | 21% | 1% |
| multi_turn | 3 | 63% | 56% | 47% | 56% | 0% | 7% | 1% |
| paraphrase | 8 | 34% | 25% | 70% | 25% | 0% | 19% | 1% |
| people | 6 | 89% | 77% | 89% | 77% | 0% | 0% | 0% |

**What the user actually sees** (Pacific's top-3 suggestions, gate applied): recall 60%, token precision 42%, essential items hit 70%, 3,659 tokens on average.

**Gate:** suggested something on 50% of the 8 off-topic or filler turns (should be 0%); stayed silent on 0% of the 61 real requests.

Scenario latency (session reset + replay + rescore): mean 1891 ms.

## Performance and resilience

Provider `endpoint`.

Baseline run used provider `mock`; change annotations are shown only between runs on the same provider.

### Scale: latency vs context-pool size

| Pool | Startup | Message p50 / p95 (ms) | Rescore p95 (ms) | Response size | RSS | BM25 index build p50 | Event-loop lag p99 / max |
|---|---|---|---|---|---|---|---|
| 44 | 3.5 s | 3,722 / 4,581 | 4,592 | 43 KB | 84 MB | 3 ms | 1 / 21 ms |
| 1,000 | 13.3 s | 4,020 / 4,688 | 4,871 | 738 KB | 149 MB | 28 ms | 1 / 160 ms |
| 5,000 | 54.4 s | 4,034 / 5,191 | 5,527 | 3,663 KB | 449 MB | 150 ms | 1 / 857 ms |
| 10,000 | 107.5 s | 4,858 / 5,880 | 5,457 | 7,328 KB | 645 MB | 498 ms | 1 / 1,997 ms |

### Concurrency (pool 1,000, 15 s per level)

| Clients | Throughput | Message p50 / p95 / p99 (ms) | Errors | Event-loop lag p99 / max |
|---|---|---|---|---|
| 1 | 0.5 req/s | 3,218 / 3,986 / 3,986 | 0 | 1 / 149 ms |
| 2 | 0.7 req/s | 4,608 / 5,784 / 5,784 | 0 | 2 / 113 ms |
| 4 | 1.4 req/s | 4,366 / 5,018 / 5,018 | 0 | 76 / 123 ms |
| 8 | 1.9 req/s | 5,113 / 9,261 / 9,261 | 0 | 83 / 146 ms |
| 16 | 2.6 req/s | 9,797 / 12,577 / 13,623 | 0 | 80 / 151 ms |

### Live capture loop (120 s, pool 1,000)

- Frames: 14, outcomes {'ok': 14}
- Interval between frames p50 / p95: 8,733 / 10,338 ms (target 5,000)
- Vision call p50 / p95: 9,211 / 11,302 ms
- Frame to updated ranking p50 / p95: 4,909 / 5,397 ms
- Messages during capture p95: 5,610 ms; ranking failures 0

### Soak (10 min, 10 session events/s)

- RSS 129.5 → 157.4 MB; slope over second half 121.1 MB/hour
- Session events 0 → 5720; session_state.json 3.0 → 690.7 KB
- Embedding cache entries 1005 → 1425
- Message latency 2471.5 → 5089.9 ms; save_session p95 38 ms

### State consistency under concurrent edits

400 operations at concurrency 16: 31 snapshots broke an invariant; 2 violations in the final state.

- attached has status 'idle': 53
- attached is also dismissed: 53

### Crash safety (SIGKILL during writes)

0/20 kills left a corrupt session_state.json; 0/20 restarts lost session events.

### Endpoint unreachable

- Startup 3.8 s; message p50 / p95 2,505 / 2,604 ms
- 10/10 messages succeeded, 10 with suggestions
- Live frame → HTTP 502

