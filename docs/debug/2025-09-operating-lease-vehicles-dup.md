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

## Next steps to consider
- extend row matching to include presentation role / ancestor chain (already stored in `_canonical_row_key`) or dimension signatures so disclosure contexts cannot satisfy a primary statement match;
- alternatively, filter statement rows to the role that matches the anchor before alignment, ensuring note-only contexts never participate in balance sheet aggregation.
