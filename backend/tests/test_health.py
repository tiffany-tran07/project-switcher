from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app import main
from app.config import settings


def test_health_after_migration(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    # Use a file DB so migration and the API exercise the same schema.
    from sqlalchemy import create_engine

    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "database_url", database_url)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "migrations"))
    command.upgrade(config, "head")
    test_engine = create_engine(database_url)
    monkeypatch.setattr(main, "engine", test_engine)
    with TestClient(main.app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert (tmp_path / "attachments").is_dir()
    assert (tmp_path / "exports").is_dir()
    test_engine.dispose()
