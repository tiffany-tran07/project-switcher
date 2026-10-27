import pytest
from fastapi.testclient import TestClient

from app import job_analysis, jobs
from app.config import settings

pytest_plugins = ("test_library",)


@pytest.fixture
def job_client(client: TestClient) -> TestClient:
    return client


def test_job_requirements_and_verified_matches(job_client: TestClient) -> None:
    experience = job_client.post(
        "/api/v1/experiences", json={"organization": "Acme", "title": "Engineer"}
    ).json()
    skill = job_client.post(
        "/api/v1/skills", json={"name": "PostgreSQL", "aliases": ["Postgres"]}
    ).json()
    direct = job_client.post(
        "/api/v1/evidence",
        json={
            "claim": "Built reporting with PostgreSQL",
            "source_note": "Design doc",
            "experience_id": experience["id"],
            "skill_ids": [skill["id"]],
        },
    ).json()
    job_client.patch(f"/api/v1/evidence/{direct['id']}", json={"state": "verified"})
    unverified = job_client.post(
        "/api/v1/evidence",
        json={
            "claim": "Deployed Kubernetes clusters",
            "source_note": "Draft note",
            "experience_id": experience["id"],
        },
    ).json()
    job = job_client.post(
        "/api/v1/jobs",
        json={
            "title": "Developer",
            "raw_description": "We require PostgreSQL, Kubernetes and leadership experience.",
        },
    )
    assert job.status_code == 201
    job_id = job.json()["id"]
    analyzed = job_client.post(f"/api/v1/jobs/{job_id}/analyze").json()
    assert analyzed["raw_description"].startswith("We require")
    terms = {row["text"] for row in analyzed["requirements"]}
    assert {"PostgreSQL", "Kubernetes", "Leadership"} <= terms
    assert (
        next(row for row in analyzed["requirements"] if row["text"] == "PostgreSQL")[
            "supporting_span"
        ]
        == "PostgreSQL"
    )
    matches = job_client.post(f"/api/v1/jobs/{job_id}/matches").json()
    by_term = {row["requirement"]["text"]: row for row in matches}
    assert by_term["PostgreSQL"]["status"] == "direct"
    assert by_term["PostgreSQL"]["matches"][0]["evidence_id"] == direct["id"]
    assert by_term["Kubernetes"]["status"] == "unsupported"
    assert all(m["evidence_id"] != unverified["id"] for row in matches for m in row["matches"])
    requirement_id = by_term["PostgreSQL"]["requirement"]["id"]
    edited = job_client.patch(
        f"/api/v1/jobs/{job_id}/requirements",
        json={
            "requirements": [
                {
                    "id": requirement_id,
                    "text": "Postgres",
                    "kind": "tool",
                    "confirmed": True,
                }
            ]
        },
    )
    assert edited.status_code == 200
    assert edited.json()[0]["id"] == requirement_id
    assert edited.json()[0]["confirmed"] is False  # Text changes require another review.
    assert edited.json()[0]["supporting_span"] is None
    assert job_client.post(f"/api/v1/jobs/{job_id}/matches").json()[0]["status"] == "direct"
    reviewed = job_client.patch(
        f"/api/v1/jobs/{job_id}/requirements",
        json={"requirements": [{"id": requirement_id, "text": "Postgres", "confirmed": True}]},
    )
    assert reviewed.json()[0]["confirmed"] is True
    assert job_client.get(f"/api/v1/jobs/{job_id}/requirements").json()[0]["id"] == requirement_id
    duplicate = job_client.patch(
        f"/api/v1/jobs/{job_id}/requirements",
        json={
            "requirements": [
                {"id": requirement_id, "text": "Postgres"},
                {"id": requirement_id, "text": "Python"},
            ]
        },
    )
    assert duplicate.status_code == 422
    assert job_client.get(f"/api/v1/jobs/{job_id}/requirements").json()[0]["text"] == "Postgres"
    assert (
        job_client.patch(
            f"/api/v1/jobs/{job_id}",
            json={"raw_description": "Altered posting content long enough to validate."},
        ).status_code
        == 422
    )
    assert (
        job_client.get(f"/api/v1/jobs/{job_id}").json()["raw_description"]
        == analyzed["raw_description"]
    )
    assert job_client.post(f"/api/v1/jobs/{job_id}/analyze").status_code == 409
    assert job_client.post(f"/api/v1/jobs/{job_id}/analyze?force=true").status_code == 200


