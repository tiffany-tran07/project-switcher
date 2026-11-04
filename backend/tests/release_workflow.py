"""Connected fictional release drill. Invoked only by scripts/release_check.py.

Keep app imports below require_isolation: default settings must never open user data.
"""

import json
import os
import sqlite3
import sys
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
MARKER = "resume-release-check-v1"


class WorkflowFailed(Exception):
    pass


def require_isolation(stage: str) -> tuple[Path, Path, Path]:
    value = os.environ.get("RELEASE_CHECK_ROOT")
    if not value:
        raise WorkflowFailed("Use scripts/release_check.py; isolation marker is required")
    root = Path(value).absolute()
    if root != root.resolve() or (root / ".release-check").read_text() != MARKER:
        raise WorkflowFailed("Invalid isolation root")
    data = root / ("source" if stage == "create" else "restored")
    expected_url = f"sqlite:///{data / 'resume.db'}" if stage == "create" else ""
    if os.environ.get("DATA_DIR") != str(data) or os.environ.get("DATABASE_URL") != expected_url:
        raise WorkflowFailed("Refusing settings outside the disposable data directory")
    if data.is_symlink() or data.resolve() != data:
        raise WorkflowFailed("Disposable data path cannot use symlinks")
    if stage == "create" and (data.exists() or (root / "expected.json").exists()):
        raise WorkflowFailed("Source installation must be new")
    if stage == "verify" and (
        not (data / "resume.db").is_file()
        or (data / "resume.db").is_symlink()
        or (data / "resume.db").resolve() != data / "resume.db"
    ):
        raise WorkflowFailed("Restored database is missing or uses symlinks")
    artifacts = Path(os.environ["RELEASE_CHECK_ARTIFACTS"]).absolute()
    if artifacts != artifacts.resolve() or not artifacts.is_dir():
        raise WorkflowFailed("Artifact directory must already exist without symlinks")
    if stage == "create" and any(artifacts.iterdir()):
        raise WorkflowFailed("Artifact directory must be empty")
    return root, data, artifacts


def json_file(path: Path, value: Any) -> None:
    with path.open("x") as output:
        json.dump(value, output, indent=2, ensure_ascii=False)


def blob_file(path: Path, value: bytes) -> None:
    with path.open("xb") as output:
        output.write(value)


def api(client: Any, method: str, path: str, *, status: int = 200, **kwargs: Any) -> Any:
    response = client.request(method, "/api/v1" + path, **kwargs)
    if response.status_code != status:
        raise WorkflowFailed(f"{method} {path}: expected {status}, got {response.status_code}")
    return response.json() if response.content else None


def capture(
    client: Any, resume_id: str, evidence_ids: list[str], version_id: str, export_ids: list[str]
) -> dict[str, Any]:
    paths = [
        "/profile",
        "/experiences?include_archived=true",
        "/projects?include_archived=true",
        "/skills?include_archived=true",
        "/evidence?include_archived=true",
        "/jobs",
        "/resumes",
        f"/resumes/{resume_id}/versions",
        "/applications",
        "/library/search?q=cpp",
        "/library/export",
        f"/resume-versions/{version_id}/exports",
    ]
    paths.extend(f"/evidence/{id}/attachments" for id in evidence_ids)
    result = {path: api(client, "GET", path) for path in paths}
    # JSON export's generated timestamp is not persisted application state.
    result["/library/export"].pop("exported_at", None)
    result["dashboard_counts"] = api(client, "GET", "/dashboard")["counts"]
    result["ats"] = {
        id: api(
            client,
            "POST",
            f"/resume-versions/{version_id}/ats",
            json={"export_id": id, "page_target": 1},
        )
        for id in export_ids
    }
    return result


