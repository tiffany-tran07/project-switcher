# Resume Tailor

A local-first resume tailoring app. The career evidence library, job matching, and an initial evidence-backed resume snapshot workflow are available. See [BUILD_GUIDE.md](BUILD_GUIDE.md).

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

Open <http://127.0.0.1:5173>. The API is at <http://127.0.0.1:8000/health>; it returns `{"status":"ok"}` after migration. The local database and future attachments/exports live under `data/`, which Git ignores. Set `DATA_DIR` in `.env` to an absolute path to move them. If you set `DATABASE_URL`, use a SQLite URL and keep it inside your chosen local data directory.

## Dashboard

The app opens with counts and recent jobs, resumes, and applications, plus evidence needing review and follow-ups due on or before today's UTC date. Rejected and withdrawn applications are excluded from due reminders. A verified evidence record whose source context has been archived is not counted as ready for drafting. Each list shows at most five records while totals include all non-archived records. Select a row to open that specific record; the dashboard never sends follow-up messages automatically.

## Existing resume intake

Open **Intake** to select an existing `.docx` or UTF-8 `.txt` resume, or paste its text. File previews are processed by the configured backend (localhost by default), without AI calls, saved uploads, database records, or automatic verification. Check extracted dates, metrics, symbols, and table order. To save an accomplishment, highlight its exact text, choose **Use highlighted text as a claim**, link an active experience or project, and choose **Save as draft evidence**. The API rejects invented excerpts and matching active claims already saved for the same context. Only the selected claim, its context, source name, reviewed-text checksum, and optional supporting notes are stored—not the full resume. Every imported claim remains draft until you explicitly review and verify it in Evidence. DOCX headers, footers, text boxes, images, and nested tables may be omitted; table cells are shown in physical document order. PDF intake is not available yet—paste text from your PDF instead. Previews disappear when leaving the page.

Limits: 5 MB upload, 32 MB expanded DOCX, 8 MB per XML part, 500 package entries, and 100,000 extracted characters. Invalid packages, macro-enabled content, embedded objects, XML entity declarations, and unsupported entry types are rejected. A resume is a starting point for review, not independent proof of its claims.

## Career library

Use the sidebar to add experiences and projects, then create skills with optional aliases. Add one evidence item for each claim, link it to an experience or project, and record where you can verify it. Metrics have their own source notes. Save the item before clicking **Verify**. Editing a claim, its context, a linked skill, or a metric returns it to draft and clears approval on its bullet variants.

Search checks experiences, projects, skills, aliases, and evidence through SQLite FTS5. **Export JSON** downloads the complete career library, including archived records. The API schema is available at <http://127.0.0.1:8000/docs>.

## Job workspace

Use **Jobs** in the sidebar to paste a description. The original posting remains unchanged; save a new job to replace its text. Deterministic extraction produces draft requirements with cited posting spans and suggested priorities. Edit, add, remove, confirm, and save requirements before reviewing matches. Changing a requirement's text removes its confirmation and citation; review and confirm it again. Matching considers only active verified evidence and distinguishes direct, related, and unsupported requirements. Related matches are lexical hints, not proof. Select a match to open its source evidence. You can optionally set `OLLAMA_CHAT_MODEL` to an installed Ollama model and use **Try local Ollama**; the API restricts Ollama to localhost, rejects unsupported citations, and falls back to deterministic extraction if Ollama is unavailable. Re-extraction replaces the reviewed list after confirmation.

## Resume snapshots (Milestone 4 in progress)

Use **Resumes** to create a targeted resume for a saved job, select verified claims, choose and reorder sections, order bullets within each section, review source notes, and save a draft or approved version. You can edit bullet wording conservatively: the API allows omission of a leading “I” and its auxiliaries, capitalization/spacing changes, and an optional final period. It preserves all other words, signs, comparison operators, currencies, ranges, and technical punctuation (such as `.NET` and `A/B`). New words, reordered claims, changed numbers, tools, and negations are rejected. Only approved bullet variants passing the same check are offered as suggestions. Broader AI paraphrasing remains unimplemented; add and verify new claims in the library first. The editor, source preview, validation bullet numbers, and saved versions share the same section-first document order. **Use version as starting point** restores that version's section order as well as its bullets. **Check sources and wording** displays all detected bullet issues without saving a version. Checks cover stale or archived evidence, duplicate selections, section context, and unsafe wording. Editing the draft hides the old report, and saving always validates current evidence again. Each version captures the profile, evidence, metrics, and role context at creation time. The saved document preview renders a single column from the snapshot's contact details, roles, project names, dates, and bullets; it never fetches current library values. Older snapshots without dates remain supported, and missing end dates are not labeled “Present.” This browser preview is not an exported file or page-count check. Database triggers prevent changes to sealed versions and their bullets. Editing or archiving library records will not alter saved snapshots.

