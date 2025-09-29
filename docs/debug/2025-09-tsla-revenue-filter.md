# TSLA 2022 10-K revenue rows missing after inline filtering

## Summary
After enabling the inline visibility filter for presentation-first runs, the Consolidated Statement of Operations in Tesla's 2022 10-K lost multiple revenue lines (Automotive sales, Automotive regulatory credits, Automotive leasing, Total automotive revenues, Energy generation and storage, Services and other). The filtering pass believed those rows were not visible in the inline filing, so they were dropped despite being part of the published HTML statement.

## Reproduction
1. ``python render_viewer_to_xlsx.py --filing downloads/TSLA/10-K_2022-12-31/tsla-20221231.htm --out temp/tsla_debug.xlsx --save-viewer-json temp/tsla_viewer.json --keep-temp --verbose``
2. Inspect ``temp/render_success.log`` (same run without redirect prints the log) and note the ``Skipping row`` messages for each missing revenue line.
3. The generated workbook omits the affected rows.

## Findings
- ``FactMatcher._filter_visible_rows`` (src/processor/fact_matcher.py:269-305) filters data rows unless their ``(concept, dimensions)`` signature exists in the active allow-list built from the inline HTML.
- The allow-list comes from ``ViewerDataExtractor._extract_visible_fact_signatures`` (src/processor/json_extractor.py:301-365). That helper was written assuming it would read the SEC-supplied ``*_htm.xml`` context file that ships with the original filing bundle. When we drive the parser off the Arelle-generated viewer HTML instead, there is no ``ixbrl-viewer_htm.xml`` companion, so the context lookup returns an empty dimensional fingerprint for every fact.
- The saved viewer JSON (``temp/tsla_viewer3.json``) confirms that each entry under ``"consolidated statements of operations"`` has an empty dimensions array. Meanwhile, the matcher derives the real fingerprints from the viewer facts (e.g., ``ProductOrServiceAxis=AutomotiveRevenuesMember``), so the signatures never match and every dimensioned revenue row is skipped.
- The same issue hits other dimensioned rows like ``Operating lease vehicles, net`` (property, plant & equipment by type axis) in the balance sheet.

## Root Cause
``_extract_visible_fact_signatures`` relied solely on the SEC sidecar ``*_htm.xml`` contexts. Arelle’s viewer output does not provide that file, so when we parse ``ixbrl-viewer.htm`` the helper cannot recover dimension members and records dimensionless signatures. The visibility filter then rejects legitimate rows that carry dimensions.

## Remediation
- ``_extract_visible_fact_signatures`` now looks for SEC-generated context files referenced by ``MetaLinks.json`` (for example ``tsla-20221231_htm.xml``) when the viewer-side ``ixbrl-viewer_htm.xml`` is absent, ensuring dimensional fingerprints carry through to the visibility filter.
- Follow up by adding a regression test (fixture with the saved TSLA viewer payload) so the automotive revenue rows stay visible.
- Re-run the TSLA 2022 10-K pipeline (and another segmented income statement) to validate the restored output and catch any remaining disclosures trimmed by visibility filtering (e.g., facts with additional axes outside ``ProductOrServiceAxis``).
