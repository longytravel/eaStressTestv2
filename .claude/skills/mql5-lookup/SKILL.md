# MQL5 Lookup Skill

Fast lookup into the 7000-page MQL5 reference documentation.

## Trigger

User says: `/mql5-lookup <query>` or other skills need MQL5 syntax verification

## Purpose

Search the indexed MQL5 reference to find:
- Function signatures and parameters
- Class methods and properties
- Code examples
- Correct syntax for any MQL5 operation

---

## Reference Location

```
reference/
├── mql5_index.json       # Search index
├── indexer.py            # Index builder
├── lookup.py             # Search functions
└── cache/                # Pre-extracted topics (48 files)
    ├── ctrade.txt
    ├── trade_functions.txt
    ├── irsi.txt
    ├── ordersend.txt
    └── ...
```

**Source**: Copy from `C:\Users\User\Projects\simpleEA\reference\`

---

## Query Types

### 1. Function Lookup
```
/mql5-lookup OrderSend
/mql5-lookup iRSI
/mql5-lookup ArrayCopy
```

Returns:
- Full function signature
- Parameter descriptions
- Return value
- Example code

### 2. Class Method Lookup
```
/mql5-lookup CTrade Buy
/mql5-lookup CPositionInfo Profit
```

Returns:
- Method signature
- Required includes
- Example usage

### 3. Concept Lookup
```
/mql5-lookup trailing stop
/mql5-lookup position sizing
/mql5-lookup error handling
```

Returns:
- Relevant functions
- Best practices
- Code patterns

### 4. Error Code Lookup
```
/mql5-lookup error 4756
/mql5-lookup TRADE_RETCODE_DONE
```

Returns:
- Error meaning
- Common causes
- How to handle

---

## Search Process

### Step 1: Parse Query
```python
def parse_query(query):
    query = query.lower().strip()

    # Check for class.method pattern
    if " " in query and query.split()[0].startswith("c"):
        return ("class_method", query.split()[0], query.split()[1])

    # Check for error code
    if query.startswith("error") or query.startswith("retcode"):
        return ("error", extract_code(query))

    # Check for function name (starts with letter, contains only word chars)
    if query.isidentifier():
        return ("function", query)

    # Concept search
    return ("concept", query)
```

### Step 2: Search Index
```python
def search_index(query_type, query):
    index = load_index("reference/mql5_index.json")

    if query_type == "function":
        # Exact match first
        if query in index['functions']:
            return index['functions'][query]

        # Fuzzy match
        matches = []
        for func in index['functions']:
            if query in func.lower():
                matches.append(func)
        return matches

    # ... similar for other types
```

### Step 3: Load Cache File
```python
def get_cached_content(topic):
    cache_file = Path(f"reference/cache/{topic.lower()}.txt")

    if cache_file.exists():
        return cache_file.read_text()

    # Fall back to PDF extraction
    return extract_from_pdf(topic)
```

### Step 4: Format Response
```python
def format_response(content, query):
    return f"""
## MQL5 Reference: {query}

{content['signature']}

### Parameters
{format_params(content['params'])}

### Returns
{content['returns']}

### Example
```mql5
{content['example']}
```

### Notes
{content['notes']}
"""
```

---

## Common Lookups (Pre-Cached)

| Topic | File | Contents |
|-------|------|----------|
| CTrade class | ctrade.txt | All CTrade methods |
| Trade functions | trade_functions.txt | OrderSend, OrderCheck |
| Position functions | position_functions.txt | PositionSelect, PositionGet* |
| Order functions | order_functions.txt | OrderGet*, OrdersTotal |
| Indicator functions | indicators.txt | iMA, iRSI, iATR, etc. |
| Array functions | arrays.txt | ArrayCopy, ArrayResize |
| Math functions | math.txt | MathMax, NormalizeDouble |
| Time functions | time.txt | TimeCurrent, TimeToString |
| Account functions | account.txt | AccountInfo*, AccountBalance |
| Symbol functions | symbol.txt | SymbolInfo*, SymbolSelect |
| Error codes | errors.txt | All error codes and meanings |

---

## Output Format

### Function Response
```markdown
## iRSI

```mql5
int iRSI(
   string           symbol,          // symbol name
   ENUM_TIMEFRAMES  period,          // period
   int              ma_period,       // averaging period
   ENUM_APPLIED_PRICE applied_price  // type of price
);
```

### Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| symbol | string | Symbol name. NULL = current |
| period | ENUM_TIMEFRAMES | Timeframe. PERIOD_CURRENT = current |
| ma_period | int | Averaging period for RSI calculation |
| applied_price | ENUM_APPLIED_PRICE | Price to use (PRICE_CLOSE, etc.) |

### Returns
Indicator handle (int) or INVALID_HANDLE on failure.

### Example
```mql5
int rsi_handle = iRSI(_Symbol, PERIOD_H1, 14, PRICE_CLOSE);
if(rsi_handle == INVALID_HANDLE)
{
    Print("Failed to create RSI: ", GetLastError());
    return INIT_FAILED;
}

// Get RSI value
double rsi[];
ArraySetAsSeries(rsi, true);
if(CopyBuffer(rsi_handle, 0, 0, 1, rsi) > 0)
{
    Print("RSI = ", rsi[0]);
}
```

### Notes
- Always check for INVALID_HANDLE
- Use CopyBuffer to get values
- Release handle in OnDeinit with IndicatorRelease()
```

### Error Response
```markdown
## Error 4756 (ERR_TRADE_SEND_FAILED)

**Meaning**: Trade request sending failed.

**Common Causes**:
1. Market is closed
2. Invalid price/stops
3. No connection to server
4. Insufficient margin

**How to Handle**:
```mql5
MqlTradeResult result;
if(!OrderSend(request, result))
{
    int error = GetLastError();
    if(error == 4756)
    {
        Print("Trade send failed. Retcode: ", result.retcode);
        Print("Comment: ", result.comment);
        // Wait and retry or handle specific retcode
    }
}
```
```

---

## Integration

- **ea-improver**: Uses for correct syntax in suggestions
- **mql5-fixer**: Uses for fixing compilation errors
- **mql5-coder** (user skill): References for EA development

## Quick Reference

### Most Common Functions

| Function | Purpose |
|----------|---------|
| `OrderSend()` | Send trade request |
| `PositionSelect()` | Select position by symbol |
| `PositionGetDouble()` | Get position property |
| `iMA()` | Moving average handle |
| `iRSI()` | RSI handle |
| `iATR()` | ATR handle |
| `CopyBuffer()` | Get indicator values |
| `NormalizeDouble()` | Round to digits |
| `SymbolInfoDouble()` | Get symbol property |
| `AccountInfoDouble()` | Get account property |

### Key Includes
```mql5
#include <Trade\Trade.mqh>           // CTrade class
#include <Trade\PositionInfo.mqh>    // CPositionInfo
#include <Trade\SymbolInfo.mqh>      // CSymbolInfo
#include <Trade\AccountInfo.mqh>     // CAccountInfo
```
