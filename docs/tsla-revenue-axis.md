# TSLA Income Statement Axis Gap

## What Changed
- After collapsing structural presentation nodes (table/axis/domain/member) in `FactMatcher`, the income statement now skips the `Product and Service [Axis]` branch before it reaches the revenue line items.
- Those nodes include `Automotive Revenues`, `Automotive Sales`, `Automotive Regulatory Credits`, and `Automotive Leasing` members that we previously saw as separate revenue rows in the workbook.

## Evidence
- Presentation tree (`output/tsla-viewer.json`):
  ```text
  Income Statement [Abstract]
    Statement [Table]
      Product and Service [Axis]
        Product and Service [Domain]
          Automotive Revenues [Member]
            Automotive Sales [Member]
            Automotive Regulatory Credits [Member]
            Automotive Leasing [Member]
        …
    Statement [Line Items]
      Revenues
  ```
- Facts still include the dimensional context. Example (`us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`):
  ```json
  {
    "a": {
      "c": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
      "srt:ProductOrServiceAxis": "ns0:AutomotiveSalesMember",
      "p": "2024-01-01/2025-01-01",
      "u": "iso4217:USD"
    },
    "v": 72480000000,
    "d": -6
  }
  ```
- Because the structural nodes are filtered out before fact matching, we only retain the top-level `Revenues` row and lose the member breakdown.

## Open Questions
1. Do we want to surface every axis/member combination as separate rows, or only specific axes (e.g., product/service revenue breakdown)?
2. Should we detect dimensional facts during matching and clone the parent line item per distinct member, similar to the iXBRL viewer behaviour?
3. How should indentation and labeling work when multiple axes apply (e.g., product vs geography)?

## Next Steps
1. ✅ `FactMatcher` now groups line-item facts by the axes present in the statement, emits one row per member (indented beneath the parent), and labels them using the MetaLinks member names.
2. ❑ Review whether we need configuration switches to limit expansion (e.g., keep equity component rows, but maybe skip low-signal axes on disclosures).
3. ✅ Unit test coverage (`test_dimension_rows_expanded`) asserts the breakout rows are generated with the correct fact values; rerunning the TSLA workbook now shows automotive sales / regulatory credits / leasing plus equivalent cost-of-revenue splits.
