from hashlib import sha256
from typing import Any

from fastapi.testclient import TestClient

pytest_plugins = ("test_library", "test_exports")


def test_restoring_archived_evidence_preserves_snapshots_and_exports(
    export_client: TestClient,
    snapshot: dict[str, Any],
) -> None:
    client = export_client
    evidence = snapshot["evidence"]
    version = snapshot["approved"]
    original = client.get(f"/api/v1/evidence/{evidence['id']}").json()
    artifact = client.post(f"/api/v1/resume-versions/{version['id']}/export", json={}).json()
    evidence_path = f"/api/v1/evidence/{evidence['id']}"
    experience_path = f"/api/v1/experiences/{evidence['experience_id']}"
    assert client.patch(evidence_path, json={"archived": True}).status_code == 200
    assert not any(row["id"] == evidence["id"] for row in client.get("/api/v1/evidence").json())
    assert any(
        row["id"] == evidence["id"]
        for row in client.get("/api/v1/evidence?include_archived=true").json()
    )
    client.patch(experience_path, json={"archived": True})
    assert client.patch(evidence_path, json={"archived": False}).status_code == 422
    assert client.get(evidence_path).json()["archived_at"] is not None
    client.patch(experience_path, json={"archived": False})
    restored = client.patch(evidence_path, json={"archived": False}).json()
    assert restored["archived_at"] is None
    assert restored["claim"] == original["claim"]
    assert restored["state"] == original["state"] == "verified"
    assert restored["verified_at"] == original["verified_at"]
    assert client.get(f"/api/v1/resume-versions/{version['id']}").json() == version
    download = client.get(f"/api/v1/exports/{artifact['id']}/download")
    assert sha256(download.content).hexdigest() == artifact["checksum"]


def test_restoration_does_not_verify_drafts_or_rejected_evidence(export_client: TestClient) -> None:
    client = export_client
    project = client.post("/api/v1/projects", json={"name": "Personal project"}).json()
    for state in ("draft", "rejected"):
        evidence = client.post(
            "/api/v1/evidence",
            json={
                "project_id": project["id"],
                "claim": f"{state} claim",
                "source_note": "Review needed",
            },
        ).json()
        path = f"/api/v1/evidence/{evidence['id']}"
        if state == "rejected":
            client.patch(path, json={"state": "rejected"})
        client.patch(path, json={"archived": True})
        client.patch(f"/api/v1/projects/{project['id']}", json={"archived": True})
        assert client.patch(path, json={"archived": False}).status_code == 422
        client.patch(f"/api/v1/projects/{project['id']}", json={"archived": False})
        restored = client.patch(path, json={"archived": False}).json()
        assert restored["state"] == state
        assert restored["verified_at"] is None


def test_archived_skill_aliases_return_to_search_when_restored(export_client: TestClient) -> None:
    client = export_client
    skill = client.post(
        "/api/v1/skills", json={"name": "PostgreSQL", "aliases": ["Postgres"]}
    ).json()
    path = f"/api/v1/skills/{skill['id']}"
    client.patch(path, json={"archived": True})
    assert client.get("/api/v1/library/search?q=Postgres").json() == []
    assert client.get("/api/v1/skills").json() == []
    assert client.get("/api/v1/skills?include_archived=true").json()[0]["id"] == skill["id"]
    restored = client.patch(path, json={"archived": False}).json()
    assert restored["aliases"] == ["Postgres"]
    assert client.get("/api/v1/library/search?q=Postgres").json()[0]["id"] == skill["id"]