def test_matching_excludes_source_notes_and_archived_records(job_client: TestClient) -> None:
    experience = job_client.post(
        "/api/v1/experiences", json={"organization": "Acme", "title": "Engineer"}
    ).json()
    evidence = job_client.post(
        "/api/v1/evidence",
        json={
            "experience_id": experience["id"],
            "claim": "Built reporting pipelines with Python",
            "source_note": "Review notes say: not Kubernetes",
        },
    ).json()
    job_client.patch(f"/api/v1/evidence/{evidence['id']}", json={"state": "verified"})
    job = job_client.post(
        "/api/v1/jobs",
        json={
            "title": "Engineer",
            "raw_description": "Build reporting dashboards using Python and Kubernetes.",
        },
    ).json()
    job_client.patch(
        f"/api/v1/jobs/{job['id']}/requirements",
        json={
            "requirements": [
                {"text": "Develop reporting dashboards using Python"},
                {"text": "Kubernetes"},
            ],
        },
    )
    matches = job_client.post(f"/api/v1/jobs/{job['id']}/matches").json()
    assert matches[0]["status"] == "related"
    assert matches[0]["matches"][0]["evidence_id"] == evidence["id"]
    assert matches[1]["status"] == "unsupported"
    job_client.patch(f"/api/v1/experiences/{experience['id']}", json={"archived": True})
    assert all(
        row["status"] == "unsupported"
        for row in job_client.post(f"/api/v1/jobs/{job['id']}/matches").json()
    )


def test_extraction_scopes_priorities_to_the_phrase() -> None:
    rows = jobs.extract_requirements(
        "Python is required. React is preferred. Experience with Docker is a bonus."
    )
    by_text = {row.text: row for row in rows}
    assert by_text["Python"].priority == "required"
    assert by_text["React"].priority == "preferred"
    assert by_text["Docker"].priority == "preferred"


def test_match_classifier_does_not_promote_incidental_words() -> None:
    assert jobs.classify_match("Java", "Built with JavaScript", []) is None
    assert jobs.classify_match("Kubernetes", "Used Python", []) is None
    assert jobs.classify_match("Kubernetes", "No Kubernetes work", []) is None
    assert (
        jobs.classify_match("Extensive experience with Kubernetes", "Experience with Python", [])
        is None
    )
    assert (
        jobs.classify_match("PostgreSQL", "Wrote database queries", ["Postgres", "PostgreSQL"])
        == "direct"
    )
    assert (
        jobs.classify_match(
            "Develop reporting dashboards using Python", "Built reporting pipelines with Python", []
        )
        == "related"
    )


def test_ollama_fallback_and_invalid_span(
    job_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = job_client.post(
        "/api/v1/jobs",
        json={
            "title": "Engineer",
            "raw_description": "Experience using Python for data analysis.",
        },
    ).json()

    def offline(_: str) -> list[object]:
        raise OSError("Ollama unavailable")

    monkeypatch.setattr(jobs, "extract_with_ollama", offline)
    result = job_client.post(f"/api/v1/jobs/{job['id']}/analyze?method=ollama")
    assert result.status_code == 200
    assert any(item["text"] == "Python" for item in result.json()["requirements"])


def test_ollama_rejects_unsupported_output(monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self, *_: object) -> bytes:
            output = {
                "requirements": [
                    {
                        "text": "Kubernetes",
                        "supporting_span": "Python",
                        "kind": "tool",
                        "priority": "required",
                    },
                    {
                        "text": "Python",
                        "supporting_span": "Python",
                        "kind": "skill",
                        "priority": "required",
                    },
                ]
            }
            return json.dumps({"message": {"content": json.dumps(output)}}).encode()

    monkeypatch.setattr(settings, "ollama_chat_model", "local-model")
    monkeypatch.setattr(job_analysis, "urlopen", lambda *_args, **_kwargs: FakeResponse())
    rows = job_analysis.extract_with_ollama("Python is required.")
    assert [row.text for row in rows] == ["Python"]


def test_missing_jobs_and_invalid_requirement(job_client: TestClient) -> None:
    assert job_client.post("/api/v1/jobs/missing/analyze").status_code == 404
    assert job_client.post("/api/v1/jobs/missing/matches").status_code == 404
    assert (
        job_client.post(
            "/api/v1/jobs", json={"title": "Developer", "raw_description": "short"}
        ).status_code
        == 422
    )
