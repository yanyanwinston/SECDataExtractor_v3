# TSLA 10-K rendering failure (2025-09-26)

## Summary
Running the new `download_and_render.py` workflow against Tesla's recent 10-Ks failed during the Excel rendering phase. Arelle exited without producing `ixbrl-viewer.htm`, so the renderer aborted with "viewer file was not created" errors.

## Impact
- All TSLA 10-K render attempts in the combined workflow failed.
- No Excel workbooks were generated for the requested filings.
- Workflow looked successful up to the download stage, so the failure surfaced late in the pipeline.

## Detection
Observed while testing `python download_and_render.py --ticker TSLA --k-count 5 --q-count 10 --overwrite`: Arelle logs indicated successful completion, but no viewer artifact existed in the temp directory. The wrapper logged repeated `Unexpected error during Arelle processing: Arelle completed but viewer file was not created` messages.

## Root Cause
The combined workflow chooses an input artifact for rendering via `determine_filing_input`. Before the fix, that helper:
1. Preferred any already-extracted primary HTML file.
2. Fell back to the first `.htm`/`.html` in the download directory.

For TSLA filings, the downloader saved hundreds of split report fragments (`R1.htm`, `R2.htm`, …) alongside the packaged inline filing (`0001628280-25-003063-xbrl.zip`). None of those split fragments contains the embedded inline facts; they are consumer-facing presentation slices. Because `primary_file_path` returned `R89.htm`, the renderer handed that fragment to Arelle. Arelle will exit 0 when given a plain HTML file with no inline content, but it does not emit an iXBRL viewer, leaving our pipeline without the expected `ixbrl-viewer.htm`.

## Resolution
Updated `determine_filing_input` (`download_and_render.py:210`) so we only hand off real inline sources:
- Prefer `ixviewer.zip` if it exists.
- Otherwise look for packaged inline bundles (`*ixbrl.zip`, `*xbrl.zip`, etc.).
- Skip `R##.htm` fragments and index stubs when considering HTML fallbacks.
- Fallback hierarchies remain for legacy cases, but only after excluding fragment stubs.

After this change, the renderer feeds Arelle the packaged inline filing and the viewer is generated correctly.

## Follow-up
- Consider pruning the `R##.htm` fragments when `--include-exhibits` is false to reduce bandwidth and storage.
- Add a regression test ensuring `determine_filing_input` selects packaged inline sources when present.
- Capture Arelle stdout/stderr to provide a clearer error when the viewer artifact is missing in future runs.
