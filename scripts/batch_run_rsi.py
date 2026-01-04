from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import sys

# Allow running as `python scripts/batch_run_rsi.py` without installing the repo as a package.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.runner import WorkflowRunner


def _parse_csv_list(value: str) -> list[str]:
    parts = [p.strip().upper() for p in (value or "").split(",")]
    return [p for p in parts if p]


def main() -> int:
    ap = argparse.ArgumentParser(description="Run unattended RSI Divergence Pro batch workflows.")
    ap.add_argument("--profile", default="reference/rsi_divergence_pro_profile.json")
    ap.add_argument("--terminal", default=None, help="Terminal name from terminals.json (default: active)")
    ap.add_argument("--timeframe", default=None, help="Override timeframe (default from profile)")
    ap.add_argument("--base-symbol", default=None, help="Base symbol (default from profile)")
    ap.add_argument("--symbols", default=None, help="Comma-separated list of total symbols to run (includes base)")
    ap.add_argument("--iterations", type=int, default=1)
    ap.add_argument("--stress", action="store_true", help="Run Step 12 stress scenarios")
    ap.add_argument("--forward", action="store_true", help="Run Step 13 forward windows")
    ap.add_argument("--no-multi", action="store_true", help="Disable multi-pair (only base symbol)")
    args = ap.parse_args()

    profile_path = Path(args.profile)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    ea_path = profile["ea_path"]
    wide = profile["wide_validation_params"]
    ranges = profile["optimization_ranges"]

    tf = args.timeframe or profile.get("timeframe_default") or "H4"
    base_symbol = (args.base_symbol or profile.get("symbol_default") or "GBPUSD").upper()

    symbols = None
    if args.symbols:
        symbols = _parse_csv_list(args.symbols)
    if symbols:
        if base_symbol not in symbols:
            symbols = [base_symbol] + symbols
    else:
        symbols = [base_symbol]

    other_symbols = [s for s in symbols if s != base_symbol]

    out_dir = Path("runs") / "batch"
    out_dir.mkdir(parents=True, exist_ok=True)
    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_path = out_dir / f"rsi_batch_{batch_id}.json"

    summaries = []

    def _progress(message: str) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] {message}", flush=True)

    print(
        json.dumps(
            {
                "batch_id": batch_id,
                "ea_path": ea_path,
                "timeframe": tf,
                "base_symbol": base_symbol,
                "other_symbols": other_symbols,
                "iterations": int(args.iterations),
                "stress": bool(args.stress),
                "forward": bool(args.forward),
                "multi_pair": (not args.no_multi and bool(other_symbols)),
                "profile": str(profile_path),
            },
            indent=2,
        ),
        flush=True,
    )

    for i in range(max(1, int(args.iterations))):
        _progress(f"Batch iteration {i + 1}/{max(1, int(args.iterations))}: starting base workflow")
        runner = WorkflowRunner(
            ea_path=ea_path,
            terminal_name=args.terminal,
            symbol=base_symbol,
            timeframe=tf,
            auto_stats_analysis=True,
            auto_run_stress_scenarios=bool(args.stress),
            auto_run_forward_windows=bool(args.forward),
            auto_run_multi_pair=(not args.no_multi and bool(other_symbols)),
            multi_pair_symbols=other_symbols,
            on_progress=_progress,
        )

        phase1 = runner.run(stop_on_failure=False, pause_for_analysis=True)
        _progress(f"Phase 1 complete: status={phase1.get('status')} workflow_id={phase1.get('workflow_id')}")
        summary = runner.continue_with_params(wide_validation_params=wide, optimization_ranges=ranges, stop_on_failure=False)
        summaries.append(summary)
        _progress(f"Workflow complete: status={summary.get('status')} workflow_id={summary.get('workflow_id')}")

        # If multi-pair is enabled, the child workflows are created by Step 14 and will show in Boards/Leaderboard.

    summary_path.write_text(json.dumps({"batch_id": batch_id, "summaries": summaries}, indent=2), encoding="utf-8")
    print(f"Wrote: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