## Document export (Milestone 5 in progress)

Install the current backend requirements and run `alembic upgrade head` after pulling changes. In a saved approved version, choose **Generate DOCX**, then **Download DOCX**. Draft snapshots cannot be exported. A single-column document is generated exclusively from the immutable snapshot; changing or archiving library records will not change its output. Each artifact is stored under `data/exports/` with its version ID, SHA-256 checksum, and text extracted from the generated DOCX. Downloads verify the checksum, and missing or damaged files can be regenerated. Review the extracted text in the UI and inspect the file in Word or LibreOffice. Use **Run ATS readiness check** on a DOCX or PDF export to compare its freshly extracted text against current user-confirmed job requirements. The report distinguishes normalized wording, configured skill aliases, supported-but-missing wording, and absent direct verified evidence. It links supporting sources and reports basic text-order and document-structure checks without predicting an employer score. Verified sources saved in the snapshot remain available as historical support; active verified library evidence can also identify wording gaps. Related matches alone do not count as proof. Rerun reports after changing requirements or aliases. PDF export is available through local LibreOffice: install LibreOffice and optionally set `LIBREOFFICE_PATH` in `.env` to the full `soffice` executable path. The default detector checks PATH and the standard macOS application location. Choose **Generate PDF** to convert in an isolated temporary directory/profile with a 45-second timeout. The API extracts PDF text and checks approved content order before registering the artifact, records page count, and exposes the same checksum-protected download workflow. If LibreOffice is unavailable, DOCX export continues to work. Select **Maximum resume pages** before running a readiness check to compare the PDF's freshly extracted page count with your target. PDF reports check saved text order with whitespace/line-wrap normalization; selection, image-only content, and visual layout remain manual checks. DOCX reports explicitly leave pagination unmeasured rather than using a cached or estimated page count. A real conversion test runs only when LibreOffice is detected; mocked converter tests do not substitute for visually inspecting exports.

## Application tracker (Milestone 6 in progress)

Use **Applications** to create a local record tied to an exact approved resume version for the same job. The tracker copies the employer, role, and posting URL at creation, and fixes the job/version links so later library or posting edits do not change what was tracked. View the saved resume and its exports directly in the detail pane. Update statuses, applied/follow-up dates, and notes; each meaningful update appends a timestamped history event. Setting status to **applied** defaults the applied date to today's UTC date when no date is supplied; dates can be corrected or cleared. History notes are append-only. Creating a record or updating its status never submits anything to a job site. Save edits before changing records. Portable backup export is available in Settings; validated restore is available through the backend CLI into a new directory.

## Portable backups and clean-directory restore

In **Settings**, acknowledge that the archive contains unencrypted personal data and choose **Download backup**. The ZIP contains a consistent SQLite snapshot (including migrations, search indexes, immutable resume versions, and application history), all regular attachment files, and exports referenced by that database snapshot. `manifest.json` records the schema revision, file sizes, and SHA-256 checksums. Runtime configuration, `.env`, dependencies, temporary files, and unregistered export files are excluded. The API rejects missing/corrupt registered assets, symbolic links, invalid paths, integrity-check failures, and archives exceeding 256 MB uncompressed or 2,000 data files. Damaged original exports must be repaired before a complete backup can be made; generating a new artifact does not repair an older export record. Store archives privately, outside public Git repositories. Restore never replaces existing or active data. With the project virtual environment active, run from `backend`:

```bash
# Validate without restoring (temporary validation files are removed afterward)
python -m app.restore /path/to/resume-backup.zip --check-only

# Restore into a NEW absolute path whose parent already exists
python -m app.restore /path/to/resume-backup.zip --destination /absolute/path/to/new-data
```

Validation checks file paths, entry types, duplicates, limits, hashes, database integrity, foreign keys, resume evidence links, export references, and the exact trusted schema/triggers built from this app's migrations. The backup must have the same schema revision as this app; incompatible revisions are refused rather than silently upgraded. Restore also applies the current source-wording rules to saved bullets; older backups with broader wording edits may be refused even when the schema matches. Keep the original data rather than bypassing these checks. Checksums detect damage, not authorship: use only backups you created and trust. After successful restore, stop the API, set `DATA_DIR` in `.env` to the new absolute directory, clear `DATABASE_URL`, and restart. Review the restored data and exports before retiring the original directory. No browser backup upload or live-database replacement is enabled.

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
