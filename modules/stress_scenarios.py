"""
Stress Scenario Backtests

Runs additional backtests for a fixed parameter set under different execution/data assumptions
(latency, tick model, short lookback windows, etc.).

This module also supports deterministic, post-hoc cost overlays for spread/slippage by
recomputing metrics from the MT5 trade list (no additional MT5 runs).

These scenarios are meant to be infrastructure-level and EA-agnostic.
"""

from __future__ import annotations

import re
import hashlib
from datetime import datetime, timedelta, date
from pathlib import Path
from statistics import median
from typing import Optional, Any, Iterable, Callable

import settings
from modules.backtest import run_backtest
from modules.trade_extractor import extract_trades


MT5_DATE_FMT = "%Y.%m.%d"


def _sanitize_id(value: str, max_len: int = 60) -> str:
    value = (value or "").strip()
    value = re.sub(r"[^A-Za-z0-9_]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        value = "scenario"
    return value[:max_len]


def _make_report_name(ea_stem: str, scenario_id: str, max_len: int = 60) -> str:
    """
    Generate a short, deterministic report name for MT5.

    Stress scenarios can easily collide when long IDs get truncated into the same filename.
    Keep filenames readable while guaranteeing uniqueness via a hash suffix.
    """
    ea_short = _sanitize_id(ea_stem, max_len=18)
    sc_short = _sanitize_id(scenario_id, max_len=18)
    digest = hashlib.sha1(f"{ea_stem}:{scenario_id}".encode("utf-8")).hexdigest()[:8]
    return _sanitize_id(f"{ea_short}_S12_{sc_short}_{digest}", max_len=max_len)


def _parse_mt5_date(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(str(value), MT5_DATE_FMT)
    except Exception:
        return None


def _fmt_mt5_date(value: datetime | date) -> str:
    if isinstance(value, datetime):
        value = value.date()
    return value.strftime(MT5_DATE_FMT)


def _pips_to_points(pips: float) -> int:
    try:
        return int(round(float(pips) * float(getattr(settings, "PIP_TO_POINTS", 10) or 10)))
    except Exception:
        return 0


def _canonical_symbol(symbol: str) -> str:
    return re.sub(r"[^A-Za-z]", "", symbol or "").upper()


def _month_id(dt: datetime | date) -> str:
    if isinstance(dt, datetime):
        dt = dt.date()
    return f"{dt.year:04d}{dt.month:02d}"


def _iter_month_ids(start_dt: date, end_dt: date) -> list[str]:
    months: list[str] = []
    year = start_dt.year
    month = start_dt.month
    while (year, month) <= (end_dt.year, end_dt.month):
        months.append(f"{year:04d}{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def _find_tick_symbol_dir(data_path: str, symbol: str) -> tuple[Optional[Path], Optional[str]]:
    """
    Best-effort locate the MT5 tick storage folder for a given symbol.

    MT5 stores ticks at: <data_path>/bases/<server>/ticks/<SYMBOL>/
    """
    base_path = Path(str(data_path or "")).expanduser()
    bases = base_path / "bases"
    if not bases.exists():
        return None, None

    sym = _canonical_symbol(symbol) or str(symbol or "").strip()
    if not sym:
        return None, None

    candidates: list[tuple[tuple[int, int, int], Path, str]] = []
    for server_dir in bases.iterdir():
        if not server_dir.is_dir():
            continue
        tick_dir = server_dir / "ticks" / sym
        if not tick_dir.exists():
            continue

        tkc_files = list(tick_dir.glob("*.tkc"))
        tkc_count = len(tkc_files)
        tkc_size = 0
        for f in tkc_files:
            try:
                tkc_size += int(f.stat().st_size)
            except Exception:
                continue

        ticks_dat = tick_dir / "ticks.dat"
        ticks_dat_size = 0
        if ticks_dat.exists():
            try:
                ticks_dat_size = int(ticks_dat.stat().st_size)
            except Exception:
                ticks_dat_size = 0

        candidates.append(((tkc_count, tkc_size, ticks_dat_size), tick_dir, server_dir.name))

    if not candidates:
        return None, None

    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates[0][1], candidates[0][2]


def _tick_file_coverage(
    terminal_data_path: str,
    symbol: str,
    from_date: str,
    to_date: str,
) -> dict[str, Any]:
    """
    Side-channel validation for tick-model scenarios.

    MT5 "History Quality" can still show 100% even when the terminal doesn't have
    monthly `.tkc` real-tick files for the window (MT5 can synthesize ticks).
    This checks whether the expected `.tkc` files exist for each month in-range.
    """
    start_dt = _parse_mt5_date(from_date)
    end_dt = _parse_mt5_date(to_date)
    if start_dt is None or end_dt is None:
        return {
            "success": False,
            "error": "Invalid from/to date",
            "months_needed": [],
            "months_present": [],
            "months_missing": [],
            "coverage_ok": False,
        }

    tick_dir, server = _find_tick_symbol_dir(terminal_data_path, symbol)
    if tick_dir is None:
        return {
            "success": False,
            "error": "Tick directory not found",
            "server": server,
            "tick_dir": None,
            "months_needed": [],
            "months_present": [],
            "months_missing": [],
            "coverage_ok": False,
        }

    months_needed = _iter_month_ids(start_dt.date(), end_dt.date())
    months_present: list[str] = []
    months_missing: list[str] = []

    for mid in months_needed:
        f = tick_dir / f"{mid}.tkc"
        if f.exists():
            months_present.append(mid)
        else:
            months_missing.append(mid)

    ticks_dat = tick_dir / "ticks.dat"
    ticks_dat_used = False
    live_month = _month_id(datetime.now())
    end_month = _month_id(end_dt)

    # `ticks.dat` is a live cache; treat it as coverage ONLY for the current calendar month.
    if end_month == live_month and ticks_dat.exists():
        try:
            if ticks_dat.stat().st_size > 0 and end_month in months_missing:
                months_missing.remove(end_month)
                ticks_dat_used = True
        except Exception:
            pass

    coverage_ok = len(months_missing) == 0

    return {
        "success": True,
        "server": server,
        "tick_dir": str(tick_dir),
        "months_needed": months_needed,
        "months_present": months_present,
        "months_missing": months_missing,
        "ticks_dat_used": ticks_dat_used,
        "coverage_ok": coverage_ok,
    }


def _infer_pip_size(symbol: str, sample_prices: Iterable[float] = ()) -> float:
    sym = _canonical_symbol(symbol)
    if len(sym) >= 6:
        quote = sym[3:6]
        if quote == "JPY":
            return 0.01
        return 0.0001

    # Fallback: infer from decimals (best-effort)
    digits = 0
    for p in sample_prices:
        s = f"{p:.10f}".rstrip("0").rstrip(".")
        if "." in s:
            digits = max(digits, len(s.split(".")[1]))
    if digits >= 4:
        return 0.0001
    if digits == 3:
        return 0.01
    if digits == 2:
        return 0.01
    return 0.0001


def _max_drawdown_pct(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0] if equity_curve[0] != 0 else max(equity_curve[0], 1e-9)
    max_dd = 0.0
    for v in equity_curve:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd * 100.0


def _profit_factor(trade_profits: list[float]) -> float:
    gross_profit = sum(p for p in trade_profits if p > 0)
    gross_loss = abs(sum(p for p in trade_profits if p < 0))
    if gross_loss <= 1e-12:
        return 99.0 if gross_profit > 0 else 0.0
    return float(gross_profit) / float(gross_loss)


def _estimate_pip_value_per_lot(trades, symbol: str) -> Optional[float]:
    prices = []
    pip_values = []

    for t in trades:
        if not getattr(t, "open_price", 0) or not getattr(t, "close_price", 0):
            continue
        if not getattr(t, "volume", 0):
            continue
        prices.append(float(t.open_price))
        prices.append(float(t.close_price))

    pip_size = _infer_pip_size(symbol, prices)
    if pip_size <= 0:
        return None

    for t in trades:
        try:
            vol = float(getattr(t, "volume", 0) or 0)
            if vol <= 0:
                continue

            open_p = float(getattr(t, "open_price", 0) or 0)
            close_p = float(getattr(t, "close_price", 0) or 0)
            diff = abs(close_p - open_p)
            if diff <= 0:
                continue

            pips = diff / pip_size
            if pips <= 0:
                continue

            gross = float(getattr(t, "gross_profit", 0) or 0)
            if gross == 0:
                gross = float(getattr(t, "net_profit", 0) or 0)
            if gross == 0:
                continue

            pv = abs(gross) / (pips * vol)
            if pv <= 0 or pv > 1e6:
                continue
            pip_values.append(pv)
        except Exception:
            continue

    if not pip_values:
        return None

    # Median is robust to outliers and conversion rate drift
    try:
        return float(median(pip_values))
    except Exception:
        return None


def _load_overlay_base_from_report(report_path: str, symbol: str) -> tuple[bool, dict, list[str]]:
    errors: list[str] = []

    trades_res = extract_trades(report_path)
    if not trades_res.success or not trades_res.trades:
        errors.append(trades_res.error or "Failed to extract trades from report")
        return False, {}, errors

    pip_value = _estimate_pip_value_per_lot(trades_res.trades, symbol)
    if pip_value is None:
        errors.append("Could not estimate pip value for overlay costs")
        return False, {}, errors

    return True, {"trades_res": trades_res, "pip_value": pip_value}, errors


def _apply_cost_overlay(
    trades_res,
    pip_value_per_lot: float,
    spread_pips: float,
    slippage_pips: float,
    slippage_sides: int,
) -> dict:
    try:
        spread_pips_f = float(spread_pips or 0)
        slippage_pips_f = float(slippage_pips or 0)
        slippage_sides_i = int(slippage_sides or 0)
        if slippage_sides_i < 0:
            slippage_sides_i = 0
    except Exception:
        spread_pips_f = 0.0
        slippage_pips_f = 0.0
        slippage_sides_i = 0

    extra_pips = max(0.0, spread_pips_f) + max(0.0, slippage_pips_f) * slippage_sides_i

    # Compute adjusted profits and equity-based drawdown using close-time ordering.
    initial_balance = trades_res.initial_balance or float(getattr(settings, "DEPOSIT", 0) or 0)
    rows = []
    overlay_cost_total = 0.0

    for t in trades_res.trades:
        vol = float(getattr(t, "volume", 0) or 0)
        cost = float(pip_value_per_lot) * vol * extra_pips
        overlay_cost_total += cost
        adj = float(getattr(t, "net_profit", 0) or 0) - cost
        rows.append((getattr(t, "close_time", None), adj))

    rows.sort(key=lambda x: x[0] or datetime.min)

    profit = 0.0
    gross_profit = 0.0
    gross_loss = 0.0

    balance = float(initial_balance or 0)
    peak = balance if balance != 0 else max(balance, 1e-9)
    max_dd = 0.0

    for _, p in rows:
        profit += p
        if p > 0:
            gross_profit += p
        elif p < 0:
            gross_loss += abs(p)

        balance += p
        if balance > peak:
            peak = balance
        if peak > 0:
            dd = (peak - balance) / peak
            if dd > max_dd:
                max_dd = dd

    pf = 0.0
    if gross_loss <= 1e-12:
        pf = 99.0 if gross_profit > 0 else 0.0
    else:
        pf = gross_profit / gross_loss

    return {
        "profit": float(profit),
        "profit_factor": float(pf),
        "max_drawdown_pct": float(max_dd * 100.0),
        "total_trades": len(trades_res.trades),
        "overlay": {
            "spread_pips": spread_pips_f,
            "slippage_pips": slippage_pips_f,
            "slippage_sides": slippage_sides_i,
            "extra_pips_total": float(extra_pips),
            "pip_value_per_lot_est": float(pip_value_per_lot),
            "overlay_cost_total": float(overlay_cost_total),
        },
    }


def _get_dates_for_period(period: str, overrides: dict, workflow_dates: Optional[dict] = None) -> tuple[str, str]:
    # Explicit overrides (used to align to a stored workflow date range)
    if isinstance(overrides, dict):
        fd = overrides.get("from_date")
        td = overrides.get("to_date")
        if fd and td:
            return str(fd), str(td)

    period = (period or "full").strip().lower()

    if period == "full":
        dates = workflow_dates or settings.get_backtest_dates()
        return dates["start"], dates["end"]

    if period == "tick":
        lookback_days = overrides.get("lookback_days", settings.TICK_VALIDATION_DAYS)
        try:
            lookback_days = int(lookback_days)
        except Exception:
            lookback_days = settings.TICK_VALIDATION_DAYS
        anchor = None
        if workflow_dates:
            anchor = _parse_mt5_date(workflow_dates.get("end"))
        if anchor is None:
            anchor = datetime.now()
        start_dt = anchor - timedelta(days=lookback_days)
        return _fmt_mt5_date(start_dt), _fmt_mt5_date(anchor)

    dates = workflow_dates or settings.get_backtest_dates()
    return dates["start"], dates["end"]


def build_dynamic_scenarios(workflow_dates: Optional[dict[str, str]] = None) -> list[dict[str, Any]]:
    """
    Build the default stress scenario suite dynamically.

    Windows are anchored to the workflow end date for reproducibility.
    """
    workflow_dates = workflow_dates or settings.get_backtest_dates()
    anchor = _parse_mt5_date(workflow_dates.get("end")) or datetime.now()

    scenarios: list[dict[str, Any]] = []

    rolling_days = list(getattr(settings, "STRESS_WINDOW_ROLLING_DAYS", []) or [])
    calendar_months_ago = list(getattr(settings, "STRESS_WINDOW_CALENDAR_MONTHS_AGO", []) or [])
    models = list(getattr(settings, "STRESS_WINDOW_MODELS", [1, 0]) or [1, 0])
    tick_latencies = list(getattr(settings, "STRESS_TICK_LATENCY_MS", []) or [])

    def add_window(window_id: str, window_label: str, start_dt: datetime, end_dt: datetime) -> None:
        from_date = _fmt_mt5_date(start_dt)
        to_date = _fmt_mt5_date(end_dt)
        for model in models:
            if int(model) not in (0, 1):
                continue
            model_name = "tick" if int(model) == 0 else "ohlc"
            base_id = f"{model_name}_{window_id}"
            scenarios.append({
                "id": base_id,
                "label": f"{'Tick' if int(model)==0 else 'OHLC (1m)'} - {window_label}",
                "period": window_id,
                "window": {
                    "id": window_id,
                    "label": window_label,
                    "from_date": from_date,
                    "to_date": to_date,
                },
                "overrides": {
                    "model": int(model),
                    "from_date": from_date,
                    "to_date": to_date,
                },
                "tags": ["window", model_name],
            })

            if int(model) == 0 and tick_latencies:
                for lat in tick_latencies:
                    try:
                        lat_i = int(lat)
                    except Exception:
                        continue
                    scenarios.append({
                        "id": f"{base_id}_latency_{lat_i}ms",
                        "label": f"Tick + latency {lat_i}ms - {window_label}",
                        "period": window_id,
                        "window": {
                            "id": window_id,
                            "label": window_label,
                            "from_date": from_date,
                            "to_date": to_date,
                        },
                        "overrides": {
                            "model": 0,
                            "execution_latency_ms": lat_i,
                            "from_date": from_date,
                            "to_date": to_date,
                        },
                        "tags": ["window", "tick", "latency"],
                    })

    # Rolling windows (e.g., last 30d)
    for days in rolling_days:
        try:
            d = int(days)
        except Exception:
            continue
        if d <= 0:
            continue
        start_dt = anchor - timedelta(days=d)
        add_window(f"last_{d}d", f"Last {d} days", start_dt, anchor)

    # Calendar months (e.g., last month, two months ago)
    for months_ago in calendar_months_ago:
        try:
            m = int(months_ago)
        except Exception:
            continue
        if m <= 0:
            continue

        # First day of anchor month
        anchor_month_start = date(anchor.year, anchor.month, 1)
        # Compute target month by subtracting m months
        year = anchor_month_start.year
        month = anchor_month_start.month - m
        while month <= 0:
            year -= 1
            month += 12
        target_start = date(year, month, 1)
        # End = day before next month
        next_month_year = year + (1 if month == 12 else 0)
        next_month = 1 if month == 12 else month + 1
        target_end = date(next_month_year, next_month, 1) - timedelta(days=1)

        window_id = f"month_{target_start.year}_{target_start.month:02d}"
        window_label = target_start.strftime("%b %Y")
        add_window(window_id, window_label, datetime.combine(target_start, datetime.min.time()), datetime.combine(target_end, datetime.min.time()))

    return scenarios


def run_stress_scenarios(
    compiled_ea_path: str,
    symbol: str,
    timeframe: str,
    params: dict,
    terminal: dict,
    scenarios: Optional[list[dict[str, Any]]] = None,
    timeout_per_scenario: int = 900,
    workflow_dates: Optional[dict[str, str]] = None,
    baseline: Optional[dict[str, Any]] = None,
    include_overlays: Optional[bool] = None,
    on_progress: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    Run stress scenarios for a compiled EA.

    - Base scenarios are executed in MT5.
    - Optional cost overlays (spread/slippage) are computed post-hoc from the trade list.

    Args:
        compiled_ea_path: Path to compiled .ex5
        symbol: e.g. "GBPUSD"
        timeframe: e.g. "H1"
        params: Fixed input parameters for the pass under test
        terminal: Terminal config dict
        scenarios: Optional override list. If None, uses settings.STRESS_SCENARIOS or a dynamic suite.
        timeout_per_scenario: Max seconds per scenario backtest
        workflow_dates: Backtest dates dict from workflow state (used for dynamic suite anchoring)
        baseline: Optional dict for baseline overlays. Expected keys: report_path, profit_factor, etc.
        include_overlays: Override settings.STRESS_INCLUDE_OVERLAYS

    Returns:
        dict with:
          - success: bool
          - scenario_count: int
          - scenarios: list of scenario result dicts (some may fail individually)
    """
    scenario_defs = scenarios if scenarios is not None else getattr(settings, "STRESS_SCENARIOS", None)
    if scenario_defs is None:
        scenario_defs = build_dynamic_scenarios(workflow_dates=workflow_dates)
    scenario_defs = list(scenario_defs or [])

    ea_stem = Path(compiled_ea_path).stem
    prefix = _sanitize_id(f"{ea_stem}_STRESS", max_len=40)

    results: list[dict] = []
    overlay_bases: list[dict] = []

    # Baseline can participate in overlay generation without being shown as a scenario row.
    if isinstance(baseline, dict) and baseline.get("report_path"):
        base_settings = baseline.get("settings", {}) if isinstance(baseline.get("settings"), dict) else {}
        base_from = base_settings.get("from_date")
        base_to = base_settings.get("to_date")
        overlay_bases.append({
            "id": "baseline_full",
            "label": "Baseline (best pass) - full period",
            "period": "full",
            "window": {
                "id": "full",
                "label": "Full period",
                "from_date": base_from,
                "to_date": base_to,
            },
            "settings": base_settings,
            "result": {
                "profit": baseline.get("profit", 0),
                "profit_factor": baseline.get("profit_factor", 0),
                "max_drawdown_pct": baseline.get("max_drawdown_pct", 0),
                "total_trades": baseline.get("total_trades", 0),
                "history_quality_pct": baseline.get("history_quality_pct", 0),
                "bars": baseline.get("bars", 0),
                "ticks": baseline.get("ticks", 0),
                "symbols": baseline.get("symbols", 0),
            },
            "report_path": baseline.get("report_path"),
            "tags": ["baseline", "ohlc"],
        })

    for s in scenario_defs:
        if not isinstance(s, dict):
            continue

        scenario_id = _sanitize_id(str(s.get("id") or "scenario"))
        label = str(s.get("label") or scenario_id)
        period = str(s.get("period") or "full")
        overrides = s.get("overrides") if isinstance(s.get("overrides"), dict) else {}

        from_date, to_date = _get_dates_for_period(period, overrides, workflow_dates=workflow_dates)

        model = overrides.get("model", settings.DATA_MODEL)
        execution_latency_ms = overrides.get("execution_latency_ms", settings.EXECUTION_LATENCY_MS)

        spread_points = overrides.get("spread_points")
        if spread_points is None and "spread_pips" in overrides:
            spread_points = _pips_to_points(overrides.get("spread_pips"))
        if spread_points is not None:
            try:
                spread_points = int(spread_points)
            except Exception:
                spread_points = None

        report_name = _make_report_name(ea_stem=ea_stem, scenario_id=scenario_id, max_len=60)

        if on_progress:
            try:
                on_progress(f"Stress {len(results)+1}/{len(scenario_defs)}: {scenario_id} ({from_date} -> {to_date})")
            except Exception:
                pass

        bt = run_backtest(
            compiled_ea_path,
            symbol=symbol,
            timeframe=timeframe,
            params=params,
            from_date=from_date,
            to_date=to_date,
            model=model,
            execution_latency_ms=execution_latency_ms,
            spread=spread_points,
            report_name=report_name,
            terminal=terminal,
            timeout=timeout_per_scenario,
            extract_equity=False,
            on_progress=on_progress,
        )

        tick_files: Optional[dict[str, Any]] = None
        if int(model) == 0:
            tick_files = _tick_file_coverage(
                terminal_data_path=str((terminal or {}).get("data_path") or ""),
                symbol=symbol,
                from_date=from_date,
                to_date=to_date,
            )

        entry = {
            "id": scenario_id,
            "label": label,
            "period": period,
            "window": s.get("window", {}),
            "tags": list(s.get("tags") or []),
            "variant": "base",
            "settings": {
                "from_date": from_date,
                "to_date": to_date,
                "model": model,
                "execution_latency_ms": execution_latency_ms,
                "spread_points": spread_points,
            },
            "report_name": report_name,
            "success": bool(bt.get("success")),
            "result": {
                "profit": bt.get("profit", 0),
                "profit_factor": bt.get("profit_factor", 0),
                "max_drawdown_pct": bt.get("max_drawdown_pct", 0),
                "total_trades": bt.get("total_trades", 0),
                "history_quality_pct": bt.get("history_quality_pct", 0),
                "bars": bt.get("bars", 0),
                "ticks": bt.get("ticks", 0),
                "symbols": bt.get("symbols", 0),
                "tick_files_ok": bool((tick_files or {}).get("coverage_ok")) if isinstance(tick_files, dict) and tick_files.get("success") else None,
                "tick_files_missing": (tick_files or {}).get("months_missing") if isinstance(tick_files, dict) and tick_files.get("success") else None,
            },
            "errors": bt.get("errors", []),
            "report_path": bt.get("report_path"),
            "xml_path": bt.get("xml_path"),
            "tick_files": tick_files,
        }
        results.append(entry)

        if on_progress:
            try:
                r = entry.get("result", {}) if isinstance(entry, dict) else {}
                on_progress(
                    f"Stress {len(results)}/{len(scenario_defs)} {'OK' if entry.get('success') else 'FAIL'}: "
                    f"{scenario_id} profit {float(r.get('profit', 0) or 0):.0f}, "
                    f"PF {float(r.get('profit_factor', 0) or 0):.2f}, "
                    f"trades {int(r.get('total_trades', 0) or 0)}"
                )
            except Exception:
                pass

        # Track eligible bases for overlays (skip latency variants by default)
        if entry["success"] and entry.get("report_path") and "latency" not in set(entry.get("tags") or []):
            overlay_bases.append(entry)

    # Optional overlays
    if include_overlays is None:
        include_overlays = bool(getattr(settings, "STRESS_INCLUDE_OVERLAYS", True))

    if include_overlays:
        if on_progress:
            try:
                on_progress("Stress overlays: computing spread/slippage variants...")
            except Exception:
                pass

        spread_opts = list(getattr(settings, "STRESS_OVERLAY_SPREAD_PIPS", []) or [])
        slip_opts = list(getattr(settings, "STRESS_OVERLAY_SLIPPAGE_PIPS", []) or [])
        sides = int(getattr(settings, "STRESS_OVERLAY_SLIPPAGE_SIDES", 2) or 2)
        overlay_cache: dict[str, dict] = {}

        for base in overlay_bases:
            base_id = str(base.get("id") or "base")
            base_label = str(base.get("label") or base_id)
            base_period = str(base.get("period") or "")
            base_set = base.get("settings", {}) if isinstance(base.get("settings"), dict) else {}
            base_res = base.get("result", {}) if isinstance(base.get("result"), dict) else {}

            report_path = base.get("report_path")
            if not report_path:
                continue

            report_path = str(report_path)
            cached = overlay_cache.get(report_path)
            if cached is None:
                ok_base, overlay_base, overlay_base_errors = _load_overlay_base_from_report(
                    report_path=report_path,
                    symbol=symbol,
                )
                if not ok_base:
                    results.append({
                        "id": _sanitize_id(f"{base_id}_overlay_error", max_len=60),
                        "label": f"{base_label} + costs (overlay unavailable)",
                        "period": base_period,
                        "window": base.get("window", {}),
                        "tags": list(set((base.get("tags") or []) + ["overlay"])),
                        "variant": "overlay",
                        "base_id": base_id,
                        "settings": {**base_set},
                        "success": False,
                        "result": {
                            "profit": base_res.get("profit", 0),
                            "profit_factor": base_res.get("profit_factor", 0),
                            "max_drawdown_pct": base_res.get("max_drawdown_pct", 0),
                            "total_trades": base_res.get("total_trades", 0),
                            "history_quality_pct": base_res.get("history_quality_pct", 0),
                            "bars": base_res.get("bars", 0),
                            "ticks": base_res.get("ticks", 0),
                            "symbols": base_res.get("symbols", 0),
                            "tick_files_ok": base_res.get("tick_files_ok"),
                            "tick_files_missing": base_res.get("tick_files_missing"),
                        },
                        "errors": overlay_base_errors,
                        "report_path": report_path,
                        "xml_path": base.get("xml_path"),
                        "tick_files": base.get("tick_files"),
                    })
                    continue
                overlay_cache[report_path] = overlay_base
                cached = overlay_base

            for sp in spread_opts:
                for sl in slip_opts:
                    try:
                        sp_f = float(sp or 0)
                        sl_f = float(sl or 0)
                    except Exception:
                        continue

                    if sp_f == 0 and sl_f == 0:
                        continue

                    trades_res = cached.get("trades_res")
                    pip_value = cached.get("pip_value")
                    if trades_res is None or pip_value is None:
                        continue

                    overlay_metrics = _apply_cost_overlay(
                        trades_res=trades_res,
                        pip_value_per_lot=float(pip_value),
                        spread_pips=sp_f,
                        slippage_pips=sl_f,
                        slippage_sides=sides,
                    )

                    overlay_id = _sanitize_id(f"{base_id}_overlay_sp{sp_f:g}_sl{sl_f:g}", max_len=60)
                    overlay_label = f"{base_label} + costs (spread {sp_f:g}p, slip {sl_f:g}p x{sides})"

                    results.append({
                        "id": overlay_id,
                        "label": overlay_label,
                        "period": base_period,
                        "window": base.get("window", {}),
                        "tags": list(set((base.get("tags") or []) + ["overlay"])),
                        "variant": "overlay",
                        "base_id": base_id,
                        "settings": {
                            **base_set,
                            "overlay_spread_pips": sp_f,
                            "overlay_slippage_pips": sl_f,
                            "overlay_slippage_sides": sides,
                        },
                        "success": True,
                        "result": {
                            "profit": overlay_metrics.get("profit", 0),
                            "profit_factor": overlay_metrics.get("profit_factor", 0),
                            "max_drawdown_pct": overlay_metrics.get("max_drawdown_pct", 0),
                            "total_trades": overlay_metrics.get("total_trades", base_res.get("total_trades", 0)),
                            "history_quality_pct": base_res.get("history_quality_pct", 0),
                            "bars": base_res.get("bars", 0),
                            "ticks": base_res.get("ticks", 0),
                            "symbols": base_res.get("symbols", 0),
                            "overlay": overlay_metrics.get("overlay", {}),
                            "tick_files_ok": base_res.get("tick_files_ok"),
                            "tick_files_missing": base_res.get("tick_files_missing"),
                        },
                        "errors": [],
                        "report_path": report_path,
                        "xml_path": base.get("xml_path"),
                        "tick_files": base.get("tick_files"),
                    })

        if on_progress:
            try:
                on_progress(f"Stress overlays: done ({len(results):,} total scenario rows)")
            except Exception:
                pass

    return {
        "success": True,
        "scenario_count": len(results),
        "scenarios": results,
    }
