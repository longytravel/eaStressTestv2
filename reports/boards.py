"""
Boards Generator

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

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _best_workflow_metrics(state: dict[str, Any]) -> dict[str, Any]:
    metrics = _as_dict(state.get("metrics"))
    if any(k in metrics for k in ("profit", "profit_factor", "max_drawdown_pct", "total_trades")) and (
        metrics.get("total_trades") or metrics.get("profit") or metrics.get("profit_factor") or metrics.get("max_drawdown_pct")
    ):
        return metrics

    steps = _as_dict(state.get("steps"))
    step5 = _as_dict(_as_dict(steps.get("5_validate_trades")).get("result"))
    if step5 and (step5.get("total_trades") or step5.get("profit") or step5.get("profit_factor") or step5.get("max_drawdown_pct")):
        return {
            "profit": step5.get("profit", 0),
            "profit_factor": step5.get("profit_factor", 0),
            "max_drawdown_pct": step5.get("max_drawdown_pct", 0),
            "total_trades": step5.get("total_trades", 0),
            "sharpe_ratio": step5.get("sharpe_ratio", 0),
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
        score = state.get("composite_score", 0) or 0
        go_live = _as_dict(state.get("go_live"))
        go_live_ready = go_live.get("go_live_ready") if go_live else None

        metrics = _best_workflow_metrics(state)
        workflows.append(
            {
                "workflow_id": workflow_id,
                "ea_name": ea_name,
                "symbol": symbol,
                "timeframe": timeframe,
                "created_at": created_at,
                "status": status,
                "score_num": float(score or 0),
                "profit_num": float(metrics.get("profit") or 0),
                "pf_num": float(metrics.get("profit_factor") or 0),
                "dd_num": float(metrics.get("max_drawdown_pct") or 0),
                "trades_num": int(metrics.get("total_trades") or 0),
                "sharpe_num": float(metrics.get("sharpe_ratio") or 0),
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
