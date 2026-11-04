# Build status

## Current phase

**MVP integration and acceptance testing across Milestones 1–6.** The core workflow is implemented and exercised with automated tests, including an isolated Chromium workflow. This is not a declaration that every milestone acceptance check is complete. Semantic search (7) and browser application assistance (8) have not started.

| Milestone | Implemented core | Remaining validation / limitations |
| --- | --- | --- |
| 1 — Foundation | Local React/FastAPI startup, SQLite migrations, lint/type/test runners | Browser tests start a fresh isolated installation; normal use remains localhost-only. |
| 2 — Evidence library | Profile, roles, projects, skills/aliases, evidence, metrics, variants, PDF/DOCX/text Intake previews, local text-source attachments, archive/recovery UI, search, JSON export | Persistent supporting attachments (separate from Intake) remain UTF-8 .txt only (1 MB), append-only, and currently require macOS/Linux file operations. Scanned-PDF OCR and attachment PDF/images, replacement, and deletion are not implemented. Claims still require manual truth/source review. |
| 3 — Jobs and matching | Pasted jobs, editable/confirmed requirements, deterministic and optional local extraction, source-linked matches and gaps | Local-model behavior is tested with fixtures/local HTTP servers, not a real installed model. Related matches are not proof. |
| 4 — Resume drafting | Verified-only selection, sections/order, conservative wording, source validation, immutable snapshots/history | No broad AI paraphrasing. Working selections are tab-memory only; reload clears them. |
| 5 — Export and ATS readiness | DOCX and optional LibreOffice PDF export, checksums, actual-file text extraction, keyword/support gaps, PDF page targets | LibreOffice 26.8.2.2 is installed; real conversion, API download/ATS, and fictional 1-/3-page PDF visual checks are covered. Real-user document acceptance and native Word inspection remain pending. |
| 6 — Tracking and backup | Exact approved-version links, application history/follow-ups, portable backup export, validated clean-directory CLI restore | Restore is deliberately not a live-database/browser replacement. Backups are unencrypted. |
| 7 — Semantic search | Not started | Establish real lexical-search misses and fixtures before adding embeddings. |
| 8 — Application assistant | Not started | Playwright currently tests this app only; it does not fill or submit external job forms. |

## Current UX increment

Working resume selections, section order, and wording survive page navigation and switching between resumes in the same open tab. They are kept in React memory only—not localStorage, sessionStorage, the database, or backups. Source state is not cached as verification: saving a version still rechecks current evidence. An unavailable/rejected source does not erase wording or become usable merely because a working selection was restored.

The Archive view now supports searching and restoring career records, with dependency guidance and retry-safe errors. Recovery preserves the record's saved state; it does not verify claims or alter historical snapshots/exports.

Supporting source files can now be explicitly uploaded to saved evidence. Uploads remain local, clear verification and bullet approvals, and preserve selected files after failed requests. New snapshots capture immutable file references; downloads, new snapshot validation, backup, and clean-directory restore check file integrity. This is separate from transient Intake previews. **Existing installations need `alembic upgrade head` before using the new registry.** Migration/schema checks used a disposable database; existing user data was not migrated during this increment.

Historical source links now handle archived, missing, and uncached evidence without presenting a new-record form. The source lookup is read-only, clearly separates current library content from saved snapshot content, and offers retry, library refresh, and Archive navigation. Browser coverage includes lookup/refresh failures and a source restored outside the current view. No schema or evidence-policy change in this increment.

Experience/project/skill forms now select successfully created records and retain selection and input after failed saves/archives. Pending library writes lock their fields, record list, sidebar navigation, and search. The editors live in `frontend/src/CareerEditors.tsx`; a dedicated Chromium test covers all three. Regression tests also cover repeated skill alias saves and transactional rollback on skill-name conflicts. There is no new schema or verification-policy change; cross-page autosave/unsaved-navigation warnings remain outside this increment.

Resume source choices now use API-owned eligibility, shared with final draft validation: verified flags alone do not bypass archived linked context or missing/damaged source files. The picker fails closed during checks/errors, offers explicit refresh/review, and preserves existing working wording/selections. Checks are point-in-time rather than continuous monitoring; saving still rechecks current source, section, and wording rules. No schema change, automatic verification, or historical snapshot mutation is introduced.

The contact profile editor preserves raw multiline link input (including Enter/blank lines), normalizing it only for save. Contact fields lock during writes; failed saves retain the raw draft. Browser coverage checks typed multi-link input, pending/failure recovery, and immutable saved contact details after later profile edits. No schema or backend policy change; profile edits still need saving before page navigation.

Text-based PDF Intake now uses a bounded isolated-process reader, reading-order warnings, and OCR-required handling for no-text/scanned documents. Partially empty text layers warn rather than silently claiming a complete import. Drag/drop and file selection work for PDF/DOCX/text, and failed previews preserve prior reviewed work. Saving remains an explicit exact-excerpt, draft-only action; no uploaded resume is retained or automatically verified. There is no schema change; older environments must update backend requirements for the PDF parser minimum version.

Intake clear/replacement now asks before discarding pending review work, and identical re-previews keep excerpts/notes intact. A different accepted file clears the role/project selection. Edited extraction text is visibly labeled and saved with an explicit, user-reported provenance note; the reviewed-text hash still describes the submitted text, and every imported claim remains draft. No schema change, whole-resume storage, cross-page autosave, or automatic verification was added.

A one-command automated release gate now combines all existing checks with a connected fictional PDF intake → drafting → DOCX/PDF/ATS → backup → clean restore drill. The restored API runs in a new process with `DATABASE_URL` cleared; record collections, attachment/export checksums, ATS results, and history triggers are compared. Reports/logs and fictional artifacts are retained in new private Git-ignored directories. Active database settings are overridden, normal frontend build/browser artifacts are preserved, and no dependencies are downloaded. Full passes remain automated fixture coverage—not final real-user acceptance. See README for `.venv/bin/python scripts/release_check.py` and the explicitly partial `--workflow-only` mode.

## Next acceptance checks

1. Exercise Intake and the evidence workflow with a real, user-reviewed resume. Text-based PDF, DOCX, and UTF-8 text are supported through file selection or drop; scanned/image-only PDF content requires local OCR or pasted reviewed text.
2. Review real-user DOCX/PDF outputs and page targets; synthetic LibreOffice conversion and rendered-PDF visual checks now pass on this machine. See `ACCEPTANCE_RESULTS.md` for scope and local samples. Native Word behavior and real-document layouts are not yet accepted.
3. Optionally evaluate an installed, appropriately licensed Ollama model against real job descriptions. Core features do not depend on it, and no cloud AI is required.
4. Collect usability issues and actual matching misses before moving to Milestone 7.

See `README.md` for setup, test commands, backup/restore precautions, and feature limitations. Use high reasoning for security, schema changes, evidence-policy changes, and architecture review; medium is suitable for ordinary UI increments. Internet access may be useful for official tooling documentation or installation, but personal resumes and career data should remain local.
