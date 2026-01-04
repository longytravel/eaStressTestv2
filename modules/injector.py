"""
EA Code Injector Module

Injects OnTester() function and safety guards into MQL5 EAs.
Creates modified copies without altering originals.
"""
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional


# OnTester function that returns custom optimization criterion
# Returns Sharpe Ratio-like metric: (profit / trades) / stddev
ONTESTER_CODE = '''
//+------------------------------------------------------------------+
//| OnTester - Injected by EA Stress Test System                     |
//+------------------------------------------------------------------+
double OnTester()
{
    // Get basic statistics
    double profit = TesterStatistics(STAT_PROFIT);
    double trades = TesterStatistics(STAT_TRADES);
    double profitFactor = TesterStatistics(STAT_PROFIT_FACTOR);
    double drawdownPct = TesterStatistics(STAT_EQUITY_DDREL_PERCENT);
    double sharpe = TesterStatistics(STAT_SHARPE_RATIO);

    // Minimum trades filter
    if(trades < 50) return -1000;

    // Return Sharpe ratio as primary criterion
    // Falls back to adjusted profit factor if Sharpe unavailable
    if(sharpe != 0) return sharpe;

    // Fallback: PF adjusted by drawdown
    if(profitFactor > 0 && drawdownPct > 0)
        return profitFactor * (100.0 - drawdownPct) / 100.0;

    return profit / trades;
}
'''

# Safety guards to prevent dangerous operations during testing
SAFETY_GUARDS = '''
//+------------------------------------------------------------------+
//| Safety Guards - Injected by EA Stress Test System                |
//+------------------------------------------------------------------+
#define STRESS_TEST_MODE true

// Override dangerous functions during testing
#ifdef STRESS_TEST_MODE
    // Prevent file operations
    #define FileOpen(a,b,c) INVALID_HANDLE
    #define FileWrite(a,b) 0
    #define FileDelete(a) false

    // Prevent web requests
    #define WebRequest(a,b,c,d,e,f,g) false

    // Prevent DLL calls (already restricted in tester, but extra safety)
    #define DLLCall(a,b) 0
#endif
'''

# Trade safety guards to enforce spread + slippage limits (EA-agnostic)
TRADE_SAFETY_GUARDS = '''
//+------------------------------------------------------------------+
//| Trade Safety - Injected by EA Stress Test System                 |
//+------------------------------------------------------------------+
#ifdef STRESS_TEST_MODE

// Trading safety inputs (NOT optimized)
input double EAStressSafety_MaxSpreadPips = 3.0;     // Max allowed spread (pips)
input double EAStressSafety_MaxSlippagePips = 3.0;   // Max allowed slippage (pips)

double EAStressSafety_PipSize()
{
    // 5-digit/3-digit brokers: 1 pip = 10 points
    if(_Digits == 3 || _Digits == 5) return _Point * 10.0;
    return _Point;
}

bool EAStressSafety_IsSpreadOk()
{
    if(EAStressSafety_MaxSpreadPips <= 0) return true; // Disabled

    long spreadPoints = 0;
    if(!SymbolInfoInteger(_Symbol, SYMBOL_SPREAD, spreadPoints)) return true;

    double maxSpreadPoints = (EAStressSafety_MaxSpreadPips * EAStressSafety_PipSize()) / _Point;
    if(maxSpreadPoints <= 0) return true;

    return (double)spreadPoints <= maxSpreadPoints;
}

int EAStressSafety_MaxDeviationPoints()
{
    if(EAStressSafety_MaxSlippagePips <= 0) return 0; // Disabled
    double points = (EAStressSafety_MaxSlippagePips * EAStressSafety_PipSize()) / _Point;
    if(points < 0) return 0;
    return (int)MathRound(points);
}

bool EAStressSafety_OrderSend(const MqlTradeRequest& request, MqlTradeResult& result)
{
    if(!EAStressSafety_IsSpreadOk())
    {
        result.retcode = 0;
        result.comment = "EAStressSafety: Spread too high";
        return false;
    }

    MqlTradeRequest req = request;

    int maxDev = EAStressSafety_MaxDeviationPoints();
    if(maxDev > 0)
    {
        // Cap deviation if EA set a looser value
        if((int)req.deviation <= 0 || (int)req.deviation > maxDev)
            req.deviation = maxDev;
    }

    return OrderSend(req, result);
}

bool EAStressSafety_OrderSendAsync(const MqlTradeRequest& request, MqlTradeResult& result)
{
    if(!EAStressSafety_IsSpreadOk())
    {
        result.retcode = 0;
        result.comment = "EAStressSafety: Spread too high";
        return false;
    }

    MqlTradeRequest req = request;

    int maxDev = EAStressSafety_MaxDeviationPoints();
    if(maxDev > 0)
    {
        if((int)req.deviation <= 0 || (int)req.deviation > maxDev)
            req.deviation = maxDev;
    }

    return OrderSendAsync(req, result);
}

// Intercept all order sending (including inside standard library, e.g., CTrade)
#define OrderSend EAStressSafety_OrderSend
#define OrderSendAsync EAStressSafety_OrderSendAsync

#endif
'''


def has_ontester(content: str) -> bool:
    """Check if EA already has an OnTester function."""
    # Match OnTester function declaration
    pattern = r'^\s*(double|int|void)\s+OnTester\s*\(\s*\)'
    return bool(re.search(pattern, content, re.MULTILINE))


def has_safety_guards(content: str) -> bool:
    """Check if EA already has safety guards injected."""
    return 'STRESS_TEST_MODE' in content


