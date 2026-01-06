"""
EA Stress Test System v2 - Settings & Thresholds
"""
from datetime import datetime, timedelta

# =============================================================================
# BACKTEST SETTINGS
# =============================================================================

# Period: 4 years total (3 in-sample + 1 forward), ending TODAY
BACKTEST_YEARS = 4
IN_SAMPLE_YEARS = 3
FORWARD_YEARS = 1

def get_backtest_dates():
    """Calculate dynamic backtest dates ending today."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=BACKTEST_YEARS * 365)
    split_date = end_date - timedelta(days=FORWARD_YEARS * 365)
    return {
        "start": start_date.strftime("%Y.%m.%d"),
        "end": end_date.strftime("%Y.%m.%d"),
        "split": split_date.strftime("%Y.%m.%d"),  # In-sample ends here
    }

def get_recent_dates(days: int = 30):
    """Calculate a short lookback period ending today (used for tick-history validation)."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    return {
        "start": start_date.strftime("%Y.%m.%d"),
        "end": end_date.strftime("%Y.%m.%d"),
    }

# Data model: 1-minute OHLC
# Model=0: Every tick
# Model=1: 1 minute OHLC
# Model=2: Open prices only
DATA_MODEL = 1

# Execution latency in milliseconds
EXECUTION_LATENCY_MS = 10

# Tick-history validation window (many brokers only provide ~1 month)
TICK_VALIDATION_DAYS = 30

# EA-level safety defaults (injected into EAs that don't already have these)
SAFETY_DEFAULT_MAX_SPREAD_PIPS = 3.0
SAFETY_DEFAULT_MAX_SLIPPAGE_PIPS = 3.0

# During Step 5 (trade validation), we loosen safety limits to avoid false "no trades" failures.
SAFETY_VALIDATION_MAX_SPREAD_PIPS = 500.0
SAFETY_VALIDATION_MAX_SLIPPAGE_PIPS = 500.0

# Account settings
DEPOSIT = 3000
CURRENCY = "GBP"
LEVERAGE = 100

# Forward testing mode
# 0=disabled, 1=by period (1/2 of total), 2=by date
FORWARD_MODE = 2  # Use date-based forward test

# =============================================================================
# PASS/FAIL THRESHOLDS (Gates)
# =============================================================================

# Profit Factor: net profit / gross loss
MIN_PROFIT_FACTOR = 1.5

# Maximum Drawdown percentage
MAX_DRAWDOWN_PCT = 30.0

# Minimum trades for statistical significance
MIN_TRADES = 50

# OnTester minimum trades for optimization (can be lower for comprehensive searches)
# This is used by the injected OnTester function during optimization
ONTESTER_MIN_TRADES = 30  # Lower than MIN_TRADES to let genetic algorithm explore

# Monte Carlo simulation
MC_ITERATIONS = 10000
MC_CONFIDENCE_MIN = 70.0  # Minimum confidence percentage
MC_RUIN_MAX = 5.0         # Maximum ruin probability percentage

# =============================================================================
# RISK-ADJUSTED METRICS (Targets - not gates, for scoring/ranking)
# =============================================================================

# Sharpe Ratio: (return - risk_free) / std_dev
# > 1.0 good, > 2.0 very good, > 3.0 excellent
MIN_SHARPE_RATIO = 1.0
TARGET_SHARPE_RATIO = 2.0

# Sortino Ratio: (return - risk_free) / downside_std_dev
# Better than Sharpe as it only penalizes downside volatility
MIN_SORTINO_RATIO = 1.5
TARGET_SORTINO_RATIO = 2.5

# Calmar Ratio: annualized_return / max_drawdown
# > 1.0 acceptable, > 3.0 excellent
MIN_CALMAR_RATIO = 1.0
TARGET_CALMAR_RATIO = 3.0

# Recovery Factor: net_profit / max_drawdown
MIN_RECOVERY_FACTOR = 2.0

# MAR Ratio: same as Calmar (annualized_return / max_drawdown)
# Included for compatibility with different naming conventions
MIN_MAR_RATIO = 1.0

# Expected Payoff: average profit per trade
MIN_EXPECTED_PAYOFF = 5.0  # Minimum $ per trade

# Win Rate: percentage of winning trades
MIN_WIN_RATE = 40.0        # Minimum acceptable
TARGET_WIN_RATE = 55.0     # Target for good systems

# Risk-free rate for Sharpe/Sortino calculations (annual)
RISK_FREE_RATE = 0.05  # 5%

# =============================================================================
# PARAMETER STABILITY TESTING
# =============================================================================

# Vary each parameter by this percentage to test robustness
PARAM_STABILITY_RANGE = 0.10  # ±10%

# Minimum performance retention after parameter variation
# If performance drops more than this, parameter is flagged as fragile
PARAM_STABILITY_MIN_RETENTION = 0.70  # Must retain 70% of original performance

# =============================================================================
# PORTFOLIO CORRELATION
# =============================================================================

# Maximum acceptable correlation between EAs in portfolio
MAX_EA_CORRELATION = 0.70  # Flag if correlation > 70%

# Correlation calculation period (days)
CORRELATION_LOOKBACK_DAYS = 252  # ~1 trading year

# =============================================================================
# GO LIVE SCORE WEIGHTS
# =============================================================================
#
# The "Go Live Score" answers: "Should I trade this live?"
# Higher score = more confidence to deploy with real money.
#
# Components:
#   consistency   - Back AND forward both profitable = not overfitted
#   total_profit  - Actual money made (the goal)
#   trade_count   - Statistical significance (more trades = more reliable)
#   profit_factor - Edge sustainability (will slippage kill it?)
#   max_drawdown  - Risk tolerance (can you stomach the worst case?)

