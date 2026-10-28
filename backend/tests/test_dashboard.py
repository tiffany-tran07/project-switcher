from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import dashboard

pytest_plugins = ("test_library", "test_exports")


def test_empty_dashboard(export_client: TestClient) -> None:
    response = export_client.get("/api/v1/dashboard")
    assert response.status_code == 200
    result = response.json()
    assert set(result["counts"].values()) == {0}
    for key in (
        "recent_jobs",
        "recent_resumes",
        "recent_applications",
        "due_follow_ups",
        "evidence_needing_review",
    ):
        assert result[key] == []


def test_dashboard_shows_real_versions_review_items_and_due_dates(
    export_client: TestClient,
    snapshot: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = export_client
    monkeypatch.setattr(dashboard, "utc_now", lambda: datetime(2026, 10, 28, 12, tzinfo=UTC))
    resume = client.get(f"/api/v1/resumes/{snapshot['approved']['resume_id']}").json()
    for status, date in [
        ("planned", "2026-10-27"),
        ("interview", "2026-10-28"),
        ("rejected", "2026-10-01"),
        ("withdrawn", "2026-10-01"),
        ("applied", "2026-10-29"),
    ]:
        client.post(
            "/api/v1/applications",
            json={
                "job_id": resume["job_id"],
                "resume_version_id": snapshot["approved"]["id"],
                "status": status,
                "follow_up_date": date,
            },
        )
    draft = client.post(
        "/api/v1/evidence",
        json={
            "experience_id": snapshot["evidence"]["experience_id"],
            "claim": "Draft claim without a source",
        },
    ).json()
    rejected = client.post(
        "/api/v1/evidence",
        json={
            "experience_id": snapshot["evidence"]["experience_id"],
            "claim": "Rejected claim",
        },
    ).json()
    client.patch(f"/api/v1/evidence/{rejected['id']}", json={"state": "rejected"})
    response = client.get("/api/v1/dashboard").json()
    assert response["today_utc"] == "2026-10-28"
    assert response["counts"] == {
        "jobs": 1,
        "resumes": 1,
        "applications": 5,
        "ready_evidence": 1,
        "evidence_needing_review": 1,
        "follow_ups_due": 2,
    }
    assert [row["follow_up_date"] for row in response["due_follow_ups"]] == [
        "2026-10-27",
        "2026-10-28",
    ]
    assert response["recent_resumes"][0]["latest_version"] == 2
    assert response["recent_resumes"][0]["latest_approved_version"] == 1
    assert response["evidence_needing_review"] == [
        {
            "id": draft["id"],
            "claim": draft["claim"],
            "reason": "Missing source note",
        }
    ]
    # Archiving source context makes evidence unavailable even if its stored state is verified.
    client.patch(
        f"/api/v1/experiences/{snapshot['evidence']['experience_id']}", json={"archived": True}
    )
    after = client.get("/api/v1/dashboard").json()
    assert after["counts"]["ready_evidence"] == 0
    assert after["counts"]["evidence_needing_review"] == 2
    # Historical resume versions remain visible and unchanged.
    assert after["recent_resumes"][0]["latest_approved_version"] == 1
    assert (
        client.get(f"/api/v1/resume-versions/{snapshot['approved']['id']}").json()
        == snapshot["approved"]
    )


def test_dashboard_caps_lists_without_capping_totals(export_client: TestClient) -> None:
    client = export_client
    for index in range(8):
        client.post(
            "/api/v1/jobs",
            json={
                "title": f"Role {index}",
                "raw_description": "A Python engineering job description.",
            },
        )
    response = client.get("/api/v1/dashboard").json()
    assert response["counts"]["jobs"] == 8
    assert len(response["recent_jobs"]) == 5
    assert response["recent_jobs"][0]["title"] == "Role 7"
