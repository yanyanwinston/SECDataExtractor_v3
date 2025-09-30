# TSLA multi-year automotive alignment regression

## Context
- Workbook: `output/tsla-multi-year.xlsx`
- Trigger: review of Income Statement tab on 2025-09-30 surfaced misaligned automotive revenue / cost rows for 2025–2021 periods.
- Pipeline: `ensemble_to_xlsx.py` (presentation-first multi-filing aggregation).

## Repro steps
1. Generate the ensemble workbook (already present in `output/tsla-multi-year.xlsx`).
2. Inspect `Income Statement` sheet: rows labelled `Automotive sales`, `Automotive leasing`, `Automotive regulatory credits`, etc. show 2025–2024 values on the anchor rows while 2023–2021 values appear on separate trailing rows.
3. Use openpyxl to dump affected rows:
   ```bash
   python - <<'PY'
   from openpyxl import load_workbook
   wb = load_workbook('output/tsla-multi-year.xlsx', data_only=True)
   ws = wb['Income Statement']
   targets = {
       'Automotive sales',
       'Automotive leasing',
       'Automotive regulatory credits',
       'Automotive Revenues',
       'Total automotive revenues',
       'Automotive Cost of Revenues',
   }
   for r in range(3, ws.max_row + 1):
       label = ws.cell(r, 1).value
       if label in targets:
           row = [ws.cell(r, c).value for c in range(1, 7)]
           if any(row[1:]):
               print(r, row)
   PY
   ```
   Output confirms duplicate rows with single-period coverage for 2023–2021.

## Investigation
- Ensemble alignment logic in `src/processor/ensemble.py:_rows_match` short-circuits when `dimension_signature` differs.
- Anchor filing (2024/2025) embeds `dimension_signature=(('productorserviceaxis', 'automotivesalesmember'), …)` on automotive rows.
- Older filings (2023–2021) expose broader members such as `automotiverevenuesmember` and occasionally add `statementbusinesssegmentsaxis`.
- Because `_rows_match` rejects any signature mismatch, historical rows bypass the anchor skeleton and get appended via `_populate_additional_rows`, producing period islands.
- Confirmed by regenerating viewer JSON for historical filings:
  ```bash
  # 2023
  python -m arelle.CntlrCmdLine --plugins iXBRLViewerPlugin \
    --file temp/analysis_temp/extract_574/tsla-20231231.htm \
    --save-viewer temp/analysis_temp/arelle_output_4604/ixbrl-viewer.htm
  python - <<'PY'
  from src.processor import ViewerDataExtractor, DataParser, ValueFormatter
  extractor = ViewerDataExtractor()
  viewer = extractor.extract_viewer_data('temp/analysis_temp/arelle_output_4604/ixbrl-viewer.htm')
  stmt = next(s for s in DataParser(ValueFormatter()).parse_viewer_data(viewer).statements
              if 'operations' in s.name.lower())
  for row in stmt.rows:
      if row.label and 'Automotive' in row.label:
          print(row.label, row.dimension_signature)
  PY
  ```
  - 2024/2025 rows use member-specific signatures (`automotiveleasingmember`, `automotivesalesmember`).
  - 2023 rows mostly point to `automotiverevenuesmember` for the same labels.
  - 2022/2021 filings mix additional segment axes (`statementbusinesssegmentsaxis`) and extension concepts (`ns0:AutomotiveSalesRevenue`).

## Hypothesis
We need to tolerate controlled cardinality changes on axes like `ProductOrServiceAxis`. When the anchor presents a more granular member but the candidate filing uses a broader one (or vice versa) and other invariants (label depth, parent path) match, we should align them instead of creating extra rows.

## Solution implemented (2025-09-30)

### Architecture
Rather than hardcode member mappings or use heuristics, the solution leverages **XBRL's native dimensional hierarchy** from presentation relationships. This provides a fundamental, generalizable approach that works for any company's taxonomy evolution.

### Key components

**1. DimensionHierarchy data model** (`src/processor/data_models.py:52-110`)
- Stores parent-child relationships between dimension members
- Provides `is_ancestor(ancestor, descendant)` for semantic queries
- Provides `get_all_descendants(member)` for hierarchy traversal
- Normalizes member names (strips namespace prefix, lowercases)

**2. Hierarchy extraction** (`src/processor/json_extractor.py:798-851`)
- Parses presentation relationships from Arelle viewer JSON (`rels.pres`)
- Identifies dimension members (concepts containing "Member" or "Domain")
- Builds parent-child graph from presentation hierarchy
- Successfully extracts 114 members with 45 parent nodes from TSLA 2023 10-K

Example hierarchy discovered:
```
srt:ProductsAndServicesDomain
├── tsla:AutomotiveRevenuesMember (parent)
│   ├── tsla:AutomotiveSalesMember
│   ├── tsla:AutomotiveLeasingMember
│   └── tsla:AutomotiveRegulatoryCreditsMember
├── tsla:EnergyGenerationAndStorageMember
└── tsla:ServicesAndOtherMember
```

**3. Semantic dimension matching** (`src/processor/ensemble.py:159-222`)
- New `_signatures_semantically_compatible(anchor_sig, candidate_sig, hierarchy)` function
- Returns `True` when:
  - Signatures are identical (strict match)
  - Signatures are on the same axes AND one member is ancestor of the other
  - All axes must align (no cross-axis matching)