GO_LIVE_SCORE_WEIGHTS = {
    'consistency': 0.25,      # Both back+forward positive = robust across time
    'total_profit': 0.25,     # Actual money made - the end goal
    'trade_count': 0.20,      # Statistical confidence (50-200 trades)
    'profit_factor': 0.15,    # Edge quality (PF < 1.5 = thin edge)
    'max_drawdown': 0.15,     # Risk (inverted - lower DD = higher score)
}

# Normalization ranges for Go Live Score
GO_LIVE_SCORE_RANGES = {
    'total_profit': (0, 5000),      # £0-5000 -> 0-1
    'trade_count': (50, 200),       # 50-200 trades -> 0-1
    'profit_factor': (1.0, 3.0),    # PF 1.0-3.0 -> 0-1
    'max_drawdown': (0, 30),        # DD 0-30% -> 1-0 (inverted)
    'consistency_min': (0, 2000),   # min(back,fwd) £0-2000 -> 0-1
}

# Legacy alias for backwards compatibility
SCORE_WEIGHTS = GO_LIVE_SCORE_WEIGHTS

# =============================================================================
# BEST PASS SELECTION (Step 9)
# =============================================================================
#
# Determines which backtested pass becomes the "best" pass for:
# - headline metrics
# - Monte Carlo (Step 10)
# - workflow composite score
#
# Options:
#   - "score": leaderboard composite score (recommended)
#   - "profit": net profit
BEST_PASS_SELECTION = "score"

# =============================================================================
# AUTOMATION (Optional)
# =============================================================================
#
# If True, Step 8b (stats analysis) is done automatically by score to enable
# unattended / batch runs (no LLM dependency). Interactive runs can keep this False.
AUTO_STATS_ANALYSIS = True
AUTO_STATS_TOP_N = 20

# Post-steps after report generation
AUTO_RUN_FORWARD_WINDOWS = True   # Step 13 (fast, trade-list based)
AUTO_RUN_MULTI_PAIR = False       # Step 14 (slow, runs full workflow per symbol)
MULTI_PAIR_SYMBOLS = ["EURUSD", "USDJPY"]

# =============================================================================
# POST-STEP STRESS SCENARIOS (Step 12)
# =============================================================================
#
# These run AFTER the main workflow as additional robustness checks.
# They are infrastructure-level and should work for every EA.
#
# Notes:
# - In headless MT5 runs, some tester knobs (notably fixed `Spread=`) may be ignored.
#   Prefer tick-history validation for realistic spread behaviour.
# - `ExecutionMode` (latency) only has a visible effect in tick model for many EAs.
PIP_TO_POINTS = 10

# Optional override list. When None, the stress suite is generated dynamically from
# the window + overlay settings below.
STRESS_SCENARIOS = None

# Window scenarios (relative to the workflow end date)
# Include longer windows for tick-history validation comparisons.
STRESS_WINDOW_ROLLING_DAYS = [7, 14, 30, 60, 90]  # e.g., last 7d/14d/30d/60d/90d
STRESS_WINDOW_CALENDAR_MONTHS_AGO = [1, 2, 3]  # 1=last full month, 2=two months ago, etc.

# Models to run per window
# Model=1: 1-minute OHLC, Model=0: Every tick
STRESS_WINDOW_MODELS = [1, 0]

# Optional tick-only latency variants to append (ms). Empty list disables.
STRESS_TICK_LATENCY_MS = [250, 5000]

# Cost overlays (applied post-hoc from the trade list; does not re-run MT5)
STRESS_INCLUDE_OVERLAYS = True
STRESS_OVERLAY_SPREAD_PIPS = [0.0, 1.0, 2.0, 3.0, 5.0]
STRESS_OVERLAY_SLIPPAGE_PIPS = [0.0, 1.0, 3.0]
STRESS_OVERLAY_SLIPPAGE_SIDES = 2  # entry + exit

# If True, Step 12 runs automatically after Step 11.
# If False, you can invoke stress scenarios manually for a completed workflow.
AUTO_RUN_STRESS_SCENARIOS = True

# =============================================================================
# OPTIMIZATION SETTINGS
# =============================================================================

# Default optimization criteria
# 0=Balance max, 1=Profit Factor max, 2=Expected Payoff max,
# 3=Drawdown min, 4=Recovery Factor max, 5=Sharpe Ratio max
# 6=Custom max (uses OnTester return value)
OPTIMIZATION_CRITERION = 6  # Custom: Profit × R² × sqrt(trades)

# Maximum passes to keep from optimization
MAX_OPTIMIZATION_PASSES = 1000

# Top N passes to show in dashboard
TOP_PASSES_DISPLAY = 20

# Top N passes to backtest for detailed analysis (equity curves, Monte Carlo, etc.)
TOP_PASSES_BACKTEST = 30

# =============================================================================
# FILE PATHS
# =============================================================================

# Runs directory for workflow states and outputs
RUNS_DIR = "runs"
DASHBOARDS_DIR = "runs/dashboards"
LEADERBOARD_DIR = "runs/leaderboard"

# Reference system
REFERENCE_DIR = "reference"
REFERENCE_CACHE_DIR = "reference/cache"

# =============================================================================
# AUTONOMOUS MODE (Future)
# =============================================================================

AUTONOMOUS_MODE = False
DEFAULT_TERMINAL = None  # Set to terminal name for autonomous mode
BATCH_EAS = []           # List of EA filenames to process
NOTIFY_EMAIL = None      # Email for completion notification