def has_trade_safety_guards(content: str) -> bool:
    """Check if EA already has trade safety guards injected."""
    return 'EAStressSafety_MaxSpreadPips' in content


def inject_ontester(content: str) -> tuple[str, bool]:
    """
    Inject OnTester function into EA source code.

    Args:
        content: EA source code

    Returns:
        Tuple of (modified_content, was_injected)
    """
    if has_ontester(content):
        return content, False

    # Find a good injection point - after the last #include or #property
    # or before the first function definition

    # Try to find last preprocessor directive
    last_directive = 0
    for match in re.finditer(r'^#\w+.*$', content, re.MULTILINE):
        last_directive = match.end()

    if last_directive > 0:
        # Inject after last directive
        injection_point = last_directive
        prefix = '\n\n'
    else:
        # Inject at beginning after any initial comments
        comment_end = 0
        # Skip initial block comment
        if content.strip().startswith('//+'):
            match = re.search(r'//\+-+\+\s*\n', content[50:])
            if match:
                comment_end = 50 + match.end()
        injection_point = comment_end
        prefix = '\n'

    modified = content[:injection_point] + prefix + ONTESTER_CODE + '\n' + content[injection_point:]
    return modified, True


def inject_safety(content: str) -> tuple[str, bool]:
    """
    Inject safety guards into EA source code.

    Args:
        content: EA source code

    Returns:
        Tuple of (modified_content, was_injected)
    """
    injected = False

    # Inject safety guards at the very beginning, after initial comment block
    comment_end = 0

    # Skip initial header comment block
    if content.strip().startswith('//+'):
        # Find end of header block (//+--...--+)
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if i > 0 and line.strip().startswith('//+') and line.strip().endswith('+'):
                comment_end = sum(len(l) + 1 for l in lines[:i+1])
                break

    # If safety guard block is missing, insert it
    if not has_safety_guards(content):
        content = content[:comment_end] + '\n' + SAFETY_GUARDS + '\n' + content[comment_end:]
        injected = True

    # If trade safety is missing, insert it (upgrade older injected files)
    if not has_trade_safety_guards(content):
        # Prefer inserting immediately after the safety guard block if present
        marker = '//| Safety Guards - Injected by EA Stress Test System'
        idx = content.find(marker)
        if idx != -1:
            end_idx = content.find('#endif', idx)
            if end_idx != -1:
                end_idx = content.find('\n', end_idx)
                if end_idx != -1:
                    content = content[:end_idx+1] + TRADE_SAFETY_GUARDS + '\n' + content[end_idx+1:]
                    injected = True
                else:
                    content = content + '\n' + TRADE_SAFETY_GUARDS + '\n'
                    injected = True
            else:
                content = content + '\n' + TRADE_SAFETY_GUARDS + '\n'
                injected = True
        else:
            content = content[:comment_end] + '\n' + TRADE_SAFETY_GUARDS + '\n' + content[comment_end:]
            injected = True

    return content, injected


def create_modified_ea(
    ea_path: str,
    output_dir: Optional[str] = None,
    inject_tester: bool = True,
    inject_guards: bool = True,
    suffix: str = '_stress_test',
) -> dict:
    """
    Create a modified copy of an EA with injected code.

    Args:
        ea_path: Path to original .mq5 file
        output_dir: Directory for modified file (default: same as original)
        inject_tester: Whether to inject OnTester function
        inject_guards: Whether to inject safety guards
        suffix: Suffix for modified filename

    Returns:
        dict with keys:
            - success: bool
            - original_path: str
            - modified_path: str
            - ontester_injected: bool
            - safety_injected: bool
            - errors: list of error strings
    """
    ea_path = Path(ea_path)

    if not ea_path.exists():
        return {
            'success': False,
            'original_path': str(ea_path),
            'modified_path': None,
            'ontester_injected': False,
            'safety_injected': False,
            'errors': [f"EA file not found: {ea_path}"],
        }

    try:
        content = ea_path.read_text(encoding='utf-8', errors='ignore')
    except Exception as e:
        return {
            'success': False,
            'original_path': str(ea_path),
            'modified_path': None,
            'ontester_injected': False,
            'safety_injected': False,
            'errors': [f"Failed to read EA: {str(e)}"],
        }

    ontester_injected = False
    safety_injected = False

    # Inject OnTester
    if inject_tester:
        content, ontester_injected = inject_ontester(content)

    # Inject safety guards
    if inject_guards:
        content, safety_injected = inject_safety(content)

    # Determine output path
    if output_dir:
        output_path = Path(output_dir) / f"{ea_path.stem}{suffix}.mq5"
    else:
        output_path = ea_path.parent / f"{ea_path.stem}{suffix}.mq5"

    # Write modified file
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding='utf-8')
    except Exception as e:
        return {
            'success': False,
            'original_path': str(ea_path),
            'modified_path': None,
            'ontester_injected': ontester_injected,
            'safety_injected': safety_injected,
            'errors': [f"Failed to write modified EA: {str(e)}"],
        }

    return {
        'success': True,
        'original_path': str(ea_path),
        'modified_path': str(output_path),
        'ontester_injected': ontester_injected,
        'safety_injected': safety_injected,
        'errors': [],
    }


def restore_original(modified_path: str) -> bool:
    """
    Remove a modified EA file.

    Args:
        modified_path: Path to the modified .mq5 file

    Returns:
        True if file was deleted, False otherwise
    """
    path = Path(modified_path)
    if path.exists() and '_stress_test' in path.stem:
        path.unlink()
        # Also remove .ex5 if it exists
        ex5_path = path.with_suffix('.ex5')
        if ex5_path.exists():
            ex5_path.unlink()
        return True
    return False