- Logs semantic matches via `logger.debug()` for transparency

**4. Integration into ensemble pipeline** (`src/processor/ensemble.py:225-310, 359-392`)
- Updated `_rows_match(anchor, candidate, hierarchy)` to accept optional hierarchy
- Checks semantic compatibility when strict signature match fails
- Only relaxes matching when concept/label/depth/parent-path also align
- `_merge_dimension_hierarchies(slices)` combines hierarchies from all filings
- Hierarchies propagated through: `build_ensemble_result` → `_aggregate_statement` → `_map_rows` → `_rows_match`

**5. Regression test** (`tests/test_ensemble.py:295-431`)
- `test_dimension_semantic_matching_with_hierarchy()` validates the TSLA scenario
- Sets up anchor filing with granular members (sales/leasing/credits)
- Sets up prior filing with parent member (automotiverevenuesmember)
- Asserts all three rows align across periods (single row per label)
- ✅ All 6 ensemble tests pass

### Validation commands
```bash
# Run regression test
PYTHONPATH=. pytest tests/test_ensemble.py::test_dimension_semantic_matching_with_hierarchy -v

# Regenerate TSLA workbook
python ensemble_to_xlsx.py --ticker TSLA --form 10-K --count 5 --out output/tsla-multi-year-fixed.xlsx

# Check hierarchy extraction
python - <<'PY'
import sys
sys.path.insert(0, 'src')
from processor.json_extractor import ViewerDataExtractor
from processor.data_parser import DataParser

extractor = ViewerDataExtractor()
data = extractor.extract_viewer_data('temp/analysis_temp/arelle_output_4604/ixbrl-viewer.htm')
hierarchy = data.get('dimension_hierarchy')
if hierarchy:
    print(f"Members: {len(hierarchy.parents)}, Parents: {len(hierarchy.children)}")
    if 'automotiverevenuesmember' in hierarchy.children:
        print(f"Children: {hierarchy.children['automotiverevenuesmember']}")
PY
```

### Why this approach is fundamental
1. **Leverages XBRL's native semantic model** - uses standardized presentation relationships, not heuristics
2. **Generalizes to any taxonomy evolution** - works for any company that refines/coarsens dimensional granularity
3. **Maintains precision** - only relaxes matching when hierarchical relationship exists
4. **Future-proof** - handles axis drift in any domain (geography, segments, products, etc.)
5. **Transparent** - logs semantic matches for audit trail

### Current status

**✅ Implementation complete**
- Hierarchy extraction: working (114 members extracted from TSLA filings)
- Semantic matching logic: working (unit tests pass)
- Integration: complete (wired through ensemble pipeline)
- Regression test: passing (validates parent-child alignment)

**⚠️ Full validation incomplete**
Regenerating the 5-year TSLA ensemble workbook still shows misalignment:
```
Label Frequency Analysis:
  ⚠ 'Automotive Revenues' appears 3 times (MISALIGNED)
  ⚠ 'Automotive leasing' appears 6 times (MISALIGNED)
  ⚠ 'Automotive regulatory credits' appears 2 times (MISALIGNED)
  ⚠ 'Automotive sales' appears 4 times (MISALIGNED)
```

This suggests the semantic matching isn't triggering for the real TSLA data despite working in unit tests. Possible blocking factors:
1. **Concept differences** - anchor vs. candidate rows may use different concepts (e.g., `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` vs. `tsla:AutomotiveRevenue`)
2. **Label variations** - exact label text may differ beyond normalization ("Automotive sales" vs. "Automotive Sales")
3. **Parent path mismatches** - presentation hierarchy ancestors may differ across filings
4. **Multiple presentation contexts** - TSLA may present automotive data in multiple disclosure contexts (segment reporting, revenue disaggregation, geographic) within a single filing, causing legitimate duplication

### Next steps for investigation
1. **Add debug logging** to `_rows_match` to capture why specific TSLA rows fail to align:
   ```python
   if not _rows_match(anchor_row, candidate, hierarchy):
       logger.debug(f"Row mismatch: anchor={anchor_row.label}/{anchor_row.concept}/{anchor_row.dimension_signature}, "
                    f"candidate={candidate.label}/{candidate.concept}/{candidate.dimension_signature}")
   ```

2. **Inspect actual ProcessingResult objects** from 2024 and 2023 TSLA filings to compare:
   - Exact concept QNames
   - Exact label text
   - Dimension signatures (normalized)
   - Parent paths
   - Presentation node metadata

3. **Test 2-year ensemble only** (2024 + 2023) to isolate the specific mismatch:
   ```bash
   python ensemble_to_xlsx.py --ticker TSLA --form 10-K --count 2 --out output/tsla-2yr-debug.xlsx
   ```

4. **Consider concept normalization** - if concepts differ but labels match, may need to relax concept matching when dimensions are semantically compatible

5. **Review TSLA's actual XBRL structure** - the multiple occurrences of automotive rows (6x "Automotive leasing") suggest TSLA may intentionally present these in multiple contexts that should NOT be collapsed

### References
- XBRL Dimensions 1.0 spec: http://www.xbrl.org/Specification/xdt-pwd-2005-07-19.htm
- XBRL US GAAP Taxonomy Preparers Guide: https://xbrl.us/wp-content/uploads/2015/03/PreparersGuide.pdf
- Arelle viewer JSON format: presentation relationships stored in `rels.pres` with parent-child structure
