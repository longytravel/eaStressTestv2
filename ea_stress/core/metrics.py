"""
Trade Metrics and Scoring Domain Models

Dataclasses for trade metrics, gate results, and composite scoring.
"""

from dataclasses import dataclass, field
from typing import Optional


# Go Live Score weights (how important each component is)
GO_LIVE_SCORE_WEIGHTS: dict[str, float] = {
    "consistency": 0.25,      # Both back+forward positive
    "total_profit": 0.25,     # Actual money made
    "trade_count": 0.20,      # Statistical confidence
    "profit_factor": 0.15,    # Edge sustainability
    "max_drawdown": 0.15,     # Risk tolerance
}

# Go Live Score normalization ranges (value ranges for 0-1 scaling)
GO_LIVE_SCORE_RANGES: dict[str, tuple[float, float]] = {
    "total_profit": (0, 5000),       # $0-5000 -> 0-1
    "trade_count": (50, 200),        # 50-200 trades -> 0-1
    "profit_factor": (1.0, 3.0),     # PF 1.0-3.0 -> 0-1
    "max_drawdown": (0, 30),         # DD 0-30% -> 1-0 (inverted)
    "consistency_min": (0, 2000),    # min(back,fwd) $0-2000 -> 0-1
}


def normalize_value(
    value: float,
    min_val: float,
    max_val: float,
    invert: bool = False,
) -> float:
    """
    Normalize a value to 0-1 range.

    Args:
        value: The value to normalize.
        min_val: Minimum of the range (maps to 0).
        max_val: Maximum of the range (maps to 1).
        invert: If True, invert the result (max maps to 0, min to 1).

    Returns:
        Normalized value in range 0-1.
    """
    if max_val <= min_val:
        return 0.0
    clamped = max(min_val, min(max_val, value))
    normalized = (clamped - min_val) / (max_val - min_val)
    return (1.0 - normalized) if invert else normalized


@dataclass
class TradeMetrics:
    """
    Trade performance metrics from a backtest.

    Produced by Step 9 (backtest top passes).

    Attributes:
        profit: Net profit (total).
        profit_factor: Gross profit / gross loss.
        max_drawdown_pct: Maximum equity drawdown percentage.
        total_trades: Total trade count.
        win_rate: Winning trades percentage (0-100).
        sharpe_ratio: Risk-adjusted return.
        sortino_ratio: Downside risk-adjusted return.
        expected_payoff: Average profit per trade.
        recovery_factor: Profit / max drawdown.
        gross_profit: Total profit from winning trades.
        gross_loss: Total loss from losing trades (positive number).
    """
    profit: float
    profit_factor: float
    max_drawdown_pct: float
    total_trades: int
    win_rate: float
    sharpe_ratio: float
    sortino_ratio: float = 0.0
    expected_payoff: float = 0.0
    recovery_factor: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "profit": self.profit,
            "profit_factor": self.profit_factor,
            "max_drawdown_pct": self.max_drawdown_pct,
            "total_trades": self.total_trades,
            "win_rate": self.win_rate,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "expected_payoff": self.expected_payoff,
            "recovery_factor": self.recovery_factor,
            "gross_profit": self.gross_profit,
            "gross_loss": self.gross_loss,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TradeMetrics":
        """Create TradeMetrics from dictionary."""
        return cls(
            profit=data.get("profit", 0.0),
            profit_factor=data.get("profit_factor", 0.0),
            max_drawdown_pct=data.get("max_drawdown_pct", 0.0),
            total_trades=data.get("total_trades", 0),
            win_rate=data.get("win_rate", 0.0),
            sharpe_ratio=data.get("sharpe_ratio", 0.0),
            sortino_ratio=data.get("sortino_ratio", 0.0),
            expected_payoff=data.get("expected_payoff", 0.0),
            recovery_factor=data.get("recovery_factor", 0.0),
            gross_profit=data.get("gross_profit", 0.0),
            gross_loss=data.get("gross_loss", 0.0),
        )


@dataclass
class GateResult:
    """
    Result of a gate check.

    Gates are pass/fail checks at each workflow step.

    Attributes:
        name: Gate identifier (e.g., "profit_factor", "minimum_trades").
        passed: True if gate passed, False if failed.
        value: Actual measured value.
        threshold: Gate threshold value.
        operator: Comparison operator (>=, <=, ==, >, <).
        message: Human-readable result message.
    """
    name: str
    passed: bool
    value: float
    threshold: float
    operator: str = ">="
    message: Optional[str] = None

    def __post_init__(self) -> None:
        """Generate default message if not provided."""
        if self.message is None:
            status = "PASS" if self.passed else "FAIL"
            self.message = f"{status}: {self.name} = {self.value} ({self.operator} {self.threshold})"

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "passed": self.passed,
            "value": self.value,
            "threshold": self.threshold,
            "operator": self.operator,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GateResult":
        """Create GateResult from dictionary."""
        return cls(
            name=data["name"],
            passed=data["passed"],
            value=data["value"],
            threshold=data["threshold"],
            operator=data.get("operator", ">="),
            message=data.get("message"),
        )


