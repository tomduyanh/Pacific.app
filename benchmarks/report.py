"""Render benchmark results as Markdown, optionally against a baseline run.

    python -m benchmarks.report RESULTS_DIR [--baseline BASELINE_DIR]

Reads RESULTS_DIR/quality.json and RESULTS_DIR/stress.json (either may be
missing) and writes RESULTS_DIR/report.md.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

METHOD_LABELS = {
    "pacific": "Pacific", "hybrid": "Hybrid (BM25 + embedding)", "embedding": "Embedding only",
    "bm25": "BM25 only", "recency": "Most recent", "pool_order": "Pool order", "random": "Random",
}


def _load(d: Path, name: str) -> dict | None:
    p = d / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _p(x: float | None, digits: int = 0) -> str:
    return "–" if x is None else f"{100 * x:.{digits}f}%"


def _ci(cell: dict) -> str:
    if cell.get("mean") is None:
        return "–"
    return f"{100 * cell['mean']:.0f}% ({100 * cell['lo']:.0f}–{100 * cell['hi']:.0f})"


def _diff(cell: dict) -> str:
    if cell.get("mean") is None:
        return "–"
    sig = "" if cell["lo"] <= 0 <= cell["hi"] else " *"
    return f"{100 * cell['mean']:+.0f} pts ({100 * cell['lo']:+.0f} to {100 * cell['hi']:+.0f}){sig}"


def _ms(cell: dict | None, key: str = "p50") -> str:
    if not cell or cell.get(key) is None:
        return "–"
    return f"{cell[key]:,.0f}"


def _delta(now: float | None, before: float | None, lower_is_better: bool = True) -> str:
    if now is None or before is None or before == 0:
        return ""
    change = (now - before) / before
    better = change < 0 if lower_is_better else change > 0
    return f" ({change:+.0%} {'better' if better else 'worse'})" if abs(change) >= 0.05 else " (≈)"


def quality_section(q: dict, base: dict | None) -> list[str]:
    out = ["## Retrieval quality under a token budget", ""]
    for pool_size, run in q.items():
        meta, s = run["meta"], run["summary"]
        out += [f"### Pool of {meta['pool_size']} items · provider `{meta['provider']}` · "
                f"{meta['scenarios']} scenarios", ""]
        if meta["provider"] in {"mock", "outage"}:
            out += ["> **Not a quality result.** This run used hash-based placeholder embeddings with no "
                    "semantic content, so every embedding-dependent method is handicapped. "
                    "It validates the harness only.", ""]
        b5 = s["budgets"].get("5000")
        if b5:
            best = max((m for m in METHOD_LABELS if m != "pacific"),
                       key=lambda m: b5[m]["pct_oracle"]["mean"] or 0)
            d = b5["pacific_vs"][best]["pct_oracle"]
            out += [f"**Headline (5k-token budget):** Pacific packs **{_p(b5['pacific']['pct_oracle']['mean'])}** "
                    f"of the best achievable relevant context, vs **{_p(b5[best]['pct_oracle']['mean'])}** for the "
                    f"strongest baseline ({METHOD_LABELS[best]}): {_diff(d)}. "
                    f"Recall {_p(b5['pacific']['recall']['mean'])} vs {_p(b5[best]['recall']['mean'])}; "
                    f"relevant share of tokens {_p(b5['pacific']['token_precision']['mean'])} vs "
                    f"{_p(b5[best]['token_precision']['mean'])}.", ""]
        out += ["% of oracle (95% CI). The oracle is the best possible pick under the same budget, "
                "computed from the labels.", "",
                "| Method | " + " | ".join(f"{int(b) // 1000}k tokens" for b in s["budgets"]) + " |",
                "|---|" + "---|" * len(s["budgets"])]
        for m, label in METHOD_LABELS.items():
            out.append(f"| {label} | " + " | ".join(_ci(s["budgets"][b][m]["pct_oracle"]) for b in s["budgets"]) + " |")
        out += ["", "Pacific minus each baseline, % of oracle (`*` = 95% CI excludes zero):", "",
                "| vs | " + " | ".join(f"{int(b) // 1000}k" for b in s["budgets"]) + " |",
                "|---|" + "---|" * len(s["budgets"])]
        for m, label in METHOD_LABELS.items():
            if m == "pacific":
                continue
            out.append(f"| {label} | " + " | ".join(_diff(s["budgets"][b]["pacific_vs"][m]["pct_oracle"])
                                                    for b in s["budgets"]) + " |")
        if b5:
            out += ["", "At 5k tokens:", "", "| Method | Recall | Token precision | Essential items hit | nDCG | Tokens used |",
                    "|---|---|---|---|---|---|"]
            for m, label in METHOD_LABELS.items():
                c = b5[m]
                out.append(f"| {label} | {_p(c['recall']['mean'])} | {_p(c['token_precision']['mean'])} | "
                           f"{_p(c['essential_hit']['mean'])} | {_p(c['ndcg']['mean'])} | {c['tokens_used']:,.0f} |")
            out += ["", "% of oracle at 5k by scenario type:", "",
                    "| Type | n | " + " | ".join(METHOD_LABELS.values()) + " |",
                    "|---|---|" + "---|" * len(METHOD_LABELS)]
            for t, row in s["by_type"].items():
                out.append(f"| {t} | {row['n']} | " + " | ".join(_p(row[m]) for m in METHOD_LABELS) + " |")
        sh, g = s["shipped"], s["gate"]
        out += ["", "**What the user actually sees** (Pacific's top-3 suggestions, gate applied): "
                f"recall {_p(sh['recall'])}, token precision {_p(sh['token_precision'])}, "
                f"essential items hit {_p(sh['essential_hit'])}, {sh['tokens_used']:,.0f} tokens on average.", "",
                f"**Gate:** suggested something on {_p(g['false_suggest_rate'])} of the {g['n_should_be_silent']} "
                f"off-topic or filler turns (should be 0%); stayed silent on {_p(g['false_silence_rate'])} of the "
                f"{g['n_should_suggest']} real requests.", "",
                f"Scenario latency (session reset + replay + rescore): mean {s['latency_ms']['mean']:.0f} ms.", ""]
        if base and pool_size in base:
            b0 = base[pool_size]["summary"]["budgets"].get("5000")
            if b0 and b5:
                out += [f"**Vs baseline run** (5k, % of oracle): Pacific {_p(b0['pacific']['pct_oracle']['mean'])} → "
                        f"{_p(b5['pacific']['pct_oracle']['mean'])}.", ""]
    return out


def stress_section(st: dict, base: dict | None) -> list[str]:
    out = ["## Performance and resilience", "", f"Provider `{st['meta']['provider']}`.", ""]
    b = base or {}
    if "scale" in st:
        out += ["### Scale: latency vs context-pool size", "",
                "| Pool | Startup | Message p50 / p95 (ms) | Rescore p95 (ms) | Response size | RSS | BM25 index build p50 | Event-loop lag p99 |",
                "|---|---|---|---|---|---|---|---|"]
        for n, r in st["scale"].items():
            before = b.get("scale", {}).get(n, {})
            out.append(
                f"| {int(n):,} | {r['startup_s']:.1f} s | {_ms(r['message_ms'])} / {_ms(r['message_ms'], 'p95')}"
                f"{_delta(r['message_ms'].get('p95'), before.get('message_ms', {}).get('p95'))} | "
                f"{_ms(r['rescore_ms'], 'p95')} | {r['response_kb']:,.0f} KB | {r['rss_after_run_mb']:.0f} MB | "
                f"{_ms(r['stages'].get('build_index_bm25'))} ms | {_ms(r['loop_lag_ms'], 'p99')} ms |")
        out.append("")
    if "concurrency" in st:
        c = st["concurrency"]
        out += [f"### Concurrency (pool {c['pool_size']:,}, {c['seconds_per_level']:.0f} s per level)", "",
                "| Clients | Throughput | Message p50 / p95 / p99 (ms) | Errors | Event-loop lag p99 |",
                "|---|---|---|---|---|"]
        for k, r in c["levels"].items():
            msg = r["ops"].get("message", {})
            before = b.get("concurrency", {}).get("levels", {}).get(k, {})
            out.append(f"| {k} | {r['throughput_rps']:.1f} req/s{_delta(r['throughput_rps'], before.get('throughput_rps'), False)} | "
                       f"{_ms(msg)} / {_ms(msg, 'p95')} / {_ms(msg, 'p99')} | {r['errors']} | {_ms(r['loop_lag_ms'], 'p99')} ms |")
        out.append("")
    if "live" in st:
        lv = st["live"]
        out += [f"### Live capture loop ({lv['seconds']:.0f} s, pool {lv['pool_size']:,})", "",
                f"- Frames: {lv['ticks']}, outcomes {lv['outcomes']}",
                f"- Interval between frames p50 / p95: {_ms(lv['tick_interval_ms'])} / {_ms(lv['tick_interval_ms'], 'p95')} ms (target 5,000)",
                f"- Vision call p50 / p95: {_ms(lv['vision_ms'])} / {_ms(lv['vision_ms'], 'p95')} ms",
                f"- Frame to updated ranking p50 / p95: {_ms(lv['frame_to_ranking_ms'])} / {_ms(lv['frame_to_ranking_ms'], 'p95')} ms",
                f"- Messages during capture p95: {_ms(lv['message_ms'], 'p95')} ms; ranking failures {lv['rescore_failures']}", ""]
    if "soak" in st:
        sk = st["soak"]
        s0, s1 = (sk["samples"][0], sk["samples"][-1]) if sk["samples"] else ({}, {})
        out += [f"### Soak ({sk['seconds'] / 60:.0f} min, {sk['event_rate_per_s']:g} session events/s)", "",
                f"- RSS {s0.get('rss_mb')} → {s1.get('rss_mb')} MB; slope over second half "
                f"{sk['rss_slope_mb_per_hour_second_half']} MB/hour",
                f"- Session events {s0.get('session_events')} → {s1.get('session_events')}; "
                f"session_state.json {s0.get('state_file_kb')} → {s1.get('state_file_kb')} KB",
                f"- Embedding cache entries {s0.get('embed_cache_entries')} → {s1.get('embed_cache_entries')}",
                f"- Message latency {s0.get('message_ms')} → {s1.get('message_ms')} ms; "
                f"save_session p95 {_ms(sk.get('save_session_ms'), 'p95')} ms", ""]
    if "consistency" in st:
        cs = st["consistency"]
        out += ["### State consistency under concurrent edits", "",
                f"{cs['ops']} operations at concurrency {cs['concurrency']}: "
                f"{cs['snapshots_with_violations']} snapshots broke an invariant; "
                f"{len(cs['final_violations'])} violations in the final state.", ""]
        for kind, n in cs["violation_kinds"].items():
            out.append(f"- {kind}: {n}")
        out.append("")
    if "crash" in st:
        cr = st["crash"]
        out += ["### Crash safety (SIGKILL during writes)", "",
                f"{cr['corrupt_files']}/{cr['trials']} kills left a corrupt session_state.json; "
                f"{cr['sessions_lost']}/{cr['trials']} restarts lost session events.", ""]
    if "outage" in st:
        o = st["outage"]
        out += ["### Endpoint unreachable", "",
                f"- Startup {o['startup_s']:.1f} s; message p50 / p95 {_ms(o['message_ms'])} / {_ms(o['message_ms'], 'p95')} ms",
                f"- {o['message_success']}/{o['messages']} messages succeeded, {o['messages_with_suggestions']} with suggestions",
                f"- Live frame → HTTP {o['live_tick_status']}", ""]
    return out


def render(results: Path, baseline: Path | None) -> str:
    q, st = _load(results, "quality.json"), _load(results, "stress.json")
    bq = _load(baseline, "quality.json") if baseline else None
    bst = _load(baseline, "stress.json") if baseline else None
    lines = [f"# Pacific benchmark report: `{results.name}`", ""]
    if baseline:
        lines += [f"Compared against baseline run `{baseline.name}`.", ""]
    if q:
        lines += quality_section(q, bq)
    if st:
        lines += stress_section(st, bst)
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("results", type=Path)
    ap.add_argument("--baseline", type=Path, default=None)
    args = ap.parse_args()
    text = render(args.results, args.baseline)
    (args.results / "report.md").write_text(text, encoding="utf-8")
    print(f"wrote {args.results / 'report.md'}")


if __name__ == "__main__":
    main()
