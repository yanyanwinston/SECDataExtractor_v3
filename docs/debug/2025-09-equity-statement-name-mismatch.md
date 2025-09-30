# TSLA Multi-Year Equity Statement Empty Columns (2020-2022)

## Observed Issue
- Workbook: `output/tsla-multi-year.xlsx`
- Sheet: `Equity`
- Problem: Columns for 2022, 2021, and 2020 are mostly empty (showing "—" dashes), while 2024 and 2023 columns have data
- Only ~6 rows out of 59 have any data in the 2020-2022 columns

## Investigation Summary

### Individual Filing Workbooks
All individual filing workbooks contain complete Equity statements with data:
- `output/TSLA/10-K_2024-12-31_000162828025003063.xlsx`: Equity sheet has 40 rows with data
- `output/TSLA/10-K_2022-12-31_000095017023001409.xlsx`: Equity sheet has 60 rows with data (28 with values)
- `output/TSLA/10-K_2021-12-31_000095017022000796.xlsx`: Equity sheet has 83 rows with data (19 with values)
- `output/TSLA/10-K_2020-12-31_000156459021004599.xlsx`: Equity sheet has 79 rows with data (16 with values)

The data exists in source filings but is not being merged into the multi-year workbook.

### Ensemble Statement Matching

Checked the actual statement names extracted from filings:

**2020 Filing** (10-K_2020-12-31):
- Statement #30: **"Consolidated Statements of Redeemable Noncontrolling Interest and Stockholders' Equity"** (77 rows)
- Statement #31: "Consolidated Statements of Redeemable Noncontrolling Interest and Stockholders' Equity (Parenthetical)" (23 rows)

**2021 Filing** (10-K_2021-12-31):
- Similar structure with "Stockholders' Equity" in name

**2022 Filing** (10-K_2022-12-31):
- Statement #29: **"Consolidated Statements of Redeemable Noncontrolling Interest and Stockholders' Equity (Unaudited)"** (58 rows)
- Statement #30: "Consolidated Statements of Redeemable Noncontrolling Interest and Stockholders' Equity (Unaudited) (Parenthetical)" (4 rows)

**2024 Filing** (10-K_2024-12-31) - Used as Anchor:
- Statement #5: **"Consolidated Statements of Redeemable Noncontrolling Interest and Equity"** (40 rows)

## Root Cause

The ensemble merge logic in `src/processor/ensemble.py` uses `_canonical_statement_key()` (lines 44-56) to match statements across filings. This function:

1. Lowercases the statement name
2. Strips " - " prefixes (for disclosure statements)
3. Returns the normalized name as the matching key

**Current keys generated:**
- 2024 anchor: `"consolidated statements of redeemable noncontrolling interest and equity"`
- 2022: `"consolidated statements of redeemable noncontrolling interest and stockholders' equity (unaudited)"`
- 2021: `"consolidated statements of redeemable noncontrolling interest and stockholders' equity"`
- 2020: `"consolidated statements of redeemable noncontrolling interest and stockholders' equity"`

**Keys don't match!** The ensemble logic treats these as completely different statements:
- "equity" vs "stockholders' equity" - different text
- "(unaudited)" suffix - not stripped

When `build_ensemble_result()` (line 250) processes each filing:
1. Anchor filing (2024) establishes statement keys
2. For each older filing, it calls `_find_statement()` (line 430) to locate matching statements
3. No match found → warning logged, blank column created
4. Result: Empty columns for 2020-2022

### Evidence from Code Path

**In `_aggregate_statement()` (lines 306-382):**
```python
for slice_item in slices:
    statement = _find_statement(slice_item.result.statements, statement_key)

    if statement and statement.periods:
        primary_period = statement.periods[0]
    else:
        # NO MATCH - creates warning and blank period
        warnings.append(
            f"Statement '{anchor_statement.name}' missing in {slice_item.source}; column populated with blanks"
        )
        primary_period = Period(
            label=slice_item.result.filing_date or default_label or slice_item.source,
            end_date=default_end or _fallback_end_date(slice_item.filing_date),
            instant=default_instant,
        )
```

