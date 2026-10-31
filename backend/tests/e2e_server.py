"""Playwright-only API launcher. Always uses disposable data, never the real .env database."""

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def main() -> None:
    with TemporaryDirectory(prefix="resume-e2e-") as temporary:
        os.environ["DATA_DIR"] = temporary
        os.environ["DATABASE_URL"] = f"sqlite:///{Path(temporary) / 'e2e.db'}"
        os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:1"  # Never use a real Ollama instance.
        os.environ["OLLAMA_CHAT_MODEL"] = ""
        # Settings and database modules must only be imported AFTER the isolation overrides.
        import uvicorn
        from alembic import command
        from alembic.config import Config

        config = Config(str(BACKEND / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND / "migrations"))
        command.upgrade(config, "head")
        uvicorn.run("app.main:app", host="127.0.0.1", port=8876, log_level="warning")


if __name__ == "__main__":
    main()
