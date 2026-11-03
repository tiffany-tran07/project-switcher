# Resume Tailor

A local-first resume tailoring app. The career evidence library, job matching, and an initial evidence-backed resume snapshot workflow are available. See [BUILD_GUIDE.md](BUILD_GUIDE.md) for the plan and [BUILD_STATUS.md](BUILD_STATUS.md) for the current phase and remaining acceptance checks.

## Requirements

- Python 3.12 or 3.13 (use 3.12 for the documented setup; the system's 3.15 is ahead of some dependency support)
- Node.js 20.19+ or 22.12+ (Node 24 also works)
- npm

## Local setup

From the repository root:

```bash
cp .env.example .env
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open <http://127.0.0.1:5173>. The API is at <http://127.0.0.1:8000/health>; it returns `{"status":"ok"}` after migration. The local database, attachments, and exports live under `data/`, which Git ignores. Set `DATA_DIR` in `.env` to an absolute path to move them. If you set `DATABASE_URL`, use a SQLite URL and keep it inside your chosen local data directory.

When updating an existing installation, stop the API and run `alembic upgrade head` from `backend` with the virtual environment active, then restart it. The source-file feature adds an attachment registry without rewriting career records or historical snapshots. Keep backups with their matching app/schema version; restore does not silently upgrade older archives.

## Dashboard

The app opens with counts and recent jobs, resumes, and applications, plus evidence needing review and follow-ups due on or before today's UTC date. Rejected and withdrawn applications are excluded from due reminders. A verified evidence record whose source context has been archived is not counted as ready for drafting. Each list shows at most five records while totals include all non-archived records. Select a row to open that specific record; the dashboard never sends follow-up messages automatically.

## Existing resume intake

Open **Intake** to select an existing `.docx` or UTF-8 `.txt` resume, or paste its text. File previews are processed by the configured backend (localhost by default), without AI calls, saved uploads, database records, or automatic verification. Check extracted dates, metrics, symbols, and table order. To save an accomplishment, highlight its exact text, choose **Use highlighted text as a claim**, link an active experience or project, and choose **Save as draft evidence**. If the source role or project is not in the library yet, choose **Create experience or project here**. Enter its details manually; the new record is selected automatically without clearing the preview, selected claim, or notes. Projects may be independent or linked to an existing active experience. Cancellation and validation/server errors keep the intake text in place. The API rejects invented excerpts and matching active claims already saved for the same context. Only the selected claim, its context, source name, reviewed-text checksum, and optional supporting notes are stored—not the full resume. Every imported claim remains draft until you explicitly review and verify it in Evidence. DOCX headers, footers, text boxes, images, and nested tables may be omitted; table cells are shown in physical document order. PDF intake is not available yet—paste text from your PDF instead. Previews disappear when leaving the page.

Limits: 5 MB upload, 32 MB expanded DOCX, 8 MB per XML part, 500 package entries, and 100,000 extracted characters. Invalid packages, macro-enabled content, embedded objects, XML entity declarations, and unsupported entry types are rejected. A resume is a starting point for review, not independent proof of its claims.

## Career library

Use the sidebar to add experiences and projects, then create skills with optional aliases. Add one evidence item for each claim, link it to an experience or project, and record where you can verify it. Metrics have their own source notes. Save the item before clicking **Verify**. Editing a claim, its context, a linked skill, or a metric returns it to draft and clears approval on its bullet variants.

The Evidence editor blocks verification while claim/context/skill edits, unfinished metric/bullet forms, or a selected supporting file are pending. Save or explicitly reset/clear the relevant form first. Failed metric/bullet saves and deletions preserve input and edit mode; failed archiving keeps the evidence selected. A newly saved evidence record is selected automatically. If a write succeeds but refreshing fails, the UI warns you to reload before retrying instead of reporting a clean success. These safeguards do not provide cross-page autosave—save work before leaving the page.

In a saved evidence item, **Supporting source files** accepts UTF-8 `.txt` notes/logs up to 1 MB. This is a persistent upload, separate from transient resume Intake previews. Files remain under `data/attachments/`, with private file permissions and SHA-256 checksums; they are never interpreted or sent to AI. Adding a file returns the evidence to draft and clears bullet approvals. Review the sources and explicitly verify again. New snapshots retain source-file IDs/names/checksums and expose download links; source-file availability/checksums are checked before saving, and missing/damaged proof blocks new snapshots. File contents and filenames are not printed in the resume export. Downloads verify checksums and force plain-text attachment delivery. Failed uploads keep the selected file available for retry; duplicate bytes on the same evidence are rejected. **This increment is text-only and append-only: no PDF/image attachments, replacement, or in-app file deletion.** Source-file storage currently requires POSIX no-follow file support (macOS/Linux).

Experience, project, and skill editors select newly saved records, so another save updates that record rather than submitting a second create. Failed saves and archives preserve the form and selection; selection is cleared only after a successful archive and library refresh. Fields, record selection, sidebar navigation, and search are locked during these library writes. **+ New** explicitly clears the form. Archiving affects the saved record, not unsaved field changes. These safeguards do not add cross-page autosave or unsaved-navigation warnings. Repeated skill saves retain unchanged alias rows; uniqueness conflicts roll back aliases and linked verification changes together.

Use **Archive** to search and recover archived experiences, projects, skills, or evidence. The view explains dependency order: restore linked experiences before projects, then linked projects before evidence. Restoration preserves the existing evidence state—it does not verify draft/rejected claims—and never rewrites saved resume snapshots or export files. Failed restore requests keep the archived record visible for retry. Source links from saved resumes, applications, and reports never fall back to a blank new-evidence form when a record is absent from the active list. The editor looks up that source read-only, distinguishes the current library record from the historical snapshot, and offers Archive or a library refresh. Lookup/refresh failures remain retryable; navigation does not restore or verify anything automatically.

Search checks experiences, projects, skills, aliases, and evidence through SQLite FTS5. **Export JSON** downloads the career library, including archived records and attachment metadata, but not file bytes; use a full backup to preserve files. The API schema is available at <http://127.0.0.1:8000/docs>.

## Job workspace

Use **Jobs** in the sidebar to paste a description. The original posting remains unchanged; save a new job to replace its text. Deterministic extraction produces draft requirements with cited posting spans and suggested priorities. Edit, add, remove, confirm, and save requirements before reviewing matches. Changing a requirement's text removes its confirmation and citation; review and confirm it again. Matching considers only active verified evidence and distinguishes direct, related, and unsupported requirements. Related matches are lexical hints, not proof. Select a match to open its source evidence. You can optionally set `OLLAMA_CHAT_MODEL` to an installed Ollama model and use **Try local Ollama**. The API allows only plain localhost HTTP base URLs, pins connections to numeric `127.0.0.1`, disables environment proxies and redirects, limits JSON responses to 1 MB, and rejects unsupported citations. If model extraction fails, existing saved requirements (including edits and confirmations) are preserved; if no requirements exist, deterministic extraction is used. Unsaved requirement edits in the workspace also remain in place on fallback and still require an explicit save. The UI labels the actual outcome for the latest request in the current session; it is not persisted as analysis history. Re-extraction replaces the reviewed list after confirmation.

## Optional local AI settings

**Settings → Optional local AI** shows the configured endpoint/model without contacting the runtime. **Check local runtime** requests only `/api/tags` metadata, with no resume, evidence, or job text and no model downloads. Invalid URLs are blocked and hidden rather than echoing credentials. Update `OLLAMA_BASE_URL` / `OLLAMA_CHAT_MODEL` in `.env` and restart the backend to change them. Deterministic features continue to work when Ollama is unavailable. Only explicitly requested job extraction sends the job description to the local model; intake, evidence verification, and resume drafting do not call AI. Model licensing and actual local model quality still need review before relying on optional model extraction.

## Resume snapshots (Milestone 4 in progress)

The source picker uses the API's current drafting-source checks, not just cached verification flags. Linked archived roles/projects and missing/damaged supporting files prevent selection. **Unavailable sources** explains blocks and links back to review; **Refresh source availability** rechecks after changes outside this view. Failed/loading checks do not fall back to cached flags. Existing selections and wording stay intact, but new snapshots are disabled until selected sources are eligible. This is a point-in-time source check—not section/wording approval or continuous monitoring—and final save still revalidates. Availability checks never verify claims or alter saved versions.

Use **Resumes** to create a targeted resume for a saved job, select verified claims, choose and reorder sections, order bullets within each section, review source notes, and save a draft or approved version. You can edit bullet wording conservatively: the API allows omission of a leading “I” and its auxiliaries, capitalization/spacing changes, and an optional final period. It preserves all other words, signs, comparison operators, currencies, ranges, and technical punctuation (such as `.NET` and `A/B`). New words, reordered claims, changed numbers, tools, and negations are rejected. Only approved bullet variants passing the same check are offered as suggestions. Broader AI paraphrasing remains unimplemented; add and verify new claims in the library first. Working selections, section order, and wording survive page navigation and switching resumes within the same open tab. This is memory-only: refreshing or closing the page clears working edits; they are not written to browser storage, the database, or backups. **Clear working selection** discards only that resume's working selection, not its saved versions. Returning from source review retains wording but never bypasses current verification checks. The editor, source preview, validation bullet numbers, and saved versions share the same section-first document order. **Use version as starting point** restores that version's section order as well as its bullets. **Check sources and wording** displays all detected bullet issues without saving a version. Checks cover stale or archived evidence, duplicate selections, section context, and unsafe wording. Editing the draft hides the old report, and saving always validates current evidence again. Each version captures the profile, evidence, metrics, and role context at creation time. The saved document preview renders a single column from the snapshot's contact details, roles, project names, dates, and bullets; it never fetches current library values. Older snapshots without dates remain supported, and missing end dates are not labeled “Present.” This browser preview is not an exported file or page-count check. Database triggers prevent changes to sealed versions and their bullets. Editing or archiving library records will not alter saved snapshots.

## Document export (Milestone 5 in progress)

Install the current backend requirements and run `alembic upgrade head` after pulling changes. In a saved approved version, choose **Generate DOCX**, then **Download DOCX**. Draft snapshots cannot be exported. A single-column document is generated exclusively from the immutable snapshot; changing or archiving library records will not change its output. Each artifact is stored under `data/exports/` with its version ID, SHA-256 checksum, and text extracted from the generated DOCX. Downloads verify the checksum, and missing or damaged files can be regenerated. Review the extracted text in the UI and inspect the file in Word or LibreOffice. Use **Run ATS readiness check** on a DOCX or PDF export to compare its freshly extracted text against current user-confirmed job requirements. The report distinguishes normalized wording, configured skill aliases, supported-but-missing wording, and absent direct verified evidence. It links supporting sources and reports basic text-order and document-structure checks without predicting an employer score. Verified sources saved in the snapshot remain available as historical support; active verified library evidence can also identify wording gaps. Related matches alone do not count as proof. Rerun reports after changing requirements or aliases. PDF export is available through local LibreOffice: install LibreOffice and optionally set `LIBREOFFICE_PATH` in `.env` to the full `soffice` executable path. The default detector checks PATH and the standard macOS application location. Choose **Generate PDF** to convert in an isolated temporary directory/profile with a 45-second timeout. The API extracts PDF text and checks approved content order before registering the artifact, records page count, and exposes the same checksum-protected download workflow. If LibreOffice is unavailable, DOCX export continues to work. Select **Maximum resume pages** before running a readiness check to compare the PDF's freshly extracted page count with your target. PDF reports check saved text order with whitespace/line-wrap normalization; selection, image-only content, and visual layout remain manual checks. DOCX reports explicitly leave pagination unmeasured rather than using a cached or estimated page count. A real conversion test runs only when LibreOffice is detected; mocked converter tests do not substitute for visually inspecting exports.

## Application tracker (Milestone 6 in progress)

Use **Applications** to create a local record tied to an exact approved resume version for the same job. The tracker copies the employer, role, and posting URL at creation, and fixes the job/version links so later library or posting edits do not change what was tracked. View the saved resume and its exports directly in the detail pane. Update statuses, applied/follow-up dates, and notes; each meaningful update appends a timestamped history event. Setting status to **applied** defaults the applied date to today's UTC date when no date is supplied; dates can be corrected or cleared. History notes are append-only. Creating a record or updating its status never submits anything to a job site. Save edits before changing records. Portable backup export is available in Settings; validated restore is available through the backend CLI into a new directory.

## Portable backups and clean-directory restore

In **Settings**, acknowledge that the archive contains unencrypted personal data and choose **Download backup**. The ZIP contains a consistent SQLite snapshot (including migrations, search indexes, immutable resume versions, and application history), all regular attachment files, and exports referenced by that database snapshot. `manifest.json` records the schema revision, file sizes, and SHA-256 checksums. Runtime configuration, `.env`, dependencies, temporary files, and unregistered export files are excluded. The API rejects missing/corrupt registered assets, symbolic links, invalid paths, integrity-check failures, and archives exceeding 256 MB uncompressed or 2,000 data files. Registered source files must match their saved size and checksum. Damaged original source files or exports must be repaired before a complete backup can be made; generating a new artifact does not repair an older export record. Store archives privately, outside public Git repositories. Restore never replaces existing or active data. With the project virtual environment active, run from `backend`:

```bash
# Validate without restoring (temporary validation files are removed afterward)
python -m app.restore /path/to/resume-backup.zip --check-only

# Restore into a NEW absolute path whose parent already exists
python -m app.restore /path/to/resume-backup.zip --destination /absolute/path/to/new-data
```

Validation checks file paths, entry types, duplicates, limits, hashes, database integrity, foreign keys, resume evidence links, registered source files and their immutable snapshot references, export references, and the exact trusted schema/triggers built from this app's migrations. The backup must have the same schema revision as this app; incompatible revisions are refused rather than silently upgraded. Restore also applies the current source-wording rules to saved bullets; older backups with broader wording edits may be refused even when the schema matches. Keep the original data rather than bypassing these checks. Checksums detect damage, not authorship: use only backups you created and trust. After successful restore, stop the API, set `DATA_DIR` in `.env` to the new absolute directory, clear `DATABASE_URL`, and restart. Review the restored data and exports before retiring the original directory. No browser backup upload or live-database replacement is enabled.

## Checks

```bash
source .venv/bin/activate
cd backend
ruff check .
mypy app
pytest
```

```bash
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

### Real-browser core workflow

```bash
cd frontend
npm install
npx playwright install chromium  # first-time browser setup
npm run test:e2e
```

Playwright starts separate localhost servers on ports **8876** (API) and **5174** (web), refuses to reuse existing servers, and creates a fresh temporary SQLite database/data directory for each run. The backend launcher sets isolation variables before importing app settings, so your `.env` database and personal data are not used. The test uses fictional records and blocks browser requests outside those two test origins. It covers profile entry, text-file intake, inline experience/project creation (including cancellation and failure recovery), explicit draft evidence creation, metric entry, supporting-file upload failure/retry and checksum-preserving download, verification invalidation, archive recovery, reviewed job requirements, rejection of an unsupported metric edit, approved resume snapshots, checksum-verified DOCX download, ATS readiness, application status history, and dashboard navigation. A second browser test exercises experience/project/skill creation, update-without-duplicate, pending-write locks, and failed save/archive recovery. A third test covers API-owned source availability, archived parent context, retry after failed checks, preserved working wording, and final validation rejecting a source that changed after a positive preview. PDF conversion is not covered by these browser tests.

The default Python interpreter is the repository's `.venv/bin/python`; set `E2E_PYTHON` if your virtual environment is elsewhere. Traces/screenshots on failure are saved under Git-ignored `frontend/test-results/`. `npm test` remains the lightweight unit/component suite; `npm run test:e2e` is separate.
