import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load_module("release_check_runner", ROOT / "scripts" / "release_check.py")
workflow = load_module("release_workflow_guard", ROOT / "backend" / "tests" / "release_workflow.py")


def test_release_environment_overrides_user_settings_without_mutating_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_DIR", "/private/user-data")
    monkeypatch.setenv("DATABASE_URL", "sqlite:////private/user-data/resume.db")
    monkeypatch.setenv("data_dir", "/private/lowercase-user-data")
    monkeypatch.setenv("database_url", "sqlite:////private/lowercase-user-data/resume.db")
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://not-used.example.test")
    monkeypatch.setenv("OLLAMA_CHAT_MODEL", "not-used")
    monkeypatch.setenv("LIBREOFFICE_PATH", "/private/not-used")
    monkeypatch.setenv("HTTP_PROXY", "https://not-used.example.test")
    monkeypatch.setenv("PYTEST_ADDOPTS", "--ignore=tests")
    monkeypatch.setenv("NPM_CONFIG_OFFLINE", "false")
    source = tmp_path / "source"
    env = runner.isolated_env(tmp_path, source)
    assert env["DATABASE_URL"] == f"sqlite:///{source / 'resume.db'}"
    assert env["OLLAMA_BASE_URL"] == "http://127.0.0.1:1"
    assert env["OLLAMA_CHAT_MODEL"] == ""
    assert env["LIBREOFFICE_PATH"] == ""
    assert env["PYTEST_ADDOPTS"] == ""
    assert env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert env["npm_config_offline"] == "true"
    assert "HTTP_PROXY" not in env and "NPM_CONFIG_OFFLINE" not in env
    assert "data_dir" not in env and "database_url" not in env
    assert os.environ["DATA_DIR"] == "/private/user-data"
    assert runner.isolated_env(tmp_path, tmp_path / "restored", restored=True)["DATABASE_URL"] == ""


def test_release_report_directory_never_overwrites_existing_data(tmp_path: Path) -> None:
    existing = tmp_path / "existing"
    existing.mkdir()
    sentinel = existing / "sentinel.txt"
    sentinel.write_text("Keep this file")
    with pytest.raises(runner.CheckFailed, match="new directory"):
        runner.new_output(existing)
    assert sentinel.read_text() == "Keep this file"
    link = tmp_path / "link"
    link.symlink_to(existing, target_is_directory=True)
    with pytest.raises(runner.CheckFailed):
        runner.new_output(link / "child")
    assert not (existing / "child").exists()


def test_release_port_conflicts_fail_without_reusing_a_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sock = MagicMock()
    sock.__enter__.return_value.bind.side_effect = OSError("occupied")
    monkeypatch.setattr(runner.socket, "socket", lambda: sock)
    with pytest.raises(runner.CheckFailed, match="will not be reused or stopped"):
        runner.ports_available()


def test_failed_command_records_failure_and_retains_its_log(tmp_path: Path) -> None:
    (tmp_path / "logs").mkdir()
    report = {"checks": []}
    with pytest.raises(runner.CheckFailed):
        runner.run_step(
            report,
            tmp_path,
            "fixture-failure",
            [sys.executable, "-c", 'print("fictional failure"); raise SystemExit(3)'],
            ROOT,
            runner.isolated_env(tmp_path, tmp_path / "source"),
        )
    assert report["checks"][0]["status"] == "failed"
    assert report["checks"][0]["returncode"] == 3
    assert "fictional failure" in (tmp_path / report["checks"][0]["log"]).read_text()
    assert json.loads((tmp_path / "report.json").read_text())["checks"][0]["status"] == "failed"


def test_timed_out_command_cannot_be_reported_as_passed(tmp_path: Path) -> None:
    (tmp_path / "logs").mkdir()
    report = {"checks": []}
    with pytest.raises(runner.CheckFailed):
        runner.run_step(
            report,
            tmp_path,
            "fixture-timeout",
            [sys.executable, "-c", "import time; time.sleep(30)"],
            ROOT,
            runner.isolated_env(tmp_path, tmp_path / "source"),
            timeout=0.1,
        )
    assert report["checks"][0]["status"] == "failed"
    assert report["checks"][0]["error"] == "TimeoutExpired"