def create(root: Path, data: Path, artifacts: Path) -> None:
    from acceptance_documents import acceptance_version
    from alembic import command
    from alembic.config import Config
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.db import engine
    from app.documents import render_docx
    from app.main import app
    from app.pdf import convert_pdf

    if settings.resolved_data_dir != data or str(engine.url.database) != str(data / "resume.db"):
        raise WorkflowFailed("App settings did not adopt the disposable installation")
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    command.upgrade(config, "head")
    fixture = acceptance_version()
    original_docx, expected_text = render_docx(fixture)
    input_pdf, _, input_pages = convert_pdf(original_docx, expected_text)
    blob_file(artifacts / "fictional-input.pdf", input_pdf)
    claims = [fixture.bullets[0].text, fixture.bullets[-1].text]
    proof = b"Synthetic release benchmark log; no real employment claims.\n"
    with TestClient(app) as client:
        if client.get("/health").json() != {"status": "ok"}:
            raise WorkflowFailed("New installation health failed")
        preview = api(
            client,
            "POST",
            "/resume-intake/preview?filename=fictional-input.pdf",
            content=input_pdf,
            headers={"Content-Type": "application/octet-stream"},
        )
        if api(client, "GET", "/evidence") or any(claim not in preview["text"] for claim in claims):
            raise WorkflowFailed("Intake must preserve exact text and create no evidence")
        profile = {
            "name": "Fictional Release Candidate",
            "email": "release@example.test",
            "phone": "555-0100",
            "location": "Synthetic fixture",
            "links": ["https://portfolio.example.test/release"],
        }
        api(client, "PUT", "/profile", json=profile)
        experience = api(
            client,
            "POST",
            "/experiences",
            status=201,
            json={
                "organization": "Fictional Systems",
                "title": "Engineer",
                "start_date": "2020-01-01",
                "end_date": "2023-06-30",
                "location": "Remote",
            },
        )
        project = api(
            client,
            "POST",
            "/projects",
            status=201,
            json={
                "name": "Fictional Atlas",
                "experience_id": experience["id"],
                "start_date": "2021-02-01",
                "end_date": "2022-03-31",
            },
        )
        skills = [
            api(client, "POST", "/skills", status=201, json={"name": name, "aliases": aliases})
            for name, aliases in [
                ("C++", ["cpp"]),
                ("Python", ["Python3"]),
                ("PostgreSQL", ["Postgres"]),
            ]
        ]
        evidence = []
        for index, claim in enumerate(claims):
            row = api(
                client,
                "POST",
                "/resume-intake/drafts",
                status=201,
                json={
                    "source_text": preview["text"],
                    "source_name": preview["filename"],
                    "claim": claim,
                    "experience_id": experience["id"] if index == 0 else None,
                    "project_id": project["id"] if index else None,
                    "source_note": "Synthetic release drill, manually reviewed fixture only",
                },
            )
            if row["state"] != "draft" or row["verified_at"] is not None:
                raise WorkflowFailed("Intake unexpectedly verified a fixture")
            evidence.append(row)
            api(
                client,
                "PATCH",
                f"/evidence/{row['id']}",
                json={
                    "skill_ids": [
                        skill["id"] for skill in (skills[:1] if index == 0 else skills[1:])
                    ]
                },
            )
        first = f"/evidence/{evidence[0]['id']}"
        api(
            client,
            "POST",
            f"{first}/metrics",
            status=201,
            json={
                "name": "Latency reduction",
                "value": "30",
                "unit": "%",
                "context": "Fictional benchmark",
                "source_note": "Synthetic release log",
            },
        )
        attachment = api(
            client,
            "POST",
            f"{first}/attachments?filename=fictional-proof.txt",
            status=201,
            content=proof,
            headers={"Content-Type": "application/octet-stream"},
        )
        job = api(
            client,
            "POST",
            "/jobs",
            status=201,
            json={
                "company": "Fictional hiring team",
                "title": "Release fixture engineer",
                "raw_description": "Required: C++, Python, and PostgreSQL. "
                "Fictional release fixture.",
            },
        )
        req_path = f"/jobs/{job['id']}/requirements"
        requirements = api(
            client,
            "PATCH",
            req_path,
            json={
                "requirements": [
                    {"text": text, "kind": "skill", "priority": "required"}
                    for text in ("C++", "Python", "PostgreSQL")
                ]
            },
        )
        api(
            client,
            "PATCH",
            req_path,
            json={"requirements": [{**row, "confirmed": True} for row in requirements]},
        )
        resume = api(
            client,
            "POST",
            "/resumes",
            status=201,
            json={"job_id": job["id"], "name": "Fictional release resume"},
        )
        sections = [
            {"heading": heading, "bullets": [{"evidence_id": row["id"], "text": row["claim"]}]}
            for heading, row in zip(("Experience", "Projects"), evidence, strict=True)
        ]
        report = api(
            client, "POST", f"/resumes/{resume['id']}/validate", json={"sections": sections}
        )
        if report["valid"]:
            raise WorkflowFailed("Draft evidence unexpectedly passed source validation")
        for row in evidence:
            # Only these explicitly synthetic fixture claims are verified, never user data.
            api(client, "PATCH", f"/evidence/{row['id']}", json={"state": "verified"})
        api(
            client,
            "POST",
            f"{first}/bullets",
            status=201,
            json={"text": claims[0], "approved": True},
        )
        unsafe = [
            {
                "heading": "Experience",
                "bullets": [
                    {"evidence_id": evidence[0]["id"], "text": claims[0].replace("≥30%", "≥40%")}
                ],
            }
        ]
        api(
            client,
            "POST",
            f"/resumes/{resume['id']}/draft",
            status=422,
            json={"sections": unsafe, "approve": True},
        )
        if api(client, "GET", f"/resumes/{resume['id']}/versions"):
            raise WorkflowFailed("Unsafe wording created a snapshot")
        draft = api(
            client,
            "POST",
            f"/resumes/{resume['id']}/draft",
            status=201,
            json={"sections": sections},
        )
        approved = api(
            client,
            "POST",
            f"/resumes/{resume['id']}/draft",
            status=201,
            json={"sections": sections, "approve": True},
        )
        api(
            client,
            "POST",
            f"/resume-versions/{draft['id']}/export",
            status=422,
            json={"format": "pdf"},
        )
        exports = []
        checksums = {}
        for format in ("docx", "pdf"):
            artifact = api(
                client,
                "POST",
                f"/resume-versions/{approved['id']}/export",
                status=201,
                json={"format": format},
            )
            response = client.get(f"/api/v1/exports/{artifact['id']}/download")
            digest = sha256(response.content).hexdigest()
            if response.status_code != 200 or digest != artifact["checksum"]:
                raise WorkflowFailed("Export download checksum failed")
            blob_file(artifacts / f"fictional-resume.{format}", response.content)
            checksums[artifact["id"]] = digest
            exports.append(artifact["id"])
            ats = api(
                client,
                "POST",
                f"/resume-versions/{approved['id']}/ats",
                json={"export_id": artifact["id"], "page_target": 1},
            )
            formatting = {row["name"]: row["status"] for row in ats["formatting"]}
            if formatting["text_order"] != "passed" or (
                format == "pdf" and formatting["page_target"] != "passed"
            ):
                raise WorkflowFailed("Actual-file text/order/page checks failed")
            if any(row["status"] != "present_exact" for row in ats["requirements"]):
                raise WorkflowFailed("Confirmed fixture requirements missing from export")
        application = api(
            client,
            "POST",
            "/applications",
            status=201,
            json={
                "job_id": job["id"],
                "resume_version_id": approved["id"],
                "notes": "Synthetic drill only; no submission",
            },
        )
        application_path = f"/applications/{application['id']}"
        api(
            client,
            "PATCH",
            application_path,
            json={
                "status": "applied",
                "applied_date": "2026-01-15",
                "follow_up_date": "2099-01-01",
                "event_note": "Fictional history entry; not an external submission",
            },
        )
        api(client, "PATCH", application_path, json={"status": "interview"})
        api(
            client,
            "POST",
            f"{application_path}/events",
            status=201,
            json={"note": "Synthetic recovery fixture note"},
        )
        archived = api(
            client,
            "POST",
            "/resume-intake/drafts",
            status=201,
            json={
                "source_text": preview["text"],
                "source_name": preview["filename"],
                "claim": fixture.bullets[1].text,
                "experience_id": experience["id"],
            },
        )
        api(client, "PATCH", f"/evidence/{archived['id']}", json={"archived": True})
        api(client, "PUT", "/profile", json={**profile, "name": "Changed fictional live profile"})
        api(
            client, "PATCH", first, json={"claim": "Changed fictional library claim after approval"}
        )
        api(client, "PATCH", f"/jobs/{job['id']}", json={"title": "Changed fictional live job"})
        if api(client, "GET", f"/resume-versions/{approved['id']}") != approved:
            raise WorkflowFailed("Live edits changed approved history")
        if api(client, "GET", application_path)["title"] != "Release fixture engineer":
            raise WorkflowFailed("Application source link was not frozen")
        expected = {
            "fixture": MARKER,
            "resume_id": resume["id"],
            "evidence_ids": [row["id"] for row in evidence],
            "version_id": approved["id"],
            "export_ids": exports,
            "checksums": checksums,
            "attachment_id": attachment["id"],
            "attachment_sha256": sha256(proof).hexdigest(),
        }
        expected["records"] = capture(
            client, resume["id"], expected["evidence_ids"], approved["id"], exports
        )
        (data / ".env").write_text("FICTIONAL_NOT_FOR_BACKUP=example\n")
        backup = client.post("/api/v1/backup/export", json={"acknowledge_personal_data": True})
        if backup.status_code != 200:
            raise WorkflowFailed("Backup export failed")
        blob_file(artifacts / "fictional-backup.zip", backup.content)
        json_file(root / "expected.json", expected)
        json_file(
            artifacts / "source-checks.json",
            {
                "input_pages": input_pages,
                "exports": checksums,
                "attachment_sha256": expected["attachment_sha256"],
                "intake_unverified": True,
                "unsafe_wording_rejected": True,
                "historical_versions_unchanged": True,
            },
        )
    engine.dispose()
    print("workflow created")


