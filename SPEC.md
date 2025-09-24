# SPEC.md

## Goal

Generate Excel financial statements that **match the filer’s HTML/iXBRL presentation** (row order, section headers, labels) by using **Arelle’s iXBRLViewerPlugin** to produce the viewer JSON and then rendering that JSON to XLSX with our own number formatting.

## Inputs

* **Filing source**: URL or local path to an iXBRL filing (single HTML or the SEC “filing-documents” zip).
* **Target statements**: Balance Sheet (BS), Income Statement (IS), Cash Flows (CF).
* **Display options**

  * Currency display: **USD in millions** with thousands separators and parentheses for negatives.
  * EPS: **2 decimals**.
  * Weighted-average shares: **millions, no decimals**.
  * Blank/unavailable value: em dash `—`.

## Outputs

* `financials_aligned.xlsx` with one sheet per statement (default is **multi-period**; allow a `--one-period` flag).

  * **Rows** exactly match the viewer’s tables (including abstract/section rows and ordering).
  * **Columns** correspond to periods the viewer shows for that statement and order (e.g., 2024, 2023, 2022).
  * Styles: bold section headers (abstracts), indentation based on tree depth, thin border under totals.

## System outline

1. **Build viewer HTML (and embedded JSON)**

   * Install: `pip install arelle-release ixbrl-viewer`
   * Run:

     ```bash
     python -m arelle.CntlrCmdLine \
       --plugins iXBRLViewerPlugin \
       --file <FILING_PATH_OR_URL> \
       --save-viewer <OUT_DIR>/ixbrl-viewer.htm
     ```
   * This creates `ixbrl-viewer.htm` containing a `<script>` tag with a large JSON blob (the “viewer data”).

2. **Extract viewer JSON**

   * Read the HTML; locate the script tag containing `window.ixv =` or the JSON object assigned for viewer data.
   * Parse JSON safely (strip prefix/suffix JS if needed).
   * Persist as `viewer.json` (optional, for debugging).

3. **Understand the viewer JSON (what we need)**

   * **Tables**: Pre-assembled statement tables (rows/columns) the viewer renders.
   * For each statement:

     * Table metadata: title, role/ELR, statement type.
     * **Rows**: ordered list with label text, depth/indent, abstract flag, concept qname (if any), preferred label role (if any).
     * **Columns**: periods (instant/duration) with end dates and display captions.
     * **Cells**: facts keyed by row id × column id, already aligned to the presentation.
   * NOTE: exact keys can vary by viewer version; discover them programmatically and avoid hard-coding. Build adapters with defensive checks.

4. **Reconstruct tables → in-memory model**

   * Create `Statement` objects: `{name, roleURI, columns: [Period], rows: [Row]}`.
   * `Row`: `{label, depth, abstract, conceptQname?, preferredLabel?}`
   * `Cell`: `{rawValue, decimals?, unit?, signFixApplied?}`
   * Keep original **row order** and **labels** verbatim.

5. **Value normalization & formatting**

   * Decide by **unit**:

     * USD or company currency → divide by **1,000,000** and round to **0 decimals** (display).
     * Per-share (EPS) → keep raw magnitude; display **2 decimals**.
     * Shares (weighted average) → divide by **1,000,000**; **0 decimals**.
   * Negatives → display with **parentheses**.
   * Missing → `—`.
   * Respect cell/row viewer hints for **negated labels** if the viewer already flipped signs (usually it has); do not double-flip.

6. **Write XLSX**

   * Library: `openpyxl`.
   * Sheet names: `Balance Sheet`, `Income Statement`, `Cash Flows`.
   * First row: statement title, then column headers (period captions from viewer).
   * For each row: apply indentation (`alignment.indent = depth`) and bold for `abstract`.
   * Add thin bottom border to “total” rows when `preferredLabel` or label contains “Total”.

7. **CLI**

   ```bash
   python render_viewer_to_xlsx.py \
     --filing <URL_OR_PATH> \
     --out financials_aligned.xlsx \
     [--one-period] [--periods 2024,2023] [--currency USD] [--scale-millions]
   ```

8. **Acceptance tests**

   * The **row labels** and **order** in each sheet match what the iXBRL Viewer shows in the browser for the same filing.
   * Period captions match the viewer (e.g., “Year Ended December 31, 2024”).
   * A random spot-check of 10 rows across statements matches viewer values after applying display scaling.
   * Abstract/section rows are bold and have no values.

9. **Edge cases**

   * Statements with **dimensional tables** (rare for primary statements): if the viewer splits into multiple tables, write one sheet per table or stack them with spacer rows.
   * Non-USD currency: display currency symbol from viewer; still scale to millions unless `--scale-none`.
   * Very long labels: enable text wrap; set column widths reasonably.

10. **Non-goals**

    * Do not recompute totals; render reported values only.
    * Do not merge cells (keeps editing simple).