def test_workflow_guard_requires_new_owned_paths_before_app_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("RELEASE_CHECK_ROOT", raising=False)
    with pytest.raises(workflow.WorkflowFailed, match="isolation marker"):
        workflow.require_isolation("create")
    (tmp_path / ".release-check").write_text(workflow.MARKER)
    monkeypatch.setenv("RELEASE_CHECK_ROOT", str(tmp_path))
    monkeypatch.setenv("DATA_DIR", "/private/not-used")
    with pytest.raises(workflow.WorkflowFailed, match="Refusing settings"):
        workflow.require_isolation("create")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "source"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'source' / 'resume.db'}")
    (tmp_path / "source").mkdir()
    sentinel = tmp_path / "source" / "resume.db"
    sentinel.write_bytes(b"not a database; never open this")
    with pytest.raises(workflow.WorkflowFailed, match="must be new"):
        workflow.require_isolation("create")
    assert sentinel.read_bytes() == b"not a database; never open this"


def test_default_release_plan_contains_both_test_suites_and_browser_workflow(
    tmp_path: Path,
) -> None:
    commands = runner.full_commands(tmp_path / "work", tmp_path / "report")
    names = {name for name, _, _ in commands}
    by_name = {name: command for name, command, _ in commands}
    assert str(tmp_path / "work" / "frontend-build") in by_name["frontend-build"]
    assert str(tmp_path / "report" / "browser-artifacts") in by_name["browser-tests"]
    assert f"cache_dir={tmp_path / 'work' / 'pytest-cache'}" in by_name["backend-tests"]
    assert {
        "schema-upgrade",
        "schema-check",
        "backend-tests",
        "frontend-build",
        "frontend-tests",
        "browser-tests",
    } <= names


@pytest.mark.skipif(
    not (
        shutil.which("soffice")
        or shutil.which("libreoffice")
        or shutil.which("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    ),
    reason="Real release workflow requires LibreOffice",
)
def test_connected_drill_restores_fresh_api_without_touching_inherited_data(tmp_path: Path) -> None:
    active = tmp_path / "private-active"
    active.mkdir()
    sentinel = active / "resume.db"
    sentinel.write_bytes(b"private-sentinel-do-not-open")
    env = os.environ.copy()
    env.update(
        {
            "DATA_DIR": str(active),
            "DATABASE_URL": f"sqlite:///{sentinel}",
            "data_dir": str(active),
            "database_url": f"sqlite:///{sentinel}",
            "OLLAMA_BASE_URL": "https://private-never-used.example.test",
            "OLLAMA_CHAT_MODEL": "private-not-used",
        }
    )
    output = tmp_path / "report"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "release_check.py"),
            "--workflow-only",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, (
        result.stdout + result.stderr + (output / "report.json").read_text()
    )
    report = json.loads((output / "report.json").read_text())
    assert report["scope"] == "workflow-only"
    assert report["status"] == "passed"
    assert report["full_check_passed"] is False
    assert all(row["status"] == "passed" for row in report["checks"])
    assert report["workflow"]["fresh_restored_process"] is True
    assert report["workflow"]["database_url_cleared"] is True
    assert report["workflow"]["attachment_sha256_unchanged"] is True
    assert report["workflow"]["export_sha256_unchanged"] is True
    assert report["workflow"]["ats_reports_unchanged"] is True
    assert report["workflow"]["history_triggers_enforced"] is True
    assert sentinel.read_bytes() == b"private-sentinel-do-not-open"
    assert list(active.iterdir()) == [sentinel]
    with ZipFile(output / "workflow" / "fictional-backup.zip") as archive:
        assert all(not name.endswith(".env") for name in archive.namelist())
        assert len(json.loads(archive.read("manifest.json"))["files"]) == 4
    assert "private-never-used" not in (output / "report.json").read_text()
