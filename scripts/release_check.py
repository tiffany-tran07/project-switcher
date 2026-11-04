"""Run from the repository root: .venv/bin/python scripts/release_check.py.

Only standard-library imports here: app settings must never load before isolation.
"""

import argparse
import json
import os
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory, mkdtemp
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
SCENARIO = BACKEND / "tests" / "release_workflow.py"
MARKER = "resume-release-check-v1"


class CheckFailed(Exception):
    pass


def isolated_env(root: Path, data: Path, *, restored: bool = False) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.lower().startswith("npm_config_")
        and key.upper() not in {"PYTHONPATH", "PYTHONHOME", "PYTEST_PLUGINS"}
        and key.lower() not in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}
    }
    overrides = {
        "RELEASE_CHECK_ROOT": str(root),
        "DATA_DIR": str(data),
        "DATABASE_URL": "" if restored else f"sqlite:///{data / 'resume.db'}",
        "APP_HOST": "127.0.0.1",
        "APP_PORT": "8000",
        "OLLAMA_BASE_URL": "http://127.0.0.1:1",
        "OLLAMA_CHAT_MODEL": "",
        "LIBREOFFICE_PATH": "",
        "VITE_API_URL": "http://127.0.0.1:8000",
        "E2E_PYTHON": sys.executable,
        "PYTEST_ADDOPTS": "",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "NO_PROXY": "127.0.0.1,localhost,testserver",
        "TMPDIR": str(root / "tmp"),
        "MYPY_CACHE_DIR": str(root / "mypy-cache"),
        "RUFF_CACHE_DIR": str(root / "ruff-cache"),
        "npm_config_offline": "true",
        "npm_config_audit": "false",
        "npm_config_fund": "false",
        "npm_config_update_notifier": "false",
        "NPM_CONFIG_USERCONFIG": str(root / "npmrc"),
        "NPM_CONFIG_GLOBALCONFIG": str(root / "npm-globalrc"),
        "npm_config_cache": str(root / "npm-cache"),
    }
    # Pydantic settings are case-insensitive; stale lowercase aliases must not win.
    replaced = {key.upper() for key in overrides}
    env = {key: value for key, value in env.items() if key.upper() not in replaced}
    env.update(overrides)
    return env


def new_output(path: Path | None) -> Path:
    if path is None:
        parent = ROOT / "data" / "release-checks"
        if parent.absolute() != parent.resolve():
            raise CheckFailed("Default report path contains symlinks; choose --output explicitly")
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        prefix = datetime.now(UTC).strftime("run-%Y%m%dT%H%M%SZ-")
        return Path(mkdtemp(prefix=prefix, dir=parent))
    path = path.expanduser().absolute()
    if path != path.resolve() or path.exists() or path.is_symlink():
        raise CheckFailed("--output must be a new directory without symlinks or parent traversal")
    path.mkdir(parents=True, mode=0o700)
    return path


def ports_available() -> None:
    for port in (8876, 5174):
        try:
            with socket.socket() as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", port))
        except OSError as exc:
            raise CheckFailed(
                f"Test port {port} is busy; existing servers will not be reused or stopped"
            ) from exc


def stop_owned_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "posix":
        os.killpg(process.pid, signal.SIGTERM)
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait()


def run_step(
    report: dict[str, Any],
    output: Path,
    name: str,
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    *,
    timeout: float = 600,
    expected: int = 0,
    contains: str | None = None,
) -> None:
    started = time.monotonic()
    log = output / "logs" / f"{len(report['checks']) + 1:02d}-{name}.log"
    entry: dict[str, Any] = {
        "name": name,
        "status": "running",
        "log": str(log.relative_to(output)),
        "expected_returncode": expected,
    }
    report["checks"].append(entry)
    print(f"Checking {name}…", flush=True)
    try:
        with log.open("xb") as handle:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=os.name == "posix",
            )
            try:
                code = process.wait(timeout=timeout)
            except BaseException:
                stop_owned_process(process)
                raise
        entry["returncode"] = code
        if code != expected:
            raise CheckFailed(f"{name} exited {code}; see {entry['log']}")
        if contains and contains not in log.read_text(errors="replace"):
            raise CheckFailed(
                f"{name} did not produce its expected confirmation; see {entry['log']}"
            )
        entry["status"] = "passed"
    except (OSError, subprocess.TimeoutExpired, CheckFailed, KeyboardInterrupt) as exc:
        entry["status"] = "failed"
        entry["error"] = type(exc).__name__
        raise CheckFailed(f"{name} failed; see {entry['log']}") from exc
    finally:
        entry["seconds"] = round(time.monotonic() - started, 2)
        (output / "report.json").write_text(json.dumps(report, indent=2))


def full_commands(root: Path, output: Path) -> list[tuple[str, list[str], Path]]:
    python = sys.executable
    return [
        ("backend-lint", [python, "-m", "ruff", "check", "app", "tests", "../scripts"], BACKEND),
        ("backend-types", [python, "-m", "mypy", "app", "../scripts"], BACKEND),
        ("schema-upgrade", [python, "-m", "alembic", "upgrade", "head"], BACKEND),
        ("schema-check", [python, "-m", "alembic", "check"], BACKEND),
        (
            "backend-tests",
            [python, "-m", "pytest", "-q", "-o", f"cache_dir={root / 'pytest-cache'}"],
            BACKEND,
        ),
        (
            "frontend-build",
            ["npm", "run", "build", "--", "--outDir", str(root / "frontend-build")],
            FRONTEND,
        ),
        ("frontend-lint", ["npm", "run", "lint"], FRONTEND),
        ("frontend-tests", ["npm", "test", "--", "--run"], FRONTEND),
        (
            "browser-tests",
            ["npm", "run", "test:e2e", "--", "--output", str(output / "browser-artifacts")],
            FRONTEND,
        ),
    ]


