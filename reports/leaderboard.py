"""
Leaderboard Generator

Builds a combined leaderboard from the best passes of each workflow.
Prefers Step 9 robust backtest results (more accurate) and falls back to
Step 7 optimization results if needed.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

import settings
from modules.loader import load_module

_pass_analyzer = load_module("pass_analyzer", "modules/pass_analyzer.py")
analyze_passes = _pass_analyzer.analyze_passes

_gates = load_module("gates", "engine/gates.py")
calculate_composite_score = _gates.calculate_composite_score

TEMPLATES_DIR = Path(__file__).parent / "templates"
PASSES_PER_WORKFLOW = getattr(settings, "TOP_PASSES_BACKTEST", 30)


def generate_leaderboard(
    runs_dir: str = "runs",
    output_dir: Optional[str] = None,
    open_browser: bool = False,
    passes_per_workflow: int = PASSES_PER_WORKFLOW,
) -> str:
    runs_path = Path(runs_dir)
    out_dir = Path(output_dir) if output_dir else (runs_path / "leaderboard")
    out_dir.mkdir(parents=True, exist_ok=True)

    all_passes: list[dict[str, Any]] = []
    workflows_processed = 0

    # Statuses to exclude from leaderboard (stuck/failed workflows)
    EXCLUDED_STATUSES = {'failed', 'awaiting_param_analysis', 'awaiting_stats_analysis', 'awaiting_ea_fix', 'pending'}

    for state_file in sorted(runs_path.glob("workflow_*.json")):
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        # Skip failed/stuck workflows
        status = state.get("status", "")
        if status in EXCLUDED_STATUSES:
            continue

        passes = extract_top_passes(state, state_file, top_n=passes_per_workflow)
        if passes:
            all_passes.extend(passes)
            workflows_processed += 1

    all_passes.sort(key=lambda p: float(p.get("score_num") or 0), reverse=True)
    for idx, p in enumerate(all_passes, 1):
        p["rank"] = idx

    data = {
        "passes": all_passes,
        "total_passes": len(all_passes),
        "workflows_processed": workflows_processed,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    template_path = TEMPLATES_DIR / "leaderboard_spa.html"
    if not template_path.exists():
        raise FileNotFoundError(f"Missing template: {template_path}")

    template = template_path.read_text(encoding="utf-8")
    html = template.replace("{{DATA_JSON}}", json.dumps(data, indent=2))

    (out_dir / "index.html").write_text(html, encoding="utf-8")
    (out_dir / "data.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    if open_browser:
        import webbrowser

        webbrowser.open(f"file://{(out_dir / 'index.html').absolute()}")

    return str(out_dir / "index.html")


def _load_results_file(results_file: str, state_file: Path) -> list[dict[str, Any]]:
    if not results_file:
        return []

    candidates = [Path(results_file), state_file.parent / results_file]
    for candidate in candidates:
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                return []
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
            if isinstance(data, dict):
                items = data.get("all_results", data.get("results", []))
                return [x for x in items if isinstance(x, dict)]
            return []
    return []


def _fmt_gbp(value: Any) -> str:
    try:
        num = float(value)
    except Exception:
        num = 0.0
    return f"£{num:,.0f}"


def _status_from(forward: float, back: float, is_consistent: bool) -> tuple[str, str]:
    if is_consistent:
        return "consistent", "✓ Consistent"
    if forward > 0 and back < 0:
        return "forward_only", "↗ Forward Only"
    if back > 0 and forward < 0:
        return "back_only", "↘ Back Only"
    return "mixed", "• Mixed"


def _score_for_backtest(pass_result: dict[str, Any]) -> float:
    """Calculate Go Live Score for a pass.

    Uses the new Go Live Score formula which considers:
    - Consistency (back+forward both positive)
    - Total profit
    - Trade count
    - Profit factor
    - Max drawdown
    """
    # Extract all metrics needed for Go Live Score
    profit = float(pass_result.get("profit") or 0)
    trades = int(pass_result.get("total_trades") or 0)
    pf = float(pass_result.get("profit_factor") or 0)
    dd = float(pass_result.get("max_drawdown_pct") or 0)

    # Forward/back results for consistency scoring
    forward = float(pass_result.get("forward_result") or 0)
    back = float(pass_result.get("back_result") or 0)

    # If forward/back not directly available, check params
    if forward == 0 and back == 0:
        params = pass_result.get("params") if isinstance(pass_result.get("params"), dict) else {}
        forward = float(params.get("Forward Result") or 0)
        back = float(params.get("Back Result") or 0)

    return float(
        calculate_composite_score(
            {
                "profit": profit,
                "total_trades": trades,
                "profit_factor": pf,
                "max_drawdown_pct": dd,
                "forward_result": forward,
                "back_result": back,
            }
        )
    )


def extract_top_passes(state: dict[str, Any], state_file: Path, top_n: int = 20) -> list[dict[str, Any]]:
    steps = state.get("steps") if isinstance(state.get("steps"), dict) else {}

    # Priority 1: Backtest results (most accurate - actual backtests on selected passes)
    bt_step = steps.get("9_backtest_robust") if isinstance(steps, dict) else None
    bt_result = bt_step.get("result") if isinstance(bt_step, dict) else None
    backtests: list[dict[str, Any]] = []
    if isinstance(bt_result, dict):
        backtests = bt_result.get("all_results", []) if isinstance(bt_result.get("all_results"), list) else []
        if not backtests and bt_result.get("results_file"):
            backtests = _load_results_file(str(bt_result.get("results_file")), state_file)

    if backtests:
        return _extract_from_backtests(state, state_file, backtests, top_n)

    # Priority 2: optimization_results.top_20 (direct optimization results storage)
    opt_results_direct = state.get("optimization_results")
    if isinstance(opt_results_direct, dict):
        top_20 = opt_results_direct.get("top_20", [])
        if isinstance(top_20, list) and top_20:
            return _extract_from_optimization(state, state_file, top_20, top_n)

    # Priority 3: steps.7_run_optimization (workflow runner storage)
    opt_step = steps.get("7_run_optimization") if isinstance(steps, dict) else None
    opt_result = opt_step.get("result") if isinstance(opt_step, dict) else None
    opt_results: list[dict[str, Any]] = []
    if isinstance(opt_result, dict):
        opt_results = opt_result.get("results", []) if isinstance(opt_result.get("results"), list) else []
        if not opt_results and opt_result.get("results_file"):
            opt_results = _load_results_file(str(opt_result.get("results_file")), state_file)

    if not opt_results:
        return []

    analysis = analyze_passes(opt_results) if callable(analyze_passes) else {}
    filtered = analysis.get("filtered_passes", []) if isinstance(analysis, dict) else []
    filtered = [p for p in filtered if isinstance(p, dict)][:top_n]
    if not filtered:
        return []
    return _extract_from_optimization(state, state_file, filtered, top_n)


def _stress_summary(state: dict[str, Any]) -> tuple[Optional[int], dict[str, Any]]:
    stress = state.get("stress_scenarios")
    if not isinstance(stress, dict):
        return None, {}
    pass_num = stress.get("pass_num")
    if isinstance(pass_num, int):
        return pass_num, stress
    return None, stress


def _worst_stress_profit(stress: dict[str, Any]) -> tuple[Optional[float], str]:
    worst_profit: Optional[float] = None
    worst_label = "-"
    for s in stress.get("scenarios", []) or []:
        if not isinstance(s, dict) or not s.get("success"):
            continue
        r = s.get("result") if isinstance(s.get("result"), dict) else {}
        profit = r.get("profit")
        if not isinstance(profit, (int, float)):
            continue
        profit = float(profit)
        label = str(s.get("label") or s.get("id") or "scenario")
        if worst_profit is None or profit < worst_profit:
            worst_profit = profit
            worst_label = label
    return worst_profit, worst_label


def _row_base(state: dict[str, Any], state_file: Path) -> dict[str, Any]:
    return {
        "ea_name": state.get("ea_name", "Unknown"),
        "symbol": state.get("symbol", ""),
        "timeframe": state.get("timeframe", ""),
        "workflow_id": state.get("workflow_id") or state_file.stem.replace("workflow_", ""),
        "created_at": state.get("created_at", ""),
    }


def _extract_from_optimization(
    state: dict[str, Any], state_file: Path, passes: list[dict[str, Any]], top_n: int
) -> list[dict[str, Any]]:
    stress_pass_num, stress = _stress_summary(state)
    worst_profit, worst_label = _worst_stress_profit(stress) if stress_pass_num is not None else (None, "-")

    rows: list[dict[str, Any]] = []
    for p in passes[:top_n]:
        params = p.get("params") if isinstance(p.get("params"), dict) else {}
        pass_num = int(params.get("Pass") or 0)

        forward = float(p.get("forward_result") or 0)
        back = float(p.get("back_result") or 0)
        is_consistent = bool(p.get("is_consistent"))
        status, status_label = _status_from(forward, back, is_consistent)

        profit = float(p.get("profit") or 0)
        pf = float(p.get("profit_factor") or 0)
        dd = float(p.get("max_drawdown_pct") or 0)
        trades = int(p.get("total_trades") or 0)
        win_rate = float(p.get("win_rate") or 0)
        score = _score_for_backtest(p)

        stress_worst_profit_num = None
        stress_worst_profit = "-"
        stress_worst_scenario = "-"
        if stress_pass_num is not None:
            if pass_num == stress_pass_num and worst_profit is not None:
                stress_worst_profit_num = worst_profit
                stress_worst_profit = _fmt_gbp(worst_profit)
                stress_worst_scenario = worst_label
            else:
                stress_worst_scenario = f"Stress scenarios were run for Pass #{stress_pass_num} only"

        rows.append(
            {
                **_row_base(state, state_file),
                "pass_num": pass_num,
                "dashboard_link": f"../dashboards/{(_row_base(state, state_file)['workflow_id'])}/index.html",
                "score": f"{score:.1f}",
                "score_num": score,
                "profit": _fmt_gbp(profit),
                "profit_num": profit,
                "stress_worst_profit": stress_worst_profit,
                "stress_worst_profit_num": stress_worst_profit_num,
                "stress_worst_scenario": stress_worst_scenario,
                "profit_factor": f"{pf:.2f}",
                "pf_num": pf,
                "max_drawdown_pct": f"{dd:.1f}%",
                "dd_num": dd,
                "total_trades": trades,
                "win_rate": f"{win_rate:.1f}%",
                "win_rate_num": win_rate,
                "forward_result": f"{forward:+.1f}" if forward != 0 else "0",
                "forward_num": forward,
                "back_result": f"{back:+.1f}" if back != 0 else "0",
                "back_num": back,
                "status": status,
                "status_label": status_label,
            }
        )

    return rows


def _extract_from_backtests(
    state: dict[str, Any], state_file: Path, backtests: list[dict[str, Any]], top_n: int
) -> list[dict[str, Any]]:
    stress_pass_num, stress = _stress_summary(state)
    worst_profit, worst_label = _worst_stress_profit(stress) if stress_pass_num is not None else (None, "-")

    backtests_sorted = sorted(backtests, key=_score_for_backtest, reverse=True)[:top_n]
    rows: list[dict[str, Any]] = []

    for p in backtests_sorted:
        pass_num = int(p.get("pass_num") or 0)
        profit = float(p.get("profit") or 0)
        pf = float(p.get("profit_factor") or 0)
        dd = float(p.get("max_drawdown_pct") or 0)
        trades = int(p.get("total_trades") or 0)
        win_rate = float(p.get("win_rate") or 0)

        forward = float(p.get("forward_result") or 0)
        back = float(p.get("back_result") or 0)
        is_consistent = bool(p.get("is_consistent"))
        status, status_label = _status_from(forward, back, is_consistent)

        score = _score_for_backtest(p)

        stress_worst_profit_num = None
        stress_worst_profit = "-"
        stress_worst_scenario = "-"
        if stress_pass_num is not None:
            if pass_num == stress_pass_num and worst_profit is not None:
                stress_worst_profit_num = worst_profit
                stress_worst_profit = _fmt_gbp(worst_profit)
                stress_worst_scenario = worst_label
            else:
                stress_worst_scenario = f"Stress scenarios were run for Pass #{stress_pass_num} only"

        rows.append(
            {
                **_row_base(state, state_file),
                "pass_num": pass_num,
                "dashboard_link": f"../dashboards/{(_row_base(state, state_file)['workflow_id'])}/index.html",
                "score": f"{score:.1f}",
                "score_num": score,
                "profit": _fmt_gbp(profit),
                "profit_num": profit,
                "stress_worst_profit": stress_worst_profit,
                "stress_worst_profit_num": stress_worst_profit_num,
                "stress_worst_scenario": stress_worst_scenario,
                "profit_factor": f"{pf:.2f}",
                "pf_num": pf,
                "max_drawdown_pct": f"{dd:.1f}%",
                "dd_num": dd,
                "total_trades": trades,
                "win_rate": f"{win_rate:.1f}%",
                "win_rate_num": win_rate,
                "forward_result": f"{forward:+.1f}" if forward != 0 else "0",
                "forward_num": forward,
                "back_result": f"{back:+.1f}" if back != 0 else "0",
                "back_num": back,
                "status": status,
                "status_label": status_label,
            }
        )

    return rows


if __name__ == "__main__":
    path = generate_leaderboard(open_browser=True)
    print(f"Generated: {path}")
