from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.config import settings

pytest_plugins = ("test_library", "test_exports")


def statuses(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/v1/resume-evidence")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    return {row["evidence_id"]: row for row in response.json()}


def test_source_availability_excludes_archived_and_never_verifies_drafts(
    export_client: TestClient, snapshot: dict[str, Any]
) -> None:
    client = export_client
    source_id = snapshot["evidence"]["id"]
    project = client.post("/api/v1/projects", json={"name": "Independent fixture"}).json()
    rows = []
    for state in ("draft", "rejected", "archived"):
        row = client.post(
            "/api/v1/evidence", json={"project_id": project["id"], "claim": f"{state} claim"}
        ).json()
        client.patch(
            f"/api/v1/evidence/{row['id']}",
            json={"state": "rejected"}
            if state == "rejected"
            else {"archived": True}
            if state == "archived"
            else {},
        )
        rows.append(row)
    result = statuses(client)
    assert result[source_id] == {"evidence_id": source_id, "eligible": True, "problem": None}
    assert result[rows[0]["id"]]["eligible"] is False
    assert result[rows[1]["id"]]["eligible"] is False
    assert rows[2]["id"] not in result
    assert client.get(f"/api/v1/evidence/{rows[0]['id']}").json()["state"] == "draft"
    assert (
        client.get(f"/api/v1/resume-versions/{snapshot['approved']['id']}").json()
        == snapshot["approved"]
    )


def test_archived_context_is_not_a_ready_source_even_when_claim_stays_verified(
    export_client: TestClient, snapshot: dict[str, Any]
) -> None:
    client = export_client
    source = snapshot["evidence"]
    parent = f"/api/v1/experiences/{source['experience_id']}"
    client.patch(parent, json={"archived": True})
    result = statuses(client)
    assert result[source["id"]]["eligible"] is False
    assert client.get(f"/api/v1/evidence/{source['id']}").json()["state"] == "verified"
    report = client.post(
        f"/api/v1/resumes/{snapshot['approved']['resume_id']}/validate",
        json={"evidence_ids": [source["id"]]},
    ).json()
    assert report["valid"] is False
    assert report["issues"][0]["message"] == result[source["id"]]["problem"]
    client.patch(parent, json={"archived": False})
    assert statuses(client)[source["id"]]["eligible"] is True
    project = client.post(
        "/api/v1/projects",
        json={"name": "Linked fixture", "experience_id": source["experience_id"]},
    ).json()
    child = client.post(
        "/api/v1/evidence",
        json={
            "project_id": project["id"],
            "claim": "Built fixture tools",
            "source_note": "Reviewed notes",
        },
    ).json()
    client.patch(f"/api/v1/evidence/{child['id']}", json={"state": "verified"})
    project_path = f"/api/v1/projects/{project['id']}"
    client.patch(project_path, json={"archived": True})
    assert statuses(client)[child["id"]]["eligible"] is False
    client.patch(project_path, json={"archived": False})
    assert statuses(client)[child["id"]]["eligible"] is True
    client.patch(parent, json={"archived": True})
    assert statuses(client)[child["id"]]["eligible"] is False


def test_attached_file_checks_match_final_validation_without_mutating_history(
    export_client: TestClient, snapshot: dict[str, Any]
) -> None:
    client = export_client
    source_id = snapshot["evidence"]["id"]
    source_path = f"/api/v1/evidence/{source_id}"
    upload = client.post(
        f"{source_path}/attachments?filename=proof.txt",
        content=b"Reviewed source",
        headers={"Content-Type": "application/octet-stream"},
    ).json()
    assert statuses(client)[source_id]["eligible"] is False
    client.patch(source_path, json={"state": "verified"})
    assert statuses(client)[source_id]["eligible"] is True
    path: Path = settings.resolved_data_dir / "attachments" / f"{upload['id']}.txt"
    path.write_bytes(b"Damaged source")
    current = client.get(source_path).json()
    result = statuses(client)[source_id]
    assert result["eligible"] is False
    assert "attached source file" in result["problem"]
    report = client.post(
        f"/api/v1/resumes/{snapshot['approved']['resume_id']}/validate",
        json={"evidence_ids": [source_id]},
    ).json()
    assert report["issues"][0]["message"] == result["problem"]
    assert client.get(source_path).json() == current
    assert (
        client.get(f"/api/v1/resume-versions/{snapshot['approved']['id']}").json()
        == snapshot["approved"]
    )
    path.write_bytes(b"Reviewed source")
    assert statuses(client)[source_id]["eligible"] is True


def test_eligible_source_is_not_automatic_wording_or_section_approval(
    export_client: TestClient, snapshot: dict[str, Any]
) -> None:
    client = export_client
    source_id = snapshot["evidence"]["id"]
    assert statuses(client)[source_id]["eligible"] is True
    report = client.post(
        f"/api/v1/resumes/{snapshot['approved']['resume_id']}/validate",
        json={
            "sections": [
                {
                    "heading": "Projects",
                    "bullets": [
                        {"evidence_id": source_id, "text": "Invented management experience"}
                    ],
                }
            ],
        },
    ).json()
    assert report["valid"] is False
    assert {issue["code"] for issue in report["issues"]} == {"section_context", "unsafe_wording"}
    assert statuses(client)[source_id]["eligible"] is True
