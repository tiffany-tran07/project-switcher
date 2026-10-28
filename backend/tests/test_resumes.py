import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.library import get_session
from app.main import app
from app.resumes import safe_wording

pytest_plugins = ("test_library",)


@pytest.fixture
def resume_client(client: TestClient) -> TestClient:
    return client


def test_verified_only_immutable_snapshot(resume_client: TestClient) -> None:
    client = resume_client
    job = client.post(
        "/api/v1/jobs",
        json={
            "title": "Engineer",
            "company": "Example",
            "raw_description": "Build reliable services with Python and PostgreSQL.",
        },
    ).json()
    resume = client.post(
        "/api/v1/resumes", json={"job_id": job["id"], "name": "Example version"}
    ).json()
    experience = client.post(
        "/api/v1/experiences",
        json={
            "organization": "Previous Employer",
            "title": "Developer",
            "start_date": "2020-01-01",
            "end_date": "2023-06-30",
        },
    ).json()
    evidence = client.post(
        "/api/v1/evidence",
        json={
            "experience_id": experience["id"],
            "claim": "Built reliable Python services",
            "source_note": "Design notes",
        },
    ).json()
    client.put("/api/v1/profile", json={"name": "Saved Name", "email": "saved@example.test"})
    path = f"/api/v1/resumes/{resume['id']}/draft"
    assert client.post(path, json={"evidence_ids": [evidence["id"]]}).status_code == 422
    assert (
        client.post(path, json={"evidence_ids": [evidence["id"], evidence["id"]]}).status_code
        == 422
    )
    client.patch(f"/api/v1/evidence/{evidence['id']}", json={"state": "verified"})
    draft = client.post(path, json={"evidence_ids": [evidence["id"]], "approve": True})
    assert draft.status_code == 201
    version = draft.json()
    assert version["version_number"] == 1
    assert version["approved_at"] is not None
    assert version["content"]["profile"]["name"] == "Saved Name"
    assert version["bullets"][0]["evidence_snapshot"]["experience"]["start_date"] == "2020-01-01"
    assert version["bullets"][0]["evidence_snapshot"]["experience"]["end_date"] == "2023-06-30"
    client.put("/api/v1/profile", json={"name": "Changed Name", "email": "changed@example.test"})
    assert version["bullets"][0]["text"] == evidence["claim"]
    assert version["bullets"][0]["evidence_id"] == evidence["id"]
    assert (
        version["bullets"][0]["evidence_snapshot"]["experience"]["organization"]
        == "Previous Employer"
    )
    client.patch(
        f"/api/v1/experiences/{experience['id']}", json={"organization": "Changed Employer"}
    )
    assert client.post(path, json={"evidence_ids": [evidence["id"]]}).status_code == 422
    assert client.get(f"/api/v1/evidence/{evidence['id']}/resume-wordings").status_code == 422
    saved = client.get(f"/api/v1/resume-versions/{version['id']}").json()
    assert saved["bullets"] == version["bullets"]
    assert saved["content"] == version["content"]
    assert len(client.get(f"/api/v1/resumes/{resume['id']}/versions").json()) == 1
    client.patch(f"/api/v1/evidence/{evidence['id']}", json={"state": "verified"})
    next_version = client.post(path, json={"evidence_ids": [evidence["id"]]}).json()
    assert next_version["version_number"] == 2
    assert (
        next_version["bullets"][0]["evidence_snapshot"]["experience"]["organization"]
        == "Changed Employer"
    )
    assert (
        client.get(f"/api/v1/resume-versions/{version['id']}").json()["bullets"]
        == version["bullets"]
    )


