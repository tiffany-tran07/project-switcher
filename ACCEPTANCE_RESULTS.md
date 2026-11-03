# Local export acceptance results

## Environment

- Apple Silicon macOS; LibreOffice **26.8.2.2**, installed using the Homebrew cask.
- No `.env` change was needed: existing executable detection finds `soffice`.
- Tests use fictional data and disposable databases, not personal career records. No career data was uploaded.

## Completed checks

- Real conversion of an approved fixture through the existing DOCX → LibreOffice → PDF pipeline.
- Real API PDF export, checksum-protected download, and actual-file ATS text/order/page-target checks.
- Synthetic symbols/context fixture: **1 page**. Dates, ≥/≤ comparisons, currencies, minus signs, ranges, C++/C#/.NET/A/B, accents, quotes, and encoded URL punctuation survive extraction.
- Synthetic pagination fixture: **3 pages**; all source paragraphs survive extraction in document order.
- Both real-converted PDFs also pass through the new untrusted PDF Intake worker with their text/order preserved. Browser coverage separately exercises PDF dropping, no-text/OCR errors, retained prior work, and explicit draft-only excerpt saving.
- Visual inspection of all four rendered PDF pages using native macOS PDFKit: readable single-column text, bullets, dates, symbols, and project context; no clipping/overlap observed in these fixtures. Multi-page bullet flow continues in order across page breaks.

The synthetic fixture generator lives in `backend/tests/acceptance_documents.py`. These are render-only examples, not real verified career claims. The real-conversion tests remain conditional on LibreOffice for other installations.

## Local samples

Git-ignored output folder on this machine:

`data/acceptance-exports/libreoffice-QlKQoF/`

Contains `fictional-symbols.docx/.pdf`, `fictional-pagination.docx/.pdf`, extracted text, page images, and `report.json` with page counts and SHA-256 hashes. Files are deliberately fictional and were generated without opening the active database.

## Still pending

- A real, user-reviewed resume through Intake (now PDF/DOCX/text), manual evidence verification, tailoring, and export. Scanned PDFs still require local OCR first.
- User review of actual document layout and page targets; the synthetic stress fixture is not a recommended three-page resume.
- Native Microsoft Word visual inspection. The reviewed PDFs reflect LibreOffice's interpretation of the generated DOCX, not every Word version.
- Optional real Ollama model evaluation, if that feature is wanted.

These results do not declare full MVP acceptance or start Milestones 7–8.

## Installation side effect

Homebrew automatically ran cleanup after installation, removing older package versions and 35 formulae it classified as unused (including `tesseract`). This was not a separately requested cleanup. No further package removals or reinstalls were requested. Confirm any needed restoration separately. For future installs, set `HOMEBREW_NO_INSTALL_CLEANUP=1` to suppress this behavior.