def execute(output: Path, report: dict[str, Any], workflow_only: bool) -> None:
    with TemporaryDirectory(prefix="resume-release-") as temporary:
        root = Path(temporary).resolve()
        (root / ".release-check").write_text(MARKER)
        (root / "tmp").mkdir()
        env = isolated_env(root, root / "checks")
        executable = (
            shutil.which("soffice")
            or shutil.which("libreoffice")
            or shutil.which("/Applications/LibreOffice.app/Contents/MacOS/soffice")
        )
        if not executable:
            raise CheckFailed(
                "LibreOffice is required; this check will not silently skip real PDF conversion"
            )
        report["tools"] = {
            "python": sys.version.split()[0],
            "sqlite": sqlite3.sqlite_version,
            "libreoffice": executable,
        }
        run_step(
            report,
            output,
            "libreoffice",
            [
                executable,
                f"-env:UserInstallation={(root / 'lo-profile').as_uri()}",
                "--headless",
                "--version",
            ],
            BACKEND,
            env,
            timeout=60,
            contains="LibreOffice",
        )
        report["tools"]["libreoffice_version"] = (
            (output / report["checks"][-1]["log"]).read_text().strip()
        )
        if not workflow_only:
            ports_available()
            run_step(
                report,
                output,
                "chromium",
                [
                    "node",
                    "--input-type=module",
                    "-e",
                    'import { chromium } from "@playwright/test"; '
                    'import { existsSync } from "node:fs"; '
                    "if (!existsSync(chromium.executablePath())) process.exit(1); "
                    'console.log("Chromium installed");',
                ],
                FRONTEND,
                env,
                timeout=30,
                contains="Chromium installed",
            )
            for name, command, cwd in full_commands(root, output):
                if name == "browser-tests":
                    ports_available()
                run_step(report, output, name, command, cwd, env)
        artifacts = output / "workflow"
        artifacts.mkdir()
        source_env = isolated_env(root, root / "source")
        source_env["RELEASE_CHECK_ARTIFACTS"] = str(artifacts)
        run_step(
            report,
            output,
            "workflow-create",
            [sys.executable, str(SCENARIO), "create"],
            BACKEND,
            source_env,
            timeout=180,
            contains="workflow created",
        )
        backup = artifacts / "fictional-backup.zip"
        run_step(
            report,
            output,
            "backup-check-only",
            [sys.executable, "-m", "app.restore", str(backup), "--check-only"],
            BACKEND,
            source_env,
            timeout=120,
            contains="validated",
        )
        destination = root / "restored"
        command = [
            sys.executable,
            "-m",
            "app.restore",
            str(backup),
            "--destination",
            str(destination),
        ]
        run_step(
            report,
            output,
            "restore-clean-installation",
            command,
            BACKEND,
            source_env,
            timeout=120,
            contains="restored",
        )
        before = sha256((destination / "resume.db").read_bytes()).hexdigest()
        run_step(
            report,
            output,
            "refuse-existing-destination",
            command,
            BACKEND,
            source_env,
            timeout=60,
            expected=2,
            contains="Destination must be a new directory",
        )
        if sha256((destination / "resume.db").read_bytes()).hexdigest() != before:
            raise CheckFailed("Refused restore changed the existing destination")
        restored_env = isolated_env(root, destination, restored=True)
        restored_env["RELEASE_CHECK_ARTIFACTS"] = str(artifacts)
        run_step(
            report,
            output,
            "verify-fresh-restored-api",
            [sys.executable, str(SCENARIO), "verify"],
            BACKEND,
            restored_env,
            timeout=120,
            contains="restored workflow verified",
        )
        report["workflow"] = json.loads((artifacts / "result.json").read_text())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Isolated fictional-data release check; never uses the active database."
    )
    parser.add_argument(
        "--output", type=Path, help="New report directory; never overwrites an existing directory"
    )
    parser.add_argument(
        "--workflow-only",
        action="store_true",
        help="Only the connected recovery drill, not a full release check",
    )
    args = parser.parse_args(argv)
    try:
        output = new_output(args.output)
    except (OSError, CheckFailed) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    (output / "logs").mkdir()
    report: dict[str, Any] = {
        "format": "resume-release-check-v1",
        "scope": "workflow-only" if args.workflow_only else "full",
        "status": "running",
        "full_check_passed": False,
        "fictional_data_only": True,
        "started_at": datetime.now(UTC).isoformat(),
        "checks": [],
    }
    (output / "report.json").write_text(json.dumps(report, indent=2))
    try:
        execute(output, report, args.workflow_only)
        report["status"] = "passed"
        report["full_check_passed"] = not args.workflow_only
    except (CheckFailed, OSError, ValueError, KeyboardInterrupt) as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        (output / "report.json").write_text(json.dumps(report, indent=2))
    print(f"{report['scope']} check: {report['status']}. Report: {output / 'report.json'}")
    print("Automated fixture coverage is not real-user acceptance.")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
