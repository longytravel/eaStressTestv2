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

# Data model: 1-minute OHLC
# Model=0: Every tick
# Model=1: 1 minute OHLC
# Model=2: Open prices only
DATA_MODEL = 1

# Execution latency in milliseconds
EXECUTION_LATENCY_MS = 10

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
# SCORING WEIGHTS (for composite score calculation)
# =============================================================================

SCORE_WEIGHTS = {
    'profit_factor': 0.15,
    'max_drawdown': 0.15,      # Inverted - lower is better
    'sharpe_ratio': 0.15,
    'sortino_ratio': 0.15,
    'calmar_ratio': 0.10,
    'recovery_factor': 0.10,
    'expected_payoff': 0.10,
    'win_rate': 0.05,
    'param_stability': 0.05,   # Bonus for stable parameters
}

# =============================================================================
# OPTIMIZATION SETTINGS
# =============================================================================

# Default optimization criteria
# 0=Balance max, 1=Profit Factor max, 2=Expected Payoff max,
# 3=Drawdown min, 4=Recovery Factor max, 5=Sharpe Ratio max
OPTIMIZATION_CRITERION = 5  # Sharpe Ratio

# Maximum passes to keep from optimization
MAX_OPTIMIZATION_PASSES = 1000

# Top N passes to show in dashboard
TOP_PASSES_DISPLAY = 20

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
