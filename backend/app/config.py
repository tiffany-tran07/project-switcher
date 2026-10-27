from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    data_dir: Path = PROJECT_ROOT / "data"
    database_url: str = ""
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_chat_model: str = ""

    @property
    def resolved_data_dir(self) -> Path:
        path = self.data_dir.expanduser()
        return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.resolved_data_dir / 'resume.db'}"

    def ensure_data_dirs(self) -> None:
        for path in (
            self.resolved_data_dir,
            self.resolved_data_dir / "attachments",
            self.resolved_data_dir / "exports",
        ):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
