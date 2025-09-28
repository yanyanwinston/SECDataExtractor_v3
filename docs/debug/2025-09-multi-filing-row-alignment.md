# Multi-Filing Ensemble: Duplicate Rows Investigation (TSLA 10-Ks)

## Summary
While reviewing `output/tsla-multi-year.xlsx`, the "Digital assets, net" line
appears twice on the Balance Sheet. The ensemble merger failed to align the
row from older filings with the anchor row because the concept QName changed
between periods (extension namespace vs base). The current canonical key uses
concept + label + depth metadata, so differing QNames bypass matching and the
row is appended as "extra" data, producing duplicates.

## Repro steps
1. Generate viewer payloads: `temp/tsla-2025-viewer.json` (10-K 2024) and
   `temp/tsla-2023-viewer.json` (10-K 2023).
2. Parse each with `DataParser(ValueFormatter())`.
3. Inspect Balance Sheet rows containing "Digital".

Observed concepts:
- 2025 anchor: `ns0:DigitalAssetsNetNonCurrent`
- 2023 slice: `tsla:DigitalAssetsNetNonCurrent`

Both rows share the same label (`Digital assets, net`), depth (2), and order (5),
but the concept QName differs due to taxonomy changes.

## Root cause
`_canonical_row_key` (src/processor/ensemble.py:62) includes the concept QName
in the key. When namespaces shift between filings, the merger treats the rows as
being different and queues the older one in `extra_rows`. After iteration, the
additional row is appended to the sheet, giving duplicate display rows.

The issue is triggered by concept reclassification (extension → base taxonomy)
or other QName rewrites even when the semantic line item is identical.

## Proposed fix
Introduce a normalised concept token for the canonical key so records with the
same local name (and/or identical labels) across namespaces can still align:

- Derive `concept_normalised = concept.split(':', 1)[-1].lower()`.
- Enhance `_canonical_row_key` to use `(concept, concept_normalised)` when
  building dictionaries.
- Preserve existing namespace-aware key to avoid collisions when two distinct
  concepts share the same local name but live under different parents. Use the
  label + depth + parent order as a secondary discriminator when both concept
  tokens match.
- Add debug logging for rows that fall back to the normalised key so we can
  spot ambiguous mappings during tests.

This should map `ns0:DigitalAssetsNetNonCurrent` and
`tsla:DigitalAssetsNetNonCurrent` to the same slot, eliminating the duplicate.

## Next steps / ideas
- Track concept aliases via MetaLinks `longName` or role metadata to map
  extension concepts to later standard QNames when names truly diverge.
- Emit debug logging for rows dropped into `extra_rows` so mismatches surface
  during tests.
