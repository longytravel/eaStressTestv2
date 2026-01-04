from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path


def _now() -> datetime:
    return datetime.now()


def _parse_pid_file(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return None
    if not text:
        return None
    # Expected: "PID=12345"
    if "=" in text:
        text = text.split("=", 1)[1].strip()
    try:
        return int(text)
    except Exception:
        return None


def _pid_running(pid: int) -> bool:
    try:
        import psutil  # type: ignore

        return psutil.pid_exists(pid)
    except Exception:
        # Fallback: best-effort using Windows tasklist
        try:
            import subprocess

            out = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}"], text=True, stderr=subprocess.DEVNULL)
            return str(pid) in out
        except Exception:
            return False


def _tail_text(path: Path, max_bytes: int = 64_000) -> str:
    try:
        data = path.read_bytes()
        if len(data) > max_bytes:
            data = data[-max_bytes:]
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _latest_file(dir_path: Path, pattern: str) -> Path | None:
    try:
        files = list(dir_path.glob(pattern))
    except Exception:
        return None
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return files[0]


def _desktop_path() -> Path:
    # Avoid extra deps; Windows-only repo anyway.
    return Path.home() / "Desktop"


def main() -> int:
    ap = argparse.ArgumentParser(description="Watch the unattended batch run and emit a status heartbeat.")
    ap.add_argument("--runs-dir", default="runs/batch", help="Batch output directory")
    ap.add_argument("--stale-minutes", type=int, default=20, help="Warn if no log updates for this long")
    ap.add_argument("--desktop-alert", action="store_true", help="Write a Desktop alert file if attention needed")
    ap.add_argument("--task-name", default=None, help="Optional name to include in alert/status")
    args = ap.parse_args()

    runs_dir = Path(args.runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)

    pid_file = _latest_file(runs_dir, "*.pid")
    out_log = _latest_file(runs_dir, "*.out.log")
    err_log = _latest_file(runs_dir, "*.err.log")

    pid = _parse_pid_file(pid_file) if pid_file else None
    running = _pid_running(pid) if pid else False

    out_mtime = datetime.fromtimestamp(out_log.stat().st_mtime) if out_log and out_log.exists() else None
    err_size = err_log.stat().st_size if err_log and err_log.exists() else 0

    # Best-effort: current workflow state is the newest workflow JSON in runs/
    workflow = {}
    try:
        wf_root = runs_dir.parent if runs_dir.name.lower() == "batch" else Path("runs")
        wf_files = list(Path(wf_root).glob("workflow_*.json"))
        wf_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        if wf_files:
            workflow = json.loads(wf_files[0].read_text(encoding="utf-8"))
            workflow = {
                "workflow_id": workflow.get("workflow_id"),
                "symbol": workflow.get("symbol"),
                "timeframe": workflow.get("timeframe"),
                "status": workflow.get("status"),
                "current_step": workflow.get("current_step"),
                "updated_at": workflow.get("updated_at"),
            }
    except Exception:
        workflow = {}

    stale = False
    stale_for_minutes = None
    if out_mtime:
        delta = _now() - out_mtime
        stale_for_minutes = int(delta.total_seconds() // 60)
        stale = delta >= timedelta(minutes=int(args.stale_minutes or 20))

    needs_attention = False
    reasons: list[str] = []
    if pid and not running:
        needs_attention = True
        reasons.append(f"batch PID {pid} not running")
    if stale and running:
        needs_attention = True
        reasons.append(f"no stdout updates for ~{stale_for_minutes} min")
    if err_size and err_size > 0:
        tail = _tail_text(err_log) if err_log else ""
        if tail.strip():
            needs_attention = True
            reasons.append("stderr has content")

    status = {
        "ts": _now().isoformat(timespec="seconds"),
        "task": args.task_name,
        "pid_file": str(pid_file) if pid_file else None,
        "pid": pid,
        "pid_running": bool(running),
        "out_log": str(out_log) if out_log else None,
        "out_log_mtime": out_mtime.isoformat(timespec="seconds") if out_mtime else None,
        "stale_for_minutes": stale_for_minutes,
        "err_log": str(err_log) if err_log else None,
        "err_log_size": err_size,
        "workflow": workflow,
        "needs_attention": needs_attention,
        "reasons": reasons,
    }

    (runs_dir / "watchdog_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")

    line = f"[{status['ts']}] ok pid={pid} running={running} stale_min={stale_for_minutes} err={err_size}"
    if needs_attention:
        line += " ATTENTION: " + "; ".join(reasons)
    (runs_dir / "watchdog.log").open("a", encoding="utf-8").write(line + "\n")

    if args.desktop_alert and needs_attention:
        msg = "EA Stress batch needs attention:\n- " + "\n- ".join(reasons)
        msg += f"\n\nStatus: {runs_dir / 'watchdog_status.json'}"
        (_desktop_path() / "EA Stress NEEDS ATTENTION.txt").write_text(msg, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
