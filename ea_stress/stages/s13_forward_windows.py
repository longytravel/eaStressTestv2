"""
Stage 13: Forward Windows

Compute time-window metrics from trade list (no MT5 runs).
Analyzes performance across different time periods.
"""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from ea_stress.stages.base import StageResult

if TYPE_CHECKING:
    from ea_stress.core.state import WorkflowState
    from ea_stress.mt5.interface import MT5Interface


class ForwardWindowsStage:
    """Stage 13: Compute time-window metrics from trade list."""

    @property
    def name(self) -> str:
        return "13_forward_windows"

    def execute(
        self,
        state: "WorkflowState",
        mt5: "MT5Interface | None" = None,
    ) -> StageResult:
        """Execute forward window analysis.

        Requires:
            - Step 9 (backtest_passes) completed with best pass report

        Computes metrics for:
            - Full period
            - In-sample vs forward (out-of-sample)
            - Rolling windows (7/14/30/60/90 days)
            - Calendar months
            - Yearly breakdown

        Args:
            state: Current workflow state
            mt5: MT5 interface (not required - pure trade list analysis)

        Returns:
            StageResult with window metrics (informational, no gate)
        """
        import settings

        # Get best pass from Step 9
        step_9 = state.steps.get("9_backtest_passes")
        if not step_9 or not step_9.passed or not step_9.result:
            return StageResult(
                success=True,
                data={"skipped": True, "reason": "No best-pass results from Step 9"},
                gate=None,
                errors=(),
            )

        best_pass = step_9.result.get("best_pass")
        if not best_pass:
            return StageResult(
                success=True,
                data={"skipped": True, "reason": "No best pass selected in Step 9"},
                gate=None,
                errors=(),
            )

        report_path = best_pass.get("report_path")
        pass_num = best_pass.get("pass_num", 0)

        if not report_path:
            return StageResult(
                success=True,
                data={"skipped": True, "reason": "No report path for best pass"},
                gate=None,
                errors=(),
            )

        # Extract trades from report
        trades = self._extract_trades(report_path)
        if not trades:
            return StageResult(
                success=True,
                data={
                    "skipped": True,
                    "reason": "No trades extracted from report",
                    "pass_num": pass_num,
                    "report_path": report_path,
                },
                gate=None,
                errors=(),
            )

        # Sort trades by close time
        trades = sorted(trades, key=lambda t: t.get("close_time", datetime.min))

        # Parse dates
        try:
            start_date = datetime.strptime(state.start_date, "%Y.%m.%d")
            end_date = datetime.strptime(state.end_date, "%Y.%m.%d")
        except (ValueError, TypeError):
            start_date = datetime.now() - timedelta(days=365 * 4)
            end_date = datetime.now()

        # Calculate split date for in-sample/forward
        forward_years = getattr(settings, "FORWARD_YEARS", 1)
        split_date = end_date - timedelta(days=365 * forward_years)

        # Get initial balance
        initial_balance = getattr(settings, "DEPOSIT", 3000)

        # Build windows
        windows = []

        # Segment windows: full, in_sample, forward
        windows.append(self._build_window(
            window_id="full",
            label="Full period",
            kind="full",
            from_date=start_date,
            to_date=end_date,
            trades=trades,
            initial_balance=initial_balance,
        ))

        windows.append(self._build_window(
            window_id="in_sample",
            label="In-sample",
            kind="segment",
            from_date=start_date,
            to_date=split_date,
            trades=trades,
            initial_balance=initial_balance,
        ))

        windows.append(self._build_window(
            window_id="forward",
            label="Forward",
            kind="segment",
            from_date=split_date,
            to_date=end_date,
            trades=trades,
            initial_balance=initial_balance,
        ))

        # Rolling windows (reuse stress settings)
        rolling_days = getattr(settings, "STRESS_WINDOW_ROLLING_DAYS", [7, 14, 30, 60, 90])
        for days in rolling_days:
            window_start = end_date - timedelta(days=days)
            windows.append(self._build_window(
                window_id=f"last_{days}d",
                label=f"Last {days} days",
                kind="rolling",
                from_date=window_start,
                to_date=end_date,
                trades=trades,
                initial_balance=initial_balance,
            ))

        # Calendar months (reuse stress settings)
        calendar_months = getattr(settings, "STRESS_WINDOW_CALENDAR_MONTHS_AGO", [1, 2, 3])
        for months_ago in calendar_months:
            month_date = end_date.replace(day=1)
            for _ in range(months_ago):
                month_date = (month_date - timedelta(days=1)).replace(day=1)

            if month_date.month == 12:
                next_month = month_date.replace(year=month_date.year + 1, month=1, day=1)
            else:
                next_month = month_date.replace(month=month_date.month + 1, day=1)
            month_end = next_month - timedelta(days=1)

            windows.append(self._build_window(
                window_id=f"month_{month_date.year}_{month_date.month:02d}",
                label=month_date.strftime("%b %Y"),
                kind="calendar",
                from_date=month_date,
                to_date=month_end,
                trades=trades,
                initial_balance=initial_balance,
            ))

        # Yearly windows
        start_year = start_date.year
        end_year = end_date.year
        for year in range(start_year, end_year + 1):
            year_start = datetime(year, 1, 1)
            year_end = datetime(year, 12, 31)

            # Clamp to actual range
            if year_start < start_date:
                year_start = start_date
            if year_end > end_date:
                year_end = end_date

            windows.append(self._build_window(
                window_id=f"year_{year}",
                label=f"Year {year}",
                kind="year",
                from_date=year_start,
                to_date=year_end,
                trades=trades,
                initial_balance=initial_balance,
            ))

        return StageResult(
            success=True,
            data={
                "pass_num": pass_num,
                "report_path": report_path,
                "window_count": len(windows),
                "windows": windows,
            },
            gate=None,
            errors=(),
        )

    def _extract_trades(self, report_path: str) -> list[dict[str, Any]]:
        """Extract trade list from HTML report.

        Returns list of trades with:
            - close_time: datetime
            - net_profit: float
        """
        # This would use trade_extractor module
        # For now, return empty list (stub)
        # Real implementation would parse HTML report
        return []

    def _build_window(
        self,
        window_id: str,
        label: str,
        kind: str,
        from_date: datetime,
        to_date: datetime,
        trades: list[dict[str, Any]],
        initial_balance: float,
    ) -> dict[str, Any]:
        """Build window with computed metrics."""
        metrics = self._compute_metrics(
            trades=trades,
            window_start=from_date,
            window_end=to_date,
            initial_balance=initial_balance,
        )

        return {
            "id": window_id,
            "label": label,
            "kind": kind,
            "from_date": from_date.strftime("%Y.%m.%d"),
            "to_date": to_date.strftime("%Y.%m.%d"),
            "metrics": metrics,
        }

    def _compute_metrics(
        self,
        trades: list[dict[str, Any]],
        window_start: datetime,
        window_end: datetime,
        initial_balance: float,
    ) -> dict[str, Any]:
        """Compute metrics for a time window.

        Algorithm:
        1. Calculate starting balance (initial + all trades before window)
        2. Filter trades by close_time within window
        3. Track profit, drawdown, wins/losses
        """
        # Calculate starting balance at window_start
        balance = initial_balance
        for trade in trades:
            close_time = trade.get("close_time")
            if close_time and close_time < window_start:
                balance += trade.get("net_profit", 0)
            elif close_time and close_time >= window_start:
                break

        start_balance = balance
        peak = start_balance
        max_dd = 0.0

        profit = 0.0
        gross_profit = 0.0
        gross_loss = 0.0
        wins = 0
        total = 0

        for trade in trades:
            close_time = trade.get("close_time")
            if not close_time:
                continue
            if close_time < window_start:
                continue
            if close_time > window_end:
                break

            p = trade.get("net_profit", 0)
            total += 1
            profit += p

            if p > 0:
                wins += 1
                gross_profit += p
            elif p < 0:
                gross_loss += abs(p)

            # Update drawdown
            balance += p
            if balance > peak:
                peak = balance
            if peak > 0:
                dd = (peak - balance) / peak
                if dd > max_dd:
                    max_dd = dd

        # Calculate profit factor
        if gross_loss <= 0:
            pf = 99.0 if gross_profit > 0 else 0.0
        else:
            pf = gross_profit / gross_loss

        win_rate = (wins / total * 100.0) if total > 0 else 0.0

        return {
            "profit": profit,
            "profit_factor": round(pf, 2),
            "max_drawdown_pct": round(max_dd * 100.0, 2),
            "total_trades": total,
            "win_rate": round(win_rate, 1),
        }