When no match is found:
- `matched_rows = [None] * len(anchor_statement.rows)` (line 357)
- `additional_rows = []` (line 358)
- All cells remain empty for that period

### Common Rows Analysis

Despite statement name mismatch, there are 10 common row labels between 2024 and 2022:
- "additional paid-in capital"
- "common stock"
- "issuance of common stock for equity incentive awards"
- "noncontrolling interest, decrease from distributions to noncontrolling interest holders"
- "noncontrolling interests in subsidiaries"
- "other comprehensive income (loss)"
- "redeemable noncontrolling interests"
- "shares, issued"
- "statement of stockholders' equity [abstract]"
- "stock-based compensation"

However, these never match because the statement-level lookup fails first. Row matching (`_rows_match()` in line 159) is never invoked for 2020-2022 equity statements.

## Implications

- Multi-year equity analysis is incomplete
- Historical equity changes (2020-2022) are invisible in the ensemble workbook
- Users must manually open individual filing workbooks to access older equity data
- The issue affects any company where equity statement naming changed between years

## Remediation

Enhance `_canonical_statement_key()` normalization to handle:

1. **Parenthetical suffixes**: Strip "(Unaudited)", "(Parenthetical)", "(Detail)", etc.
2. **Equity terminology**: Normalize "stockholders' equity" → "equity", "stockholder's equity" → "equity"
3. **Possessive apostrophes**: Remove before comparison
4. **Whitespace**: Collapse multiple spaces to single space

**Proposed implementation:**

```python
def _canonical_statement_key(statement: Statement) -> str:
    """Build a lookup key for a statement consistent across filings."""

    name_token = (statement.name or "").strip().lower()
    if " - " in name_token:
        _, _, tail = name_token.partition(" - ")
        if tail:
            name_token = tail

    if not name_token:
        name_token = (statement.short_name or "").strip().lower()

    # Strip common parenthetical suffixes
    import re
    name_token = re.sub(r'\s*\((unaudited|parenthetical|detail|details)\)\s*$', '', name_token)

    # Normalize equity terminology
    name_token = name_token.replace("stockholders' equity", "equity")
    name_token = name_token.replace("stockholder's equity", "equity")

    # Collapse multiple spaces
    name_token = re.sub(r'\s+', ' ', name_token).strip()

    return name_token
```

**Expected keys after fix:**
- All years: `"consolidated statements of redeemable noncontrolling interest and equity"`

This enables proper statement matching, row alignment, and cell population across all years.

## Validation Commands

```bash
# Regenerate multi-year workbook after fix
python ensemble_to_xlsx.py --ticker TSLA --form 10-K --count 5 --no-download \
    --out output/tsla-multi-year-fixed.xlsx

# Verify Equity sheet has populated 2020-2022 columns
python -c "
import openpyxl
wb = openpyxl.load_workbook('output/tsla-multi-year-fixed.xlsx', data_only=True)
ws = wb['Equity']
print('Columns:', [ws.cell(2, col).value for col in range(1, ws.max_column + 1)])

# Count non-empty cells per column
for col in range(2, ws.max_column + 1):
    non_empty = sum(1 for row in range(3, ws.max_row + 1)
                    if ws.cell(row, col).value not in (None, '—', ''))
    print(f'{ws.cell(2, col).value}: {non_empty} cells with data')
"
```

## Related Issues

This same pattern may affect other statement types if naming changes between years:
- Balance Sheet variations: "Balance Sheets" vs "Balance Sheet" vs "Statement of Financial Position"
- Income Statement variations: "Operations" vs "Income" vs "Earnings"
- Cash Flow variations: "Cash Flows" vs "Cash Flow Statement"

Consider adding similar normalization for all statement types, not just Equity.

## Follow-up Actions

1. Implement enhanced `_canonical_statement_key()` normalization
2. Add unit tests in `tests/test_ensemble.py` for statement key matching edge cases
3. Add integration test using TSLA 2020-2024 filings to validate cross-year equity merging
4. Document statement name normalization rules in `docs/developer-guide.md`
5. Consider logging statement key mismatches at INFO level to help diagnose similar issues