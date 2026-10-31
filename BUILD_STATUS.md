# Build status

## Current phase

**MVP integration and hardening across Milestones 1–6.** The core workflow is implemented and exercised with automated tests, including an isolated Chromium workflow. This is not a declaration that every milestone acceptance check is complete. Semantic search (7) and browser application assistance (8) have not started.

| Milestone | Implemented core | Remaining validation / limitations |
| --- | --- | --- |
| 1 — Foundation | Local React/FastAPI startup, SQLite migrations, lint/type/test runners | Browser tests start a fresh isolated installation; normal use remains localhost-only. |
| 2 — Evidence library | Profile, roles, projects, skills/aliases, evidence, metrics, variants, archive API, search, JSON export | Supporting-document upload UI is not implemented. Claims still require manual truth/source review. |
| 3 — Jobs and matching | Pasted jobs, editable/confirmed requirements, deterministic and optional local extraction, source-linked matches and gaps | Local-model behavior is tested with fixtures/local HTTP servers, not a real installed model. Related matches are not proof. |
| 4 — Resume drafting | Verified-only selection, sections/order, conservative wording, source validation, immutable snapshots/history | No broad AI paraphrasing. Working selections are tab-memory only; reload clears them. |
| 5 — Export and ATS readiness | DOCX and optional LibreOffice PDF export, checksums, actual-file text extraction, keyword/support gaps, PDF page targets | **Real LibreOffice conversion and visual inspection are still pending on this machine.** The optional real-conversion test is skipped while LibreOffice is absent. |
| 6 — Tracking and backup | Exact approved-version links, application history/follow-ups, portable backup export, validated clean-directory CLI restore | Restore is deliberately not a live-database/browser replacement. Backups are unencrypted. |
| 7 — Semantic search | Not started | Establish real lexical-search misses and fixtures before adding embeddings. |
| 8 — Application assistant | Not started | Playwright currently tests this app only; it does not fill or submit external job forms. |

## Current UX increment

Working resume selections, section order, and wording survive page navigation and switching between resumes in the same open tab. They are kept in React memory only—not localStorage, sessionStorage, the database, or backups. Source state is not cached as verification: saving a version still rechecks current evidence. An unavailable/rejected source does not erase wording or become usable merely because a working selection was restored.

## Next acceptance checks

1. Exercise Intake and the evidence workflow with a real, user-reviewed resume. DOCX and UTF-8 text are supported; PDF input currently requires pasted text.
2. With LibreOffice installed, run the optional real PDF-conversion test and inspect representative DOCX/PDF files in a document viewer. Confirm text order, dates, symbols, fonts, and page target. Automated fixtures do not replace this check.
3. Optionally evaluate an installed, appropriately licensed Ollama model against real job descriptions. Core features do not depend on it, and no cloud AI is required.
4. Collect usability issues and actual matching misses before moving to Milestone 7.

See `README.md` for setup, test commands, backup/restore precautions, and feature limitations. Use high reasoning for security, schema changes, evidence-policy changes, and architecture review; medium is suitable for ordinary UI increments. Internet access may be useful for official tooling documentation or installation, but personal resumes and career data should remain local.
