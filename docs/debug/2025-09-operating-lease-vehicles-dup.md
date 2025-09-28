# Operating Lease Vehicles duplication (TSLA multi-year ensemble)

## Symptom
- `output/tsla-multi-year.xlsx` shows two Balance Sheet rows labeled "Operating Lease Vehicles". The anchor row carries 2024-2021 values plus a $43M point for Dec 31, 2020, while a second row contains only the Dec 31, 2020 column with $3,091M.

## What the filings contain
- The 2020 inline filing publishes two facts for `us-gaap:DeferredCostsLeasingNetNoncurrent`:
  - `$3,091M` sits on the Consolidated Balance Sheet context with `PropertyPlantAndEquipmentByTypeAxis=OperatingLeaseVehiclesMember` (`contextRef="C_0001318605_us-gaapPropertyPlantAndEquipmentByTypeAxis_tslaOperatingLeaseVehiclesMember_20201231"`). See `downloads/TSLA/10-K_2020-12-31/tsla-10k_20201231.htm:13047`.
  - `$43M` belongs to the Resale Value Guarantee disclosure with `GuaranteeObligationsByNatureAxis=SalesToLeasingCompaniesWithGuaranteeMember` (`contextRef="C_0001318605_us-gaapGuaranteeObligationsByNatureAxis_tslaSalesToLeasingCompaniesWithGuaranteeMember_20201231"`). See `downloads/TSLA/10-K_2020-12-31/tsla-10k_20201231.htm:20298`.
- The 2020 presentation linkbase anchors the concept under three different roles: the balance sheet, Summary of Significant Accounting Policies, and the VIE disclosure (`downloads/TSLA/10-K_2020-12-31/tsla-20201231_pre.xml:143`, `downloads/TSLA/10-K_2020-12-31/tsla-20201231_pre.xml:1219`, `downloads/TSLA/10-K_2020-12-31/tsla-20201231_pre.xml:3625`).
- The 2024 filing (our anchor) only exposes the balance sheet presentation for that concept (`downloads/TSLA/10-K_2024-12-31/tsla-20241231_pre.xml:123`).

## Alignment behaviour
- `_rows_match` in `src/processor/ensemble.py:128` treats rows as equivalent if their concepts (after namespace stripping) and label tokens agree, ignoring statement role, presentation ancestry, and dimensional context.
- During `_map_rows`, the 2020 disclosure row (value $43M) appears before the balance sheet row inside the parsed statement, so the first match against the anchor row succeeds and injects $43M into the ensemble column. The true balance sheet row ($3,091M) is left unmatched and gets appended as an "extra" row, creating the visible duplicate.

## Diagnosis
The ensemble alignment collapses distinct dimensional contexts for the same concept/label. Because `_rows_match` does not consider presentation role or axis members, any filing that publishes the same concept in both the primary statement and a disclosure will populate the anchor slot with whichever instance appears first, while the correct statement row is relegated to the leftovers list. For Tesla's Dec 31, 2020 data this misroutes the Resale Value Guarantee disclosure total ($43M) into the Balance Sheet and leaves the actual balance sheet amount ($3,091M) on a duplicate row.

## Remediation plan
- Capture a dimension signature for every row when we expand facts by axis members in `FactMatcher`. Store the unsanitised axis→member tuple beside the cloned `PresentationNode` so it flows into the legacy `Row` objects even when the axis is not part of the presentation tree.
- Thread that signature (and the presentation ancestor path we already compute) through `_canonical_row_key` and require equality in `_rows_match` whenever both sides expose it. Keep the current concept/label fallback only when neither row carries signature metadata.
- Add targeted coverage that builds a mini ensemble with two rows sharing the same concept but different dimension signatures to confirm the disclosure row stays in the leftovers list. The test should fail on main, then pass once the matcher and alignment changes ship.
- Re-run the TSLA 2020/2024 ensemble after the code change to confirm the balance sheet slot holds `$3,091M` while the guarantee disclosure lives in the extras section, and update the regression artefact screenshots if applicable.