def test_editable_sections_are_source_bound(resume_client: TestClient) -> None:
    client = resume_client
    job = client.post(
        "/api/v1/jobs",
        json={
            "title": "Engineer",
            "raw_description": "Experience using Python for data analysis.",
        },
    ).json()
    resume = client.post("/api/v1/resumes", json={"job_id": job["id"], "name": "Targeted"}).json()
    experience = client.post(
        "/api/v1/experiences",
        json={
            "organization": "Example",
            "title": "Engineer",
        },
    ).json()
    project = client.post(
        "/api/v1/projects",
        json={
            "name": "Pipeline",
            "experience_id": experience["id"],
            "start_date": "2022-03-01",
            "end_date": "2022-06-30",
            "url": "https://example.test/project",
        },
    ).json()
    a = client.post(
        "/api/v1/evidence",
        json={
            "experience_id": experience["id"],
            "claim": "I reduced latency 30% using Python",
            "source_note": "Benchmark notes",
        },
    ).json()
    b = client.post(
        "/api/v1/evidence",
        json={
            "project_id": project["id"],
            "claim": "Built a data pipeline",
            "source_note": "Project notes",
        },
    ).json()
    for item in (a, b):
        client.patch(f"/api/v1/evidence/{item['id']}", json={"state": "verified"})
    client.post(
        f"/api/v1/evidence/{a['id']}/bullets",
        json={
            "text": "Reduced latency 30% using Python",
            "approved": True,
        },
    )
    client.post(
        f"/api/v1/evidence/{a['id']}/bullets",
        json={
            "text": "Reduced latency 90% using AWS",
            "approved": True,
        },
    )
    assert client.get(f"/api/v1/evidence/{a['id']}/resume-wordings").json() == [
        "I reduced latency 30% using Python",
        "Reduced latency 30% using Python",
    ]
    url = f"/api/v1/resumes/{resume['id']}/draft"
    payload = {
        "sections": [
            {
                "heading": "Experience",
                "bullets": [{"evidence_id": a["id"], "text": "Reduced latency 30% using Python"}],
            },
            {
                "heading": "Projects",
                "bullets": [{"evidence_id": b["id"], "text": "Built a data pipeline"}],
            },
        ],
        "approve": True,
    }
    assert (
        client.post(
            url,
            json={
                "sections": [
                    {
                        "heading": "Projects",
                        "bullets": [{"evidence_id": a["id"], "text": a["claim"]}],
                    },
                ]
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            url,
            json={
                "sections": [
                    {
                        "heading": "Experience",
                        "bullets": [
                            {"evidence_id": a["id"], "text": "Reduced latency 40% using AWS"}
                        ],
                    },
                ]
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            url,
            json={
                "sections": [
                    {
                        "heading": "Experience",
                        "bullets": [
                            {"evidence_id": a["id"], "text": a["claim"]},
                            {"evidence_id": a["id"], "text": a["claim"]},
                        ],
                    },
                ]
            },
        ).status_code
        == 422
    )
    response = client.post(url, json=payload)
    assert response.status_code == 201
    result = response.json()
    assert result["content"]["sections"][1]["heading"] == "Projects"
    assert [bullet["text"] for bullet in result["bullets"]] == [
        "Reduced latency 30% using Python",
        "Built a data pipeline",
    ]
    assert result["approved_at"]
    project_snapshot = result["bullets"][1]["evidence_snapshot"]
    assert project_snapshot["experience"]["organization"] == "Example"
    assert project_snapshot["experience"]["title"] == "Engineer"
    assert project_snapshot["project"]["start_date"] == "2022-03-01"
    assert project_snapshot["project"]["end_date"] == "2022-06-30"
    assert project_snapshot["project"]["url"] == "https://example.test/project"
    assert len(client.get(f"/api/v1/resumes/{resume['id']}/versions").json()) == 1
    reversed_sections = client.post(
        url,
        json={
            **payload,
            "sections": list(reversed(payload["sections"])),
        },
    ).json()
    assert [section["heading"] for section in reversed_sections["content"]["sections"]] == [
        "Projects",
        "Experience",
    ]
    assert [bullet["evidence_id"] for bullet in reversed_sections["bullets"]] == [b["id"], a["id"]]
    assert [bullet["position"] for bullet in reversed_sections["bullets"]] == [0, 1]
    client.patch(f"/api/v1/projects/{project['id']}", json={"name": "Renamed pipeline"})
    client.patch(f"/api/v1/experiences/{experience['id']}", json={"title": "Changed title"})
    assert client.get(f"/api/v1/resume-versions/{result['id']}").json() == result


def test_validation_reports_all_issues_without_saving(resume_client: TestClient) -> None:
    client = resume_client
    job = client.post(
        "/api/v1/jobs",
        json={
            "title": "Engineer",
            "raw_description": "Use Python to build reliable services.",
        },
    ).json()
    resume = client.post("/api/v1/resumes", json={"job_id": job["id"], "name": "Review"}).json()
    experience = client.post(
        "/api/v1/experiences",
        json={
            "organization": "Example",
            "title": "Engineer",
        },
    ).json()
    item = client.post(
        "/api/v1/evidence",
        json={
            "experience_id": experience["id"],
            "claim": "Built Python services",
            "source_note": "Notes",
        },
    ).json()
    client.patch(f"/api/v1/evidence/{item['id']}", json={"state": "verified"})
    base = f"/api/v1/resumes/{resume['id']}"
    payload = {
        "sections": [
            {
                "heading": "Projects",
                "bullets": [
                    {"evidence_id": item["id"], "text": "Built AWS services"},
                    {"evidence_id": item["id"], "text": item["claim"]},
                    {"evidence_id": "missing", "text": "Invented claim"},
                ],
            }
        ]
    }
    result = client.post(f"{base}/validate", json=payload)
    assert result.status_code == 200
    report = result.json()
    assert not report["valid"]
    assert {issue["code"] for issue in report["issues"]} == {
        "section_context",
        "unsafe_wording",
        "duplicate",
        "unavailable_evidence",
    }
    assert (
        next(issue for issue in report["issues"] if issue["code"] == "duplicate")["position"] == 1
    )
    assert client.get(f"{base}/versions").json() == []
    assert client.post(f"{base}/draft", json=payload).status_code == 422
    assert client.get(f"{base}/versions").json() == []
    good = {
        "sections": [
            {
                "heading": "Experience",
                "bullets": [
                    {"evidence_id": item["id"], "text": item["claim"]},
                ],
            }
        ]
    }
    assert client.post(f"{base}/validate", json=good).json() == {"valid": True, "issues": []}
    assert client.get(f"{base}/versions").json() == []
    # Passing a preflight check never bypasses validation at the time of saving.
    client.patch(f"/api/v1/evidence/{item['id']}", json={"state": "rejected"})
    assert client.post(f"{base}/draft", json={**good, "approve": True}).status_code == 422
    assert (
        client.post(f"{base}/validate", json=good).json()["issues"][0]["code"]
        == "unavailable_evidence"
    )
    assert client.post("/api/v1/resumes/missing/validate", json=good).status_code == 404


def test_wording_preserves_numbers_named_tools_and_negations() -> None:
    assert safe_wording("I reduced latency 30% using Python", "Reduced latency 30% using Python")
    assert not safe_wording(
        "I reduced latency 30% using Python", "Reduced latency 40% using Python"
    )
    assert not safe_wording("I reduced latency 30% using Python", "Reduced latency 30% using AWS")
    assert not safe_wording("Did not lead the team", "Led the team")
    assert not safe_wording("Built C++ services", "Built C# services")
    assert not safe_wording("Reduced time 30% over 20 months", "Reduced time 30 over 20% months")
    assert not safe_wording("Worked 2020-2023", "Worked 2020 2023")
    assert not safe_wording("Built Python services", "Built Python services 管理")
    assert safe_wording("I built multilingual résumé tools", "Built multilingual résumé tools")
    assert not safe_wording("I led the team", "The team led I")


@pytest.mark.parametrize(
    ("claim", "proposed"),
    [
        ("Observed a -30% change", "Observed a 30% change"),
        ("Observed a −30% change", "Observed a +30% change"),
        ("Kept latency <30 ms", "Kept latency >30 ms"),
        ("Kept latency ≤30 ms", "Kept latency 30 ms"),
        ("Saved €30 per request", "Saved £30 per request"),
        ("Saved ¥30 per request", "Saved 30 per request"),
        ("Saved 30% and spent 20", "Saved 30 and spent 20%"),
        ("Handled 5–10 requests", "Handled 5 requests"),
        ("Built .NET services", "Built NET services"),
        ("Used A/B experiments", "Used B experiments"),
        ("Used Tool A", "Used Tool"),
        ("Used WAS services", "Used services"),
        ("Supported a lead", "Supported lead"),
        ("I worked with the lead", "I worked the lead"),
        ("Did not own the service", "Did own the service"),
        ("Maintained 99.9% uptime", "Maintained 999% uptime"),
        ("Improved (estimated) costs", "Improved estimated costs"),
    ],
)
def test_wording_rejects_semantic_symbol_and_scope_changes(claim: str, proposed: str) -> None:
    assert not safe_wording(claim, proposed)


@pytest.mark.parametrize(
    ("claim", "proposed"),
    [
        ("I built Python services", "Built Python services."),
        ("I have built Python services.", "Built Python services"),
        ("I was maintaining .NET services", "Maintaining .NET services"),
        ("I had been maintaining .NET services", "Maintaining .NET services"),
        ("I measured -30% and €20", "Measured -30% and €20"),
        ("I kept latency <30 ms", "Kept latency <30 ms"),
        ("Built résumé tools", "Built résumé tools."),
        ("Built Python services", "Built   Python services."),
    ],
)
def test_wording_allows_only_safe_style_changes(claim: str, proposed: str) -> None:
    assert safe_wording(claim, proposed)


def test_symbol_changes_block_drafting_and_wording_suggestions(resume_client: TestClient) -> None:
    client = resume_client
    experience = client.post(
        "/api/v1/experiences",
        json={
            "organization": "Example",
            "title": "Engineer",
        },
    ).json()
    item = client.post(
        "/api/v1/evidence",
        json={
            "experience_id": experience["id"],
            "claim": "I observed -30% change at €20 cost",
            "source_note": "Measured results",
        },
    ).json()
    client.patch(f"/api/v1/evidence/{item['id']}", json={"state": "verified"})
    bad = "Observed 30% change at £20 cost"
    client.post(f"/api/v1/evidence/{item['id']}/bullets", json={"text": bad, "approved": True})
    assert bad not in client.get(f"/api/v1/evidence/{item['id']}/resume-wordings").json()
    job = client.post(
        "/api/v1/jobs",
        json={
            "title": "Engineer",
            "raw_description": "Role requiring Python services experience.",
        },
    ).json()
    resume = client.post("/api/v1/resumes", json={"job_id": job["id"], "name": "Review"}).json()
    base = f"/api/v1/resumes/{resume['id']}"
    payload = {
        "sections": [
            {
                "heading": "Experience",
                "bullets": [
                    {"evidence_id": item["id"], "text": bad},
                ],
            }
        ],
        "approve": True,
    }
    checked = client.post(f"{base}/validate", json=payload).json()
    assert checked["valid"] is False
    assert checked["issues"][0]["code"] == "unsafe_wording"
    assert client.post(f"{base}/draft", json=payload).status_code == 422
    assert client.get(f"{base}/versions").json() == []
    payload["sections"][0]["bullets"][0]["text"] = "Observed -30% change at €20 cost."
    assert client.post(f"{base}/draft", json=payload).status_code == 201


def test_database_rejects_snapshot_mutations(resume_client: TestClient) -> None:
    client = resume_client
    job = client.post(
        "/api/v1/jobs",
        json={
            "title": "Engineer",
            "raw_description": "Experience using Python for data analysis.",
        },
    ).json()
    resume = client.post("/api/v1/resumes", json={"job_id": job["id"], "name": "Draft"}).json()
    experience = client.post(
        "/api/v1/experiences",
        json={
            "organization": "Example",
            "title": "Engineer",
        },
    ).json()
    evidence = client.post(
        "/api/v1/evidence",
        json={
            "experience_id": experience["id"],
            "claim": "Used Python",
            "source_note": "Notes",
        },
    ).json()
    client.patch(f"/api/v1/evidence/{evidence['id']}", json={"state": "verified"})
    version = client.post(
        f"/api/v1/resumes/{resume['id']}/draft",
        json={
            "evidence_ids": [evidence["id"]],
        },
    ).json()
    assert version["approved_at"] is None
    session_factory = app.dependency_overrides[get_session]
    iterator = session_factory()
    session = next(iterator)
    try:
        with pytest.raises(IntegrityError):
            session.execute(
                text("UPDATE resume_versions SET template = :value WHERE id = :id"),
                {"value": "other", "id": version["id"]},
            )
            session.commit()
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(
                text("DELETE FROM resume_bullets WHERE version_id = :id"), {"id": version["id"]}
            )
            session.commit()
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO resume_bullets "
                    "(id, version_id, evidence_id, text, position, evidence_snapshot) "
                    "VALUES ('extra', :id, :evidence, 'Unsafe', 42, '{}')"
                ),
                {"id": version["id"], "evidence": evidence["id"]},
            )
            session.commit()
        session.rollback()
    finally:
        iterator.close()
