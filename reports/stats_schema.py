"""
Stats Analyzer Output Schema

Defines the data structure produced by stats-analyzer skill
and consumed by dashboard/leaderboard.

This is the CONTRACT between analysis and visualization.
"""
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class Metrics:
    """Core performance metrics."""
    profit: float = 0
    profit_factor: float = 0
    max_drawdown_pct: float = 0
    total_trades: int = 0
    win_rate: float = 0
    sharpe_ratio: float = 0
    sortino_ratio: float = 0
    calmar_ratio: float = 0
    recovery_factor: float = 0
    expected_payoff: float = 0


@dataclass
class Gate:
    """Single gate result."""
    name: str
    passed: bool
    value: float
    threshold: float
    operator: str = ">="


@dataclass
class TradePatterns:
    """When and how the EA trades."""
    hourly_distribution: list[int] = field(default_factory=lambda: [0]*24)
    daily_distribution: list[int] = field(default_factory=lambda: [0]*7)  # Mon-Sun
    holding_time_avg_minutes: float = 0
    style: str = "unknown"  # scalper, day_trader, swing, position
    best_hour: int = 0
    worst_hour: int = 0
    best_day: str = ""
    worst_day: str = ""


@dataclass
class RegimePerformance:
    """Performance in a specific market regime."""
    trades: int = 0
    win_rate: float = 0
    profit: float = 0
    avg_trade: float = 0


@dataclass
class MarketRegime:
    """Performance breakdown by market condition."""
    trending: RegimePerformance = field(default_factory=RegimePerformance)
    ranging: RegimePerformance = field(default_factory=RegimePerformance)
    volatile: RegimePerformance = field(default_factory=RegimePerformance)
    dominant_regime: str = "unknown"
    insight: str = ""  # e.g., "Performs 60% better in trending markets"


@dataclass
class ParamStability:
    """Stability analysis for a single parameter."""
    name: str
    stable: bool
    score: float  # 0-1, higher = more stable
    warning: str = ""


@dataclass
class Streaks:
    """Win/loss streak analysis."""
    max_win_streak: int = 0
    max_loss_streak: int = 0
    avg_win_streak: float = 0
    avg_loss_streak: float = 0
    current_streak: int = 0  # positive = wins, negative = losses


@dataclass
class MonteCarlo:
    """Monte Carlo simulation results."""
    iterations: int = 10000
    confidence: float = 0  # % of profitable outcomes
    ruin_probability: float = 100  # % chance of ruin
    median_profit: float = 0
    worst_case_5pct: float = 0
    best_case_95pct: float = 0
    max_drawdown_median: float = 0
    max_drawdown_worst: float = 0


@dataclass
class Diagnosis:
    """Failure diagnosis - WHY and what to fix."""
    failed_gates: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)


@dataclass
class EquityCurve:
    """Equity curve data for charting."""
    dates: list[str] = field(default_factory=list)
    values: list[float] = field(default_factory=list)
    in_sample_end_index: int = 0  # where forward test starts
    drawdown_values: list[float] = field(default_factory=list)


