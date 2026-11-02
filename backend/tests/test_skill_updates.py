from fastapi.testclient import TestClient

pytest_plugins = ("test_library",)


def test_repeated_skill_saves_reuse_retained_aliases_and_keep_search_consistent(
    client: TestClient,
) -> None:
    skill = client.post(
        "/api/v1/skills", json={"name": "Database engine", "aliases": ["Postgres", "PSQL"]}
    ).json()
    path = f"/api/v1/skills/{skill['id']}"
    for aliases in (["Postgres", "PSQL"], ["PSQL", "Postgres"], ["Postgres", "Pg"], []):
        response = client.patch(
            path, json={"name": "Database engine", "category": "Database", "aliases": aliases}
        )
        assert response.status_code == 200
        assert sorted(response.json()["aliases"]) == sorted(aliases)
        assert client.get(path).json()["category"] == "Database"
        for alias in ("Postgres", "PSQL", "Pg"):
            matches = client.get("/api/v1/library/search", params={"q": alias}).json()
            assert any(row["id"] == skill["id"] for row in matches) == (alias in aliases)
    assert len(client.get("/api/v1/skills").json()) == 1


def test_skill_conflict_rolls_back_aliases_and_verification_changes(client: TestClient) -> None:
    skill = client.post("/api/v1/skills", json={"name": "Python", "aliases": ["PyLang"]}).json()
    client.post("/api/v1/skills", json={"name": "PostgreSQL"})
    project = client.post("/api/v1/projects", json={"name": "Fixture project"}).json()
    evidence = client.post(
        "/api/v1/evidence",
        json={
            "claim": "Built Python tools",
            "source_note": "Reviewed source",
            "project_id": project["id"],
            "skill_ids": [skill["id"]],
        },
    ).json()
    evidence_path = f"/api/v1/evidence/{evidence['id']}"
    client.patch(evidence_path, json={"state": "verified"})
    client.post(f"{evidence_path}/bullets", json={"text": evidence["claim"], "approved": True})
    before = client.get(evidence_path).json()
    response = client.patch(
        f"/api/v1/skills/{skill['id']}",
        json={
            "name": "PostgreSQL",
            "aliases": ["PyLang", "NewAlias"],
            "category": "Changed",
        },
    )
    assert response.status_code == 409
    current = client.get(f"/api/v1/skills/{skill['id']}").json()
    assert current == skill
    assert client.get(evidence_path).json() == before
    assert client.get("/api/v1/library/search?q=NewAlias").json() == []
    assert client.get("/api/v1/library/search?q=PyLang").json()[0]["id"] == skill["id"]
