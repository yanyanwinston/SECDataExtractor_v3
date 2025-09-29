# TSLA 2024-12-31 Inline Visibility Regression

## Summary
- Filing: `TSLA` Form 10-K for period ended 2024-12-31 (`downloads/TSLA/10-K_2024-12-31/tsla-20241231.htm`)
- Issue: Presentation-first path keeps note-only rows (e.g., `Energy generation and storage sales/leasing`) that do not appear in the rendered HTML tables.
- Root cause: The inline visibility detector `_extract_visible_fact_signatures` fails to register any primary statement headings for the Workiva-generated filing, so `FactMatcher` never activates a signature allow-list.

## Observations
- Reproduced via `python render_viewer_to_xlsx.py --filing downloads/TSLA/10-K_2024-12-31/tsla-20241231.htm --out temp/tsla-20241231.xlsx --save-viewer-json temp/tsla-20241231.json`.
- Prior to the fix, the saved payload `temp/tsla-20241231.json` lacked a `visible_fact_signatures` block (`rg -n "visible_fact_signatures" temp/tsla-20241231.json` → no matches).
- Inspecting the viewer HTML (`temp/ixbrl-viewer-formatted.html`) shows that statement anchors use hashed IDs such as `ie9fbbc0a99a6483f9fc1594c1ef72807_175`, inserted between the balance sheet and income statement pages.
- The detector in `src/processor/json_extractor.py:391-407` only accepted element IDs containing keywords like `statement` or `balance_sheet`, so it skipped those hashed anchors and never associated the subsequent tables with a heading.
- Without signatures, `_filter_visible_rows` in `src/processor/fact_matcher.py` short-circuits (`active_visible_signatures is None`), leaving extra rows in the workbook.
- After relaxing the heading lookup, the regenerated payload now includes entries for all primary statements (for example `consolidated statements of operations`: 31 signatures), confirming that the allow-list is active again.

## Follow-up Actions
1. Done – Relax the heading fallback to prefer the normalised heading text before filtering on element IDs, so hashed anchors still bind the next table.
2. Done – Populate `visible_fact_signatures` for this filing and confirm the allow-list trims the non-present rows.
3. Pending – Add a regression (TSLA 2024-12-31 sample) that asserts the visibility map is non-empty and that `Energy generation and storage` note rows are filtered from the Consolidated Statements of Operations.