@dataclass
class StatsReport:
    """
    Complete stats-analyzer output.

    This is what the dashboard renders.
    """
    # Identity
    ea_name: str = ""
    symbol: str = ""
    timeframe: str = ""
    terminal: str = ""
    workflow_id: str = ""

    # Period
    period_start: str = ""
    period_end: str = ""
    period_split: str = ""  # in-sample ends here

    # INSIGHTS (the key differentiator)
    edge_summary: str = ""  # What works - 1-2 sentences
    weaknesses: list[str] = field(default_factory=list)  # What needs fixing
    recommendations: list[str] = field(default_factory=list)  # Actionable next steps

    # Core metrics
    metrics: Metrics = field(default_factory=Metrics)

    # Gates
    gates: dict[str, Gate] = field(default_factory=dict)
    all_gates_passed: bool = False

    # Trade patterns
    trade_patterns: TradePatterns = field(default_factory=TradePatterns)

    # Market regime
    market_regime: MarketRegime = field(default_factory=MarketRegime)

    # Parameter stability
    param_stability: list[ParamStability] = field(default_factory=list)
    fragile_params: list[str] = field(default_factory=list)

    # Streaks
    streaks: Streaks = field(default_factory=Streaks)

    # Monte Carlo
    monte_carlo: MonteCarlo = field(default_factory=MonteCarlo)

    # Diagnosis (if gates failed)
    diagnosis: Diagnosis = field(default_factory=Diagnosis)

    # Equity curve
    equity_curve: EquityCurve = field(default_factory=EquityCurve)

    # Final verdict
    composite_score: float = 0  # 0-10
    go_live_ready: bool = False
    status: str = "unknown"  # ready, review, failed, overfit_risk

    # Metadata
    generated_at: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON/template rendering."""
        from dataclasses import asdict
        return asdict(self)


def create_sample_report() -> StatsReport:
    """Create a sample report for testing dashboard."""
    return StatsReport(
        ea_name="TrendFollower_v3",
        symbol="EURUSD",
        timeframe="H1",
        terminal="IC_Markets",
        workflow_id="TrendFollower_v3_20260101_120000",

        period_start="2022-01-01",
        period_end="2026-01-01",
        period_split="2025-01-01",

        # INSIGHTS
        edge_summary="Strong trend-follower with 2.1 profit factor. Best performance during London/NY overlap. Recovers quickly from drawdowns.",
        weaknesses=[
            "Underperforms in ranging markets (45% win rate vs 72% in trends)",
            "StopLoss parameter is fragile - sensitive to small changes",
        ],
        recommendations=[
            "Add ranging market filter to reduce losses during consolidation",
            "Widen StopLoss tolerance or use ATR-based stops",
            "Consider reducing position size during Asian session",
        ],

        metrics=Metrics(
            profit=8240,
            profit_factor=2.1,
            max_drawdown_pct=18.5,
            total_trades=156,
            win_rate=62,
            sharpe_ratio=1.8,
            sortino_ratio=2.3,
            calmar_ratio=2.5,
            recovery_factor=3.2,
            expected_payoff=52.8,
        ),

        gates={
            "profit_factor": Gate("Profit Factor", True, 2.1, 1.5, ">="),
            "max_drawdown": Gate("Max Drawdown", True, 18.5, 30.0, "<="),
            "min_trades": Gate("Min Trades", True, 156, 50, ">="),
            "mc_confidence": Gate("MC Confidence", True, 85.0, 70.0, ">="),
            "mc_ruin": Gate("MC Ruin", True, 2.1, 5.0, "<="),
        },
        all_gates_passed=True,

        trade_patterns=TradePatterns(
            hourly_distribution=[0,0,0,0,2,5,8,12,15,18,16,14,12,15,18,16,12,8,5,3,2,1,0,0],
            daily_distribution=[28,32,35,30,27,4,0],
            holding_time_avg_minutes=240,
            style="day_trader",
            best_hour=14,
            worst_hour=3,
            best_day="Wednesday",
            worst_day="Saturday",
        ),

        market_regime=MarketRegime(
            trending=RegimePerformance(trades=95, win_rate=72, profit=6500, avg_trade=68.4),
            ranging=RegimePerformance(trades=61, win_rate=45, profit=1740, avg_trade=28.5),
            dominant_regime="trending",
            insight="Performs 140% better in trending markets. Consider filtering ranging periods.",
        ),

        param_stability=[
            ParamStability("Period", True, 0.92, ""),
            ParamStability("TakeProfit", True, 0.88, ""),
            ParamStability("StopLoss", False, 0.45, "Fragile - ±10% change causes 35% performance drop"),
            ParamStability("LotSize", True, 0.95, ""),
        ],
        fragile_params=["StopLoss"],

        streaks=Streaks(
            max_win_streak=8,
            max_loss_streak=4,
            avg_win_streak=3.2,
            avg_loss_streak=1.8,
            current_streak=3,
        ),

        monte_carlo=MonteCarlo(
            iterations=10000,
            confidence=85.0,
            ruin_probability=2.1,
            median_profit=7800,
            worst_case_5pct=3200,
            best_case_95pct=12400,
            max_drawdown_median=16.5,
            max_drawdown_worst=28.3,
        ),

        diagnosis=Diagnosis(
            failed_gates=[],
            reasons=[],
            fixes=[],
        ),

        equity_curve=EquityCurve(
            dates=["2022-01", "2022-04", "2022-07", "2022-10", "2023-01", "2023-04", "2023-07", "2023-10", "2024-01", "2024-04", "2024-07", "2024-10", "2025-01", "2025-04", "2025-07", "2025-10", "2026-01"],
            values=[10000, 10800, 11200, 10600, 11800, 12500, 13200, 12800, 14200, 15100, 16000, 15400, 16800, 17500, 17200, 18000, 18240],
            in_sample_end_index=12,
            drawdown_values=[0, 0, 0, 5.4, 0, 0, 0, 3.0, 0, 0, 0, 3.8, 0, 0, 1.7, 0, 0],
        ),

        composite_score=8.2,
        go_live_ready=True,
        status="ready",
        generated_at=datetime.now().isoformat(),
    )
