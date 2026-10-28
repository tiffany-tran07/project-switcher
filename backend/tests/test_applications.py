from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Application

pytest_plugins = ("test_library", "test_exports")


def create_payload(client: TestClient, snapshot: dict[str, Any]) -> dict[str, str]:
    resume = client.get(f"/api/v1/resumes/{snapshot['approved']['resume_id']}").json()
    return {"job_id": resume["job_id"], "resume_version_id": snapshot["approved"]["id"]}


def test_tracker_links_exact_version_and_records_history(
    export_client: TestClient,
    snapshot: dict[str, Any],
) -> None:
    client = export_client
    payload = create_payload(client, snapshot)
    client.patch(f"/api/v1/jobs/{payload['job_id']}", json={"company": "Example"})
    created = client.post(
        "/api/v1/applications", json={**payload, "notes": "Preparing application"}
    )
    assert created.status_code == 201
    row = created.json()
    path = f"/api/v1/applications/{row['id']}"
    assert row["status"] == "planned"
    assert row["applied_date"] is None
    assert row["resume_version_id"] == snapshot["approved"]["id"]
    assert row["title"] == "Target role"
    assert row["events"][0]["event_type"] == "created"
    assert row["events"][0]["created_at"].endswith("Z")
    assert "no external submission" in row["events"][0]["note"]
    updated = client.patch(
        path,
        json={
            "status": "applied",
            "event_note": "Submitted manually on employer site",
            "follow_up_date": "2026-12-01",
            "notes": "Sent referral email",
        },
    ).json()
    assert updated["applied_date"] == datetime.now(UTC).date().isoformat()
    assert updated["follow_up_date"] == "2026-12-01"
    assert len(updated["events"]) == 2
    assert updated["events"][1]["previous_status"] == "planned"
    assert updated["events"][1]["status"] == "applied"
    assert updated["events"][1]["note"] == "Submitted manually on employer site"
    assert len(client.patch(path, json={"status": "applied"}).json()["events"]) == 2
    interview = client.patch(path, json={"status": "interview"}).json()
    assert interview["applied_date"] == updated["applied_date"]
    assert interview["events"][-1]["previous_status"] == "applied"
    note = client.post(f"{path}/events", json={"note": "Recruiter call on Friday"}).json()
    assert note["events"][-1]["event_type"] == "note"
    assert note["events"][-1]["note"] == "Recruiter call on Friday"
    cleared = client.patch(path, json={"follow_up_date": None, "applied_date": "2026-01-12"}).json()
    assert cleared["follow_up_date"] is None
    assert cleared["applied_date"] == "2026-01-12"
    assert client.get("/api/v1/applications?status=interview").json()[0]["id"] == row["id"]
    assert client.get("/api/v1/applications?status=rejected").json() == []
    # Job edits, current library changes, and later versions must not relink this record.
    client.patch(
        f"/api/v1/jobs/{payload['job_id']}",
        json={"company": "Renamed company", "title": "Renamed role"},
    )
    after = client.get(path).json()
    assert after["company"] == "Example"
    assert after["title"] == "Target role"
    assert after["resume_version_id"] == payload["resume_version_id"]
    assert (
        client.get(f"/api/v1/resume-versions/{payload['resume_version_id']}").json()
        == snapshot["approved"]
    )


def test_tracker_rejects_wrong_job_draft_and_immutable_link_changes(
    export_client: TestClient,
    snapshot: dict[str, Any],
) -> None:
    client = export_client
    payload = create_payload(client, snapshot)
    assert (
        client.post(
            "/api/v1/applications", json={**payload, "resume_version_id": snapshot["draft"]["id"]}
        ).status_code
        == 422
    )
    other = client.post(
        "/api/v1/jobs",
        json={"title": "Other", "raw_description": "A different job posting with Python."},
    ).json()
    assert (
        client.post("/api/v1/applications", json={**payload, "job_id": other["id"]}).status_code
        == 422
    )
    assert (
        client.post("/api/v1/applications", json={**payload, "job_id": "missing"}).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/applications", json={**payload, "resume_version_id": "missing"}
        ).status_code
        == 404
    )
    row = client.post("/api/v1/applications", json=payload).json()
    path = f"/api/v1/applications/{row['id']}"
    for invalid in (
        {"resume_version_id": snapshot["draft"]["id"]},
        {"job_id": other["id"]},
        {"status": "invalid"},
        {"status": None},
        {"notes": None},
        {"follow_up_date": "bad"},
    ):
        assert client.patch(path, json=invalid).status_code == 422
    assert client.post(f"{path}/events", json={"note": "  "}).status_code == 422
    assert client.get(path).json() == row
    assert client.get("/api/v1/applications/missing").status_code == 404
    assert client.patch("/api/v1/applications/missing", json={"notes": "New"}).status_code == 404
    assert (
        client.post("/api/v1/applications/missing/events", json={"note": "New"}).status_code == 404
    )
    assert client.get("/api/v1/applications?status=bad").status_code == 422


def test_explicit_application_dates_and_note_only_updates(
    export_client: TestClient,
    snapshot: dict[str, Any],
) -> None:
    client = export_client
    payload = create_payload(client, snapshot)
    created = client.post(
        "/api/v1/applications",
        json={
            **payload,
            "status": "applied",
            "applied_date": "2026-01-15",
        },
    ).json()
    assert created["applied_date"] == "2026-01-15"
    path = f"/api/v1/applications/{created['id']}"
    row = client.patch(path, json={"event_note": "Followed up by email"}).json()
    assert row["status"] == "applied"
    assert row["events"][-1]["event_type"] == "note"
    assert row["events"][-1]["note"] == "Followed up by email"
    assert row["applied_date"] == "2026-01-15"
    assert client.patch(path, json={"applied_date": None}).json()["applied_date"] is None


def test_database_guards_application_links_and_append_only_events(
    export_client: TestClient,
    snapshot: dict[str, Any],
) -> None:
    client = export_client
    payload = create_payload(client, snapshot)
    row = client.post("/api/v1/applications", json=payload).json()
    engine = create_engine(settings.resolved_database_url)
    try:
        with Session(engine) as session:
            with pytest.raises(IntegrityError):
                session.add(
                    Application(
                        job_id=payload["job_id"],
                        resume_version_id=snapshot["draft"]["id"],
                        company="Example",
                        title="Role",
                    )
                )
                session.commit()
            session.rollback()
            for sql, params in [
                (
                    "UPDATE applications SET resume_version_id = :version WHERE id = :id",
                    {"id": row["id"], "version": snapshot["draft"]["id"]},
                ),
                ("DELETE FROM application_events WHERE application_id = :id", {"id": row["id"]}),
                (
                    "UPDATE application_events SET note = 'changed' WHERE application_id = :id",
                    {"id": row["id"]},
                ),
            ]:
                with pytest.raises(IntegrityError):
                    session.execute(text(sql), params)
                    session.commit()
                session.rollback()
    finally:
        engine.dispose()
    assert client.get(f"/api/v1/applications/{row['id']}").json() == row