@dataclass
class MonteCarloResult:
    """
    Monte Carlo simulation results.

    Produced by Step 10.

    Attributes:
        iterations: Number of simulation iterations.
        confidence: Percentage of profitable sequences (0-100).
        ruin_probability: Percentage hitting 50% drawdown (0-100).
        expected_profit: Mean profit across all sequences.
        median_profit: 50th percentile profit.
        worst_case: 5th percentile profit.
        best_case: 95th percentile profit.
        max_drawdown_median: Median maximum drawdown percentage.
        max_drawdown_worst: 95th percentile maximum drawdown.
    """
    iterations: int
    confidence: float
    ruin_probability: float
    expected_profit: float
    median_profit: float
    worst_case: float
    best_case: float
    max_drawdown_median: float
    max_drawdown_worst: float

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "iterations": self.iterations,
            "confidence": self.confidence,
            "ruin_probability": self.ruin_probability,
            "expected_profit": self.expected_profit,
            "median_profit": self.median_profit,
            "worst_case": self.worst_case,
            "best_case": self.best_case,
            "max_drawdown_median": self.max_drawdown_median,
            "max_drawdown_worst": self.max_drawdown_worst,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MonteCarloResult":
        """Create MonteCarloResult from dictionary."""
        return cls(
            iterations=data.get("iterations", 0),
            confidence=data.get("confidence", 0.0),
            ruin_probability=data.get("ruin_probability", 0.0),
            expected_profit=data.get("expected_profit", 0.0),
            median_profit=data.get("median_profit", 0.0),
            worst_case=data.get("worst_case", 0.0),
            best_case=data.get("best_case", 0.0),
            max_drawdown_median=data.get("max_drawdown_median", 0.0),
            max_drawdown_worst=data.get("max_drawdown_worst", 0.0),
        )


def calculate_composite_score(
    metrics: TradeMetrics,
    forward_result: float = 0,
    back_result: float = 0,
) -> float:
    """
    Calculate Go Live Score from metrics.

    The Go Live Score answers: "Should I trade this live?"
    Higher score (0-10) = more confidence to deploy with real money.

    Components:
        consistency (25%):   Both back+forward positive = not overfitted
        total_profit (25%):  Actual money made - the goal
        trade_count (20%):   Statistical confidence
        profit_factor (15%): Edge sustainability
        max_drawdown (15%):  Risk tolerance

    Args:
        metrics: TradeMetrics object with performance data.
        forward_result: Forward period profit (from optimization).
        back_result: In-sample period profit (from optimization).

    Returns:
        Score from 0-10.
    """
    # Extract values
    profit = metrics.profit
    trades = metrics.total_trades
    pf = metrics.profit_factor
    dd = metrics.max_drawdown_pct

    # Get ranges
    profit_range = GO_LIVE_SCORE_RANGES.get("total_profit", (0, 5000))
    trades_range = GO_LIVE_SCORE_RANGES.get("trade_count", (50, 200))
    pf_range = GO_LIVE_SCORE_RANGES.get("profit_factor", (1.0, 3.0))
    dd_range = GO_LIVE_SCORE_RANGES.get("max_drawdown", (0, 30))
    consistency_range = GO_LIVE_SCORE_RANGES.get("consistency_min", (0, 2000))

    # Get weights
    weights = GO_LIVE_SCORE_WEIGHTS

    # 1. Consistency: Both periods profitable = robust across time
    #    Score based on the WEAKER period (can't hide a bad back with great forward)
    if forward_result > 0 and back_result > 0:
        # Both positive - score based on minimum (weaker period)
        consistency_value = min(forward_result, back_result)
        consistency_score = normalize_value(
            consistency_value, consistency_range[0], consistency_range[1]
        )
    elif forward_result > 0 or back_result > 0:
        # Only one positive - partial credit (25% of what full consistency would give)
        positive_value = max(forward_result, back_result)
        consistency_score = normalize_value(
            positive_value, consistency_range[0], consistency_range[1]
        ) * 0.25
    else:
        # Both negative or zero - no consistency score
        consistency_score = 0.0

    # 2. Total Profit: Actual money made
    profit_score = normalize_value(profit, profit_range[0], profit_range[1])

    # 3. Trade Count: Statistical confidence (more trades = more reliable)
    trades_score = normalize_value(float(trades), trades_range[0], trades_range[1])

    # 4. Profit Factor: Edge quality (PF < 1.5 is thin edge)
    pf_score = normalize_value(pf, pf_range[0], pf_range[1])

    # 5. Max Drawdown: Risk (inverted - lower DD = higher score)
    dd_score = normalize_value(dd, dd_range[0], dd_range[1], invert=True)

    # Combine with weights
    score = (
        consistency_score * weights.get("consistency", 0.25) +
        profit_score * weights.get("total_profit", 0.25) +
        trades_score * weights.get("trade_count", 0.20) +
        pf_score * weights.get("profit_factor", 0.15) +
        dd_score * weights.get("max_drawdown", 0.15)
    )

    # Scale to 0-10
    return round(score * 10, 1)
