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

## Career library

Use the sidebar to add experiences and projects, then create skills with optional aliases. Add one evidence item for each claim, link it to an experience or project, and record where you can verify it. Metrics have their own source notes. Save the item before clicking **Verify**. Editing a claim, its context, a linked skill, or a metric returns it to draft and clears approval on its bullet variants.

Search checks experiences, projects, skills, aliases, and evidence through SQLite FTS5. **Export JSON** downloads the complete career library, including archived records. The API schema is available at <http://127.0.0.1:8000/docs>.

## Job workspace

Use **Jobs** in the sidebar to paste a description. The original posting remains unchanged; save a new job to replace its text. Deterministic extraction produces draft requirements with cited posting spans and suggested priorities. Edit, add, remove, confirm, and save requirements before reviewing matches. Changing a requirement's text removes its confirmation and citation; review and confirm it again. Matching considers only active verified evidence and distinguishes direct, related, and unsupported requirements. Related matches are lexical hints, not proof. Select a match to open its source evidence. You can optionally set `OLLAMA_CHAT_MODEL` to an installed Ollama model and use **Try local Ollama**; the API restricts Ollama to localhost, rejects unsupported citations, and falls back to deterministic extraction if Ollama is unavailable. Re-extraction replaces the reviewed list after confirmation.

## Resume snapshots (Milestone 4 in progress)

Use **Resumes** to create a targeted resume for a saved job, select verified claims, choose sections, order bullets, review source notes, and save a draft or approved version. You can edit bullet wording conservatively: the API allows removal of grammatical filler and punctuation changes, but rejects new words, reordered claims, changed numbers, tools, and negations. Only approved bullet variants passing the same check are offered as suggestions. Broader AI paraphrasing remains unimplemented; add and verify new claims in the library first. **Check sources and wording** displays all detected bullet issues without saving a version. Checks cover stale or archived evidence, duplicate selections, section context, and unsafe wording. Editing the draft hides the old report, and saving always validates current evidence again. Each version captures the profile, evidence, metrics, and role context at creation time. Database triggers prevent changes to sealed versions and their bullets. Editing or archiving library records will not alter saved snapshots.

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
