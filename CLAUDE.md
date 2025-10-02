# Repository Guidelines

## Project Snapshot
- SECDataExtractor v3 now leads a data-first pipeline: EDGAR filings -> Arelle viewer payloads -> bronze fact/presentation tables -> CCD normalization -> valuation-ready gold layers.
- Flow: filing source -> Arelle viewer plugin -> viewer JSON + MetaLinks -> presentation models -> fact_long/statement tables -> canonical wides + audit trails.
- Primary modules live under `src/processor/` (parsing, matching, Excel, upcoming exporters) and `src/sec_downloader/` (EDGAR search + download).
- The Excel exporter remains supported for analyst workflows; new data contracts must coexist with the XLSX path.

## Entry Points
- `download_filings.py` – search and download 10-K/10-Q filings (tickers, CIKs, or batch files) into `downloads/`.
- `export_tables.py` – parse viewer payloads into `statement_lines`, `statement_facts`, and `fact_long` artifacts (bronze/silver). Emits Parquet/CSV when invoked with `--out data/`.
- `normalize_financials.py` (planned) – apply the canonical concept dictionary to bronze/silver tables and produce gold wides plus `normalized_fact_long`.
- `valuation_interfaces.py` (planned) – thin wrappers that project gold tables into RI, DCF, and multiples inputs.
- `render_viewer_to_xlsx.py` – convert iXBRL filings into Excel; keep running for validation and downstream tasks needing spreadsheets.
- `download_and_render.py` – orchestrate download + render for portfolios, depositing workbooks in `output/`.

## Working Directories
- `downloads/` – raw filings pulled from EDGAR.
- `data/bronze/` – persisted viewer payloads and canonical `fact_long`.
- `data/silver/` – `statement_lines` and `statement_facts` per accession.
- `data/gold/` – normalized wides and audit trails for valuation.
- `output/` – generated Excel files (still used for QA and spreadsheet consumers).
- `temp/` – temporary artefacts preserved only when `--keep-temp` is passed.

## Daily Commands
```bash
./setup.sh
source venv/bin/activate
PYTHONPATH=. pytest
black . && flake8 src tests
mypy src
PYTHONPATH=. pytest tests/test_presentation_parser.py tests/test_integration_presentation.py
python export_tables.py --filing downloads/TSLA/10-K_*/tsla-*.htm --out data/ --keep-temp
python normalize_financials.py --accession downloads/TSLA/... --out data/gold/   # once normalization CLI lands
python render_viewer_to_xlsx.py --filing downloads/TSLA/10-K_*/tsla-*.htm --out output/tsla.xlsx
```
Run at least one TSLA end-to-end smoke that covers bronze -> silver -> gold and confirms the Excel workbook remains aligned.

## Coding Standards
- PEP 8, four-space indentation, descriptive names, and rich type hints.
- Dataclasses/enums use PascalCase; everything else stays snake_case.
- Preserve raw numeric values (`value_numeric` + `unit`) separately from display scaling. Excel formatting must consume display values; storage/write paths must persist raw numbers.
- Treat Parquet schemas as contracts: version `data_format_version`, stamp taxonomy/tool versions, and document changes in `docs/`.
- Always carry provenance (`filing_id`, `statement_role_id`, `concept_qname`, `normalized_item`) through transformations and QC logs.
- Keep helpers lean and purposeful; prefer direct fixes before introducing new abstraction layers.

## Testing & Validation
- `tests/test_presentation_parser.py` and `tests/test_integration_presentation.py` guard statement filtering, label handling, and MetaLinks metadata (bronze/silver).
- Add normalization golden tests (AAPL/MSFT/TSLA/JPM) to cover CCD mappings, sign normalization, and period policies.
- Extend `tests/test_excel_generator.py` to ensure Excel remains consistent with silver outputs.
- Regression harnesses should verify QC gates (balance sheet, cash roll-forward, dimension leakage) and valuation interface reconciliations.
- `test_processor.py` remains a manual harness (skipped by default).

## Documentation
- Canonical docs live in `docs/`: `architecture.md`, `user-guide.md`, `cli-reference.md`, `developer-guide.md`.
- Roadmap specs for Steps 2–5: `docs/xbrl_pipeline_specs_steps_2_5.md`. Keep CCD/override references in sync.
- Step-by-step plans live under `docs/plans/` (see @docs/plans/folder).
- Historical specs: `docs/11-refactor-spec-v3.1.md`, `SPEC.md`, `CLAUDE.md`.
- Update README and docs whenever behaviour changes; capture validation commands in PR summaries.

## Release Checklist
1. `PYTHONPATH=. pytest`
2. `black .`, `flake8 src tests`, `mypy src`
3. Bronze/silver export smoke on fresh filings (e.g., TSLA 10-K) and inspect Parquet metadata.
4. Normalize at least two filings per form type; verify CCD coverage and QC gates (balance, cash roll-forward).
5. Render Excel for the same filings and compare headline numbers against gold outputs.
6. Refresh documentation, CCD versioning notes, and CLI references; record commands + findings before tagging.

## Current Status
- Presentation-first bronze/silver pipeline is stable; normalization (Step 3) and storage orchestration (Step 4) are in active build-out.
- Excel parity remains a guardrail; continue using workbooks for visual QA while transitioning valuation to data tables.
- Outstanding work: CCD population, per-company overrides, DuckDB/Postgres schema migrations, valuation adapters, and productionizing QC dashboards.
- MetaLinks `groupType` filter keeps primary statements by default; pass `--include-disclosures` to surface schedules and cover pages.
