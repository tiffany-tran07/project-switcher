from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.library import get_session
from app.main import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    database_url = f"sqlite:///{tmp_path / 'library.db'}"
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "database_url", database_url)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "migrations"))
    command.upgrade(config, "head")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    sessions = sessionmaker(bind=engine)

    def override_session() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def test_verified_evidence_and_metric_changes(client: TestClient) -> None:
    experience = client.post(
        "/api/v1/experiences", json={"organization": "Example", "title": "Engineer"}
    ).json()
    skill = client.post(
        "/api/v1/skills", json={"name": "PostgreSQL", "aliases": ["Postgres"]}
    ).json()
    evidence = client.post(
        "/api/v1/evidence",
        json={
            "claim": "Improved report speed by 30% using PostgreSQL",
            "experience_id": experience["id"],
            "skill_ids": [skill["id"]],
        },
    ).json()
    evidence_url = f"/api/v1/evidence/{evidence['id']}"
    assert client.patch(evidence_url, json={"state": "verified"}).status_code == 422
    assert (
        client.post(
            f"{evidence_url}/bullets", json={"text": "Improved reports by 30%", "approved": True}
        ).status_code
        == 422
    )

    metric = client.post(
        f"{evidence_url}/metrics",
        json={
            "name": "Report speed",
            "value": "30",
            "unit": "%",
            "source_note": "Benchmark log",
        },
    ).json()
    assert (
        client.patch(evidence_url, json={"source_note": "Project review notes"}).json()["state"]
        == "draft"
    )
    assert client.patch(evidence_url, json={"state": "verified"}).json()["state"] == "verified"
    bullet = client.post(
        f"{evidence_url}/bullets", json={"text": "Improved reports by 30%", "approved": True}
    ).json()
    assert bullet["approved_at"] is not None

    client.patch(f"/api/v1/metrics/{metric['id']}", json={"value": "25"})
    updated = client.get(evidence_url).json()
    assert updated["state"] == "draft"
    assert updated["bullet_variants"][0]["approved_at"] is None
    assert (
        client.patch(f"/api/v1/bullets/{bullet['id']}", json={"approved": True}).status_code == 422
    )


def test_search_alias_and_export(client: TestClient) -> None:
    skill = client.post(
        "/api/v1/skills", json={"name": "PostgreSQL", "aliases": ["Postgres"]}
    ).json()
    results = client.get("/api/v1/library/search", params={"q": "Postgres"}).json()
    assert any(row["id"] == skill["id"] for row in results)
    exported = client.get("/api/v1/library/export").json()
    assert exported["format_version"] == 1
    assert exported["skills"][0]["aliases"] == ["Postgres"]


def test_browser_can_write_to_local_api(client: TestClient) -> None:
    response = client.options(
        "/api/v1/evidence",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
