# Tesla Excel Gap Notes

## Context
- Reference workbook: `downloads/TSLA/10-K_2025-01-29/Financial_Report.xlsx`
- Current export: `output/TSLA-10K-2024.xlsx`
- Goal: align the presentation-first pipeline output with Tesla's curated workbook while keeping the new parser/matcher architecture.

## Problem 1 — Sheet Explosion
- Our generator creates one sheet per presentation role, yielding 90+ tabs (`Income Statement1`, `Disclosure - …`, etc.).
- Financial_Report.xlsx consolidates roles into a concise, reviewer-friendly set (cover, audit, core statements, curated disclosures, and tables).
- Root cause: `DataParser._convert_statement_tables_to_legacy_format` forwards every `PresentationStatement`; `ExcelGenerator` writes them verbatim.

### Revised Approach
- **Leverage MetaLinks**: `downloads/TSLA/10-K_2025-01-29/MetaLinks.json` enumerates each role (`R1`, `R2`, …) with `groupType` (`statement`, `document`, `disclosure`) and `subGroupType` (`parenthetical`, `tables`, `details`).
- **Map Role IDs**: Use the shared role URI to connect viewer role IDs (`ns3`, `ns4`, …) to `MetaLinks` entries and attach `{r_id, groupType, subGroupType, longName}` to each `PresentationStatement`.
- **Default Filter**: Emit only `groupType == "statement"` (Tesla’s R3–R8) plus optional `document` roles (Cover/Audit). Skip `subGroupType == "parenthetical"` until we intentionally add them back.
- **Opt-in Disclosures**: Add a CLI flag such as `--include-disclosures` to include `disclosure`/`details` sheets when needed by analysts.
- **Diagnostics**: Provide a `--dump-role-map` flag to export the categorized role list (R#, groupType, row counts) so we can tune allowlists per issuer.

### Updated Plan
1. Parse `MetaLinks.json` during ingestion and build `role_metadata = {role_uri: {r_id, groupType, subGroupType, longName}}`.
2. Enrich `PresentationStatement` with the matched metadata when parsing presentation roles.
3. Filter statements in `DataParser` using the metadata before handing them to `ExcelGenerator` (keep `statement`, optionally `document`, gate the rest behind CLI flags).
4. Implement the diagnostic flag for QA visibility.
5. Add a regression test asserting the TSLA workbook contains only the six primary sheets by default.

_Status_: Steps 1–4 implemented (`ViewerDataExtractor` loads MetaLinks, `DataParser` filters by `groupType`, CLI exposes `--include-disclosures` and `--dump-role-map`). Regression test for default sheet count pending once we record a curated expectation file.

## Problem 2 — Period Overload
- Primary statements list every context label we encounter (`Jan 23, 2025`, `Jan 09, 2025`, …), while Tesla keeps the expected annual columns (`Dec. 31, 2024`, `Dec. 31, 2023`, `Dec. 31, 2022`).
- Facts include a mix of instants (cover/segment contexts) and durations (quarterly, trailing twelve months) that we currently treat equally.
- Consequence: columns become unsorted, duplicates appear with "(As of)"/"(YTD)" suffixes, and the workbook becomes unreadable.

### Ideas
- Filter periods per statement type:
  - Balance Sheet → latest N instants (e.g., current + prior year end).
  - Income Statement / Cash Flows → latest N annual durations, optionally latest quarter.
- Prefer contexts tied to the filing fiscal period (match `DocumentPeriodEndDate`).
- Deduplicate contexts that differ only by instant/duration flag once the preferred set is chosen.

### Open Questions
- How do we expose configuration (CLI flags vs coded defaults) for annual vs quarterly focus?
- Should we surface discarded periods via warnings so analysts know data was filtered?
- Do we need company-specific heuristics (e.g., entities with non-calendar fiscal years)?

## Next Steps
1. Prototype a role-filtering layer in `PresentationParser`/`DataParser` that maps role URIs to canonical sheet assignments and drops unneeded roles by default.
2. Update `FactMatcher.extract_periods_from_facts` (or downstream filtering) to return a curated, statement-specific period list.
3. Add regression tests comparing sheet counts and period headers against fixture expectations.
4. Re-run the CLI on TSLA and adjust heuristics until the workbook resembles Financial_Report.xlsx.
