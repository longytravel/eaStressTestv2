"""
Boards Generator (Workflow Summary)

Creates a global index across workflows and post-step scenarios so results don't
"disappear" from the UI when you switch runs.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.gates import calculate_composite_score

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _format_date(iso_date: str) -> str:
    """Convert ISO date to human-readable format like 'Jan 6, 09:18'."""
    if not iso_date:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %H:%M")
    except Exception:
        return iso_date[:16] if len(iso_date) > 16 else iso_date


def _generate_notes(state: dict[str, Any]) -> str:
    """Generate a short note summarizing key workflow characteristics."""
    notes = []
    features = []

    # Gather all params from various sources
    all_params: dict[str, Any] = {}

    # Source 1: optimization_ranges
    for r in _as_list(state.get("optimization_ranges")):
        if isinstance(r, dict) and r.get("name"):
            all_params[r["name"]] = r.get("default") or r.get("value")

    # Source 2: selected_passes (best pass params)
    selected = _as_list(state.get("selected_passes"))
    if selected and isinstance(selected[0], dict):
        all_params.update(selected[0].get("params", {}))

    # Source 3: optimization_results top pass
    opt_results = _as_dict(state.get("optimization_results"))
    top_20 = _as_list(opt_results.get("top_20"))
    if top_20 and isinstance(top_20[0], dict):
        all_params.update(top_20[0].get("params", {}))

    # Count optimized params
    opt_ranges = _as_list(state.get("optimization_ranges"))
    opt_count = sum(1 for r in opt_ranges if isinstance(r, dict) and r.get("optimize"))
    if opt_count:
        notes.append(f"{opt_count} params")

    # Detect features from params
    # London session sizing: if London_Size_Multiplier > 1
    london_mult = all_params.get("London_Size_Multiplier", 1)
    if london_mult and float(london_mult) > 1:
        features.append(f"London {london_mult}x")

    # Asymmetric params: if Long_StopLoss differs from StopLoss
    long_sl = all_params.get("Long_StopLoss_Points")
    sl = all_params.get("StopLoss_Points")
    if long_sl and sl and long_sl != sl:
        features.append("Asymmetric")

    # Check Enable_ flags
    if all_params.get("Enable_Session_Sizing") in (True, "true", 1):
        if "London" not in str(features):
            features.append("Session sizing")
    if all_params.get("Enable_Breakeven") in (True, "true", 1):
        features.append("BE")
    if all_params.get("Enable_Trailing") in (True, "true", 1):
        features.append("Trail")
    if all_params.get("Enable_Regular_Divergence") in (True, "true", 1):
        features.append("RegDiv")

    if features:
        notes.append(" + ".join(features))

    # Check if stress tested
    stress = _as_dict(state.get("stress_scenarios"))
    if stress.get("scenarios"):
        notes.append("stress tested")

    return " | ".join(notes) if notes else ""


def _best_workflow_metrics(state: dict[str, Any]) -> dict[str, Any]:
    """Get metrics from the best pass for Go Live Score calculation.

    Returns dict with: profit, profit_factor, max_drawdown_pct, total_trades,
    win_rate, forward_result, back_result
    """
    # Priority 1: Best optimization pass (most accurate after optimization completes)
    opt_results = _as_dict(state.get("optimization_results"))
    top_20 = _as_list(opt_results.get("top_20"))
    if top_20 and isinstance(top_20[0], dict):
        best = top_20[0]
        if best.get("profit") or best.get("total_trades"):
            params = _as_dict(best.get("params"))
            return {
                "profit": best.get("profit", 0),
                "profit_factor": best.get("profit_factor", 0),
                "max_drawdown_pct": best.get("max_drawdown_pct", 0),
                "total_trades": best.get("total_trades", 0),
                "win_rate": best.get("win_rate", 0),
                "forward_result": best.get("forward_result") or params.get("Forward Result", 0),
                "back_result": best.get("back_result") or params.get("Back Result", 0),
            }

    # Priority 2: Backtest results (if backtests were run on selected passes)
    backtest_results = _as_dict(state.get("backtest_results"))
    if backtest_results:
        # Get best backtest by profit
        best_bt = max(backtest_results.values(), key=lambda x: x.get("profit", 0) if isinstance(x, dict) else 0, default={})
        if isinstance(best_bt, dict) and (best_bt.get("profit") or best_bt.get("total_trades")):
            return {
                "profit": best_bt.get("profit", 0),
                "profit_factor": best_bt.get("profit_factor", 0),
                "max_drawdown_pct": best_bt.get("max_drawdown_pct", 0),
                "total_trades": best_bt.get("total_trades", 0),
                "win_rate": best_bt.get("win_rate", 0),
                "forward_result": best_bt.get("forward_result", 0),
                "back_result": best_bt.get("back_result", 0),
            }

    # Priority 3: Explicit metrics field (may be from validation)
    metrics = _as_dict(state.get("metrics"))
    if any(k in metrics for k in ("profit", "profit_factor", "max_drawdown_pct", "total_trades")) and (
        metrics.get("total_trades") or metrics.get("profit") or metrics.get("profit_factor") or metrics.get("max_drawdown_pct")
    ):
        return metrics

    # Priority 4: Step 5 validation result (fallback for early-stage workflows)
    steps = _as_dict(state.get("steps"))
    step5 = _as_dict(_as_dict(steps.get("5_validate_trades")).get("result"))
    if step5 and (step5.get("total_trades") or step5.get("profit") or step5.get("profit_factor") or step5.get("max_drawdown_pct")):
        return {
            "profit": step5.get("profit", 0),
            "profit_factor": step5.get("profit_factor", 0),
            "max_drawdown_pct": step5.get("max_drawdown_pct", 0),
            "total_trades": step5.get("total_trades", 0),
            "win_rate": step5.get("win_rate", 0),
            "forward_result": 0,
            "back_result": 0,
        }

    return {}


def generate_boards(
    runs_dir: str = "runs",
    output_dir: Optional[str] = None,
    open_browser: bool = False,
) -> str:
    runs_path = Path(runs_dir)
    out_dir = Path(output_dir) if output_dir else (runs_path / "boards")
    out_dir.mkdir(parents=True, exist_ok=True)

    workflows: list[dict[str, Any]] = []
    scenarios: list[dict[str, Any]] = []

    # Statuses to exclude from boards (stuck/failed workflows)
    EXCLUDED_STATUSES = {'failed', 'awaiting_param_analysis', 'awaiting_stats_analysis', 'awaiting_ea_fix', 'pending'}

    for state_file in sorted(runs_path.glob("workflow_*.json")):
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        workflow_id = state.get("workflow_id") or state_file.stem.replace("workflow_", "")
        ea_name = state.get("ea_name", "Unknown")
        symbol = state.get("symbol", "")
        timeframe = state.get("timeframe", "")
        created_at = state.get("created_at", "")
        status = state.get("status", "")

        # Skip failed/stuck workflows
        if status in EXCLUDED_STATUSES:
            continue

        metrics = _best_workflow_metrics(state)
        notes = _generate_notes(state)

        # Calculate Go Live Score from metrics
        go_live_score = calculate_composite_score(metrics)

        go_live = _as_dict(state.get("go_live"))
        go_live_ready = go_live.get("go_live_ready") if go_live else None

        forward_result = float(metrics.get("forward_result") or 0)
        back_result = float(metrics.get("back_result") or 0)

        workflows.append(
            {
                "workflow_id": workflow_id,
                "ea_name": ea_name,
                "symbol": symbol,
                "timeframe": timeframe,
                "created_at": created_at,
                "created_at_fmt": _format_date(created_at),
                "status": status,
                "notes": notes,
                "score_num": go_live_score,
                "profit_num": float(metrics.get("profit") or 0),
                "pf_num": float(metrics.get("profit_factor") or 0),
                "dd_num": float(metrics.get("max_drawdown_pct") or 0),
                "trades_num": int(metrics.get("total_trades") or 0),
                "win_rate_num": float(metrics.get("win_rate") or 0),
                "forward_num": forward_result,
                "back_num": back_result,
                "go_live_ready": go_live_ready,
                "dashboard_link": f"../dashboards/{workflow_id}/index.html",
            }
        )

        stress = _as_dict(state.get("stress_scenarios"))
        for s in _as_list(stress.get("scenarios")):
            if not isinstance(s, dict):
                continue
            set_ = _as_dict(s.get("settings"))
            res = _as_dict(s.get("result"))
            window = _as_dict(s.get("window"))

            scenarios.append(
                {
                    "workflow_id": workflow_id,
                    "ea_name": ea_name,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "created_at": created_at,
                    "dashboard_link": f"../dashboards/{workflow_id}/index.html",
                    "scenario_id": s.get("id"),
                    "scenario_label": s.get("label") or s.get("id") or "Scenario",
                    "success": bool(s.get("success")),
                    "variant": s.get("variant") or "base",
                    "tags": list(s.get("tags") or []),
                    "window_id": window.get("id") or s.get("period") or "",
                    "window_label": window.get("label") or "",
                    "from_date": set_.get("from_date"),
                    "to_date": set_.get("to_date"),
                    "model": set_.get("model"),
                    "execution_latency_ms": set_.get("execution_latency_ms"),
                    "spread_points": set_.get("spread_points"),
                    "overlay_spread_pips": set_.get("overlay_spread_pips"),
                    "overlay_slippage_pips": set_.get("overlay_slippage_pips"),
                    "overlay_slippage_sides": set_.get("overlay_slippage_sides"),
                    "profit_num": float(res.get("profit") or 0),
                    "pf_num": float(res.get("profit_factor") or 0),
                    "dd_num": float(res.get("max_drawdown_pct") or 0),
                    "trades_num": int(res.get("total_trades") or 0),
                    "hq_num": float(res.get("history_quality_pct") or 0),
                    "tick_files_ok": res.get("tick_files_ok"),
                    "tick_files_missing": res.get("tick_files_missing"),
                    "errors": list(s.get("errors") or []),
                }
            )

        fw = _as_dict(state.get("forward_windows"))
        for w in _as_list(fw.get("windows")):
            if not isinstance(w, dict):
                continue
            metrics_w = _as_dict(w.get("metrics"))
            scenarios.append(
                {
                    "workflow_id": workflow_id,
                    "ea_name": ea_name,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "created_at": created_at,
                    "dashboard_link": f"../dashboards/{workflow_id}/index.html",
                    "scenario_id": f"forward::{w.get('id')}",
                    "scenario_label": f"Forward Window: {w.get('label') or w.get('id') or 'window'}",
                    "success": bool(fw.get("success", True)),
                    "variant": "forward_window",
                    "tags": ["forward", w.get("kind")],
                    "window_id": w.get("id") or "",
                    "window_label": w.get("label") or "",
                    "from_date": w.get("from_date"),
                    "to_date": w.get("to_date"),
                    "model": fw.get("model", 1),
                    "execution_latency_ms": None,
                    "spread_points": None,
                    "overlay_spread_pips": None,
                    "overlay_slippage_pips": None,
                    "overlay_slippage_sides": None,
                    "profit_num": float(metrics_w.get("profit") or 0),
                    "pf_num": float(metrics_w.get("profit_factor") or 0),
                    "dd_num": float(metrics_w.get("max_drawdown_pct") or 0),
                    "trades_num": int(metrics_w.get("total_trades") or 0),
                    "hq_num": float(fw.get("history_quality_pct") or 0),
                    "tick_files_ok": None,
                    "tick_files_missing": None,
                    "errors": [fw.get("error")] if fw.get("error") else [],
                }
            )

    workflows.sort(key=lambda w: w.get("created_at", ""), reverse=True)

    data = {
        "workflows": workflows,
        "scenarios": scenarios,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "counts": {
            "workflows": len(workflows),
            "scenarios": len(scenarios),
            "unique_eas": len({w.get("ea_name") for w in workflows}),
            "unique_symbols": len({w.get("symbol") for w in workflows}),
        },
    }

    template = (TEMPLATES_DIR / "boards_spa.html").read_text(encoding="utf-8")
    html = template.replace("{{DATA_JSON}}", json.dumps(data, indent=2))

    output_path = out_dir / "index.html"
    output_path.write_text(html, encoding="utf-8")
    (out_dir / "data.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Convenience: keep a Desktop shortcut up to date on Windows.
    try:
        if sys.platform.startswith("win"):
            desktop = Path(os.path.expanduser("~")) / "Desktop"
            if desktop.exists():
                shortcut = desktop / "EA Stress Test Boards.url"
                shortcut.write_text(
                    "[InternetShortcut]\n" f"URL={output_path.resolve().as_uri()}\n",
                    encoding="utf-8",
                )
    except Exception:
        pass

    if open_browser:
        import webbrowser

        webbrowser.open(f"file://{output_path.absolute()}")

    return str(output_path)


if __name__ == "__main__":
    path = generate_boards(open_browser=True)
    print(f"Generated: {path}")