def verify(root: Path, data: Path, artifacts: Path) -> None:
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.db import engine
    from app.main import app

    if settings.resolved_data_dir != data or str(engine.url.database) != str(data / "resume.db"):
        raise WorkflowFailed("Fresh app did not use DATA_DIR with DATABASE_URL cleared")
    expected = json.loads((root / "expected.json").read_text())
    if expected.get("fixture") != MARKER:
        raise WorkflowFailed("Expected fictional fixture marker is missing")
    with TestClient(app) as client:
        if client.get("/health").json() != {"status": "ok"}:
            raise WorkflowFailed("Restored installation health failed")
        restored = capture(
            client,
            expected["resume_id"],
            expected["evidence_ids"],
            expected["version_id"],
            expected["export_ids"],
        )
        if restored != expected["records"]:
            different = [key for key in restored if restored[key] != expected["records"].get(key)]
            raise WorkflowFailed(f"Restored records differ: {different}")
        for id, checksum in expected["checksums"].items():
            response = client.get(f"/api/v1/exports/{id}/download")
            if response.status_code != 200 or sha256(response.content).hexdigest() != checksum:
                raise WorkflowFailed("Restored export bytes differ")
        response = client.get(f"/api/v1/attachments/{expected['attachment_id']}/download")
        if (
            response.status_code != 200
            or sha256(response.content).hexdigest() != expected["attachment_sha256"]
        ):
            raise WorkflowFailed("Restored supporting attachment differs")
        with closing(sqlite3.connect(data / "resume.db")) as connection:
            for statement, parameters in [
                (
                    "UPDATE resume_versions SET template = ? WHERE id = ?",
                    ("changed", expected["version_id"]),
                ),
                ("UPDATE application_events SET note = ?", ("changed",)),
                ("DELETE FROM attachments", ()),
            ]:
                try:
                    connection.execute(statement, parameters)
                except sqlite3.IntegrityError:
                    connection.rollback()
                else:
                    connection.rollback()
                    raise WorkflowFailed(
                        "Restored history integrity trigger did not reject a mutation"
                    )
        if (
            capture(
                client,
                expected["resume_id"],
                expected["evidence_ids"],
                expected["version_id"],
                expected["export_ids"],
            )
            != restored
        ):
            raise WorkflowFailed("Integrity probes changed restored records")
    engine.dispose()
    json_file(
        artifacts / "result.json",
        {
            "status": "passed",
            "fictional_data_only": True,
            "fresh_restored_process": True,
            "database_url_cleared": True,
            "record_collections_compared": len(restored),
            "export_sha256_unchanged": True,
            "attachment_sha256_unchanged": True,
            "ats_reports_unchanged": True,
            "history_triggers_enforced": True,
        },
    )
    print("restored workflow verified")


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"create", "verify"}:
        print("Invoke through scripts/release_check.py", file=sys.stderr)
        return 2
    try:
        stage = sys.argv[1]
        root, data, artifacts = require_isolation(stage)
        sys.path.insert(0, str(BACKEND))
        (create if stage == "create" else verify)(root, data, artifacts)
    except Exception as exc:
        print(f"Fictional workflow refused/failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
