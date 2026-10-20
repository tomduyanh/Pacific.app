"""One command for the whole benchmark suite.

    python -m benchmarks --provider endpoint            # preflight, quality, stress, report
    python -m benchmarks --provider mock --quick        # fast harness check, no network

Results land in benchmarks/results/<timestamp>-<provider>/, and report.md
compares against benchmarks/results/baseline-mock/ when it exists.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BENCH = Path(__file__).resolve().parent
REPO = BENCH.parent
DEFAULT_BASELINE = BENCH / "results" / "baseline-mock"


def run(*args: str) -> None:
    print("$ python -m " + " ".join(args), flush=True)
    subprocess.run([sys.executable, "-m", *args], cwd=REPO, check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="endpoint", choices=["endpoint", "mock"])
    ap.add_argument("--quick", action="store_true", help="short durations, small pools")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    ap.add_argument("--skip", nargs="*", default=[], choices=["preflight", "quality", "stress"])
    args = ap.parse_args()

    out = args.out or BENCH / "results" / f"{datetime.now():%Y%m%d-%H%M}-{args.provider}"
    out.mkdir(parents=True, exist_ok=True)

    if args.provider == "endpoint" and "preflight" not in args.skip:
        run("benchmarks.preflight", "--provider", "endpoint")
    if "quality" not in args.skip:
        sizes = ["44"] if args.quick else ["44", "1000"]
        run("benchmarks.quality.run_quality", "--provider", args.provider, "--out", str(out), "--pool-size", *sizes)
    if "stress" not in args.skip:
        extra = (["--sizes", "44", "1000", "--pool-size", "200", "--level-seconds", "5", "--levels", "1", "4",
                  "--live-seconds", "20", "--soak-seconds", "40", "--crash-trials", "3"] if args.quick else [])
        run("benchmarks.stress.run_stress", "--provider", args.provider, "--out", str(out), *extra)
    report_args = ["benchmarks.report", str(out)]
    if args.baseline.exists() and args.baseline.resolve() != out.resolve():
        report_args += ["--baseline", str(args.baseline)]
    run(*report_args)


if __name__ == "__main__":
    main()
