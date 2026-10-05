from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

from fastapi.responses import FileResponse

from breakingweb import app as wab_app
from breakingweb.app import _frontend_bundle_status, build_manifest


def _write_with_mtime(path: Path, text: str, mtime_ns: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    os.utime(path, ns=(mtime_ns, mtime_ns))
    return path


def test_frontend_bundle_status_reports_missing_build(tmp_path: Path) -> None:
    source = tmp_path / "src" / "App.tsx"
    _write_with_mtime(source, "export {};\n", 3_000_000_000)

    available, reason = _frontend_bundle_status(
        tmp_path / "dist" / "index.html",
        tmp_path / "dist" / "assets",
        [source.parent],
    )

    assert available is False
    assert reason is not None
    assert "has not been built" in reason


def test_frontend_bundle_status_reports_stale_build(tmp_path: Path) -> None:
    index_path = tmp_path / "dist" / "index.html"
    asset_path = tmp_path / "dist" / "assets" / "index.js"
    _write_with_mtime(index_path, "<html></html>\n", 1_000_000_000)
    _write_with_mtime(asset_path, "console.log('old');\n", 1_000_000_000)
    source = _write_with_mtime(tmp_path / "src" / "App.tsx", "export const x = 1;\n", 3_000_000_000)

    available, reason = _frontend_bundle_status(index_path, asset_path.parent, [source.parent])

    assert available is False
    assert reason is not None
    assert "stale" in reason


def test_frontend_bundle_status_accepts_fresh_build(tmp_path: Path) -> None:
    index_path = tmp_path / "dist" / "index.html"
    asset_path = tmp_path / "dist" / "assets" / "index.js"
    source = _write_with_mtime(tmp_path / "src" / "App.tsx", "export const x = 1;\n", 1_000_000_000)
    _write_with_mtime(index_path, "<html></html>\n", 3_000_000_000)
    _write_with_mtime(asset_path, "console.log('fresh');\n", 3_000_000_000)

    available, reason = _frontend_bundle_status(index_path, asset_path.parent, [source.parent])

    assert available is True
    assert reason is None


def test_manifest_uses_dev_frontend_override(monkeypatch) -> None:
    monkeypatch.setenv("BREAKINGWEB_DEV_FRONTENDS", "gmail=http://localhost:4173/env/gmail")

    manifest = build_manifest()
    gmail_entry = next(env for env in manifest["environments"] if env["env_id"] == "gmail")

    assert gmail_entry["available"] is True
    assert gmail_entry["base_url"] == "http://localhost:4173/env/gmail"


def test_gmail_source_template_does_not_include_toolbar_script() -> None:
    index_html = Path(__file__).resolve().parents[1] / "environments" / "gmail" / "index.html"
    content = index_html.read_text()

    assert '/static/benchmark-toolbar.js' not in content


def test_gmail_shell_renders_benchmark_toolbar_component() -> None:
    shell_path = Path(__file__).resolve().parents[1] / "environments" / "gmail" / "src" / "Shell.tsx"
    content = shell_path.read_text()

    assert "BenchmarkToolbar" in content


def test_serve_env_html_returns_built_file_without_mutation(monkeypatch, tmp_path: Path) -> None:
    index_path = tmp_path / "index.html"
    index_path.write_text("<html><head></head><body>plain</body></html>\n")

    monkeypatch.setattr(wab_app, "_env_index_path", lambda env_id: index_path)
    monkeypatch.setattr(wab_app, "_env_frontend_status", lambda env_id: (True, None))

    response = wab_app._serve_env_html("gmail")

    assert isinstance(response, FileResponse)
    assert Path(response.path) == index_path


def test_auto_build_frontends_builds_only_stale_envs(monkeypatch) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("BREAKINGWEB_AUTO_BUILD_FRONTENDS", "1")

    stale_states = [["lms", "patient_portal"], ["lms", "patient_portal"], []]

    def fake_stale_frontend_env_ids() -> list[str]:
        return stale_states.pop(0) if stale_states else []

    build_calls: list[tuple[list[str], Path]] = []

    def fake_run(command: list[str], cwd: Path, check: bool) -> SimpleNamespace:
        build_calls.append((command, Path(cwd)))
        assert check is True
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(wab_app, "_stale_frontend_env_ids", fake_stale_frontend_env_ids)
    monkeypatch.setattr(wab_app.subprocess, "run", fake_run)

    built_envs = wab_app._auto_build_frontends_if_needed()

    assert built_envs == ["lms", "patient_portal"]
    assert build_calls == [
        (["pnpm", "--filter", "@breakingweb/shared", "build"], Path(wab_app.BASE_DIR / "environments")),
        (["pnpm", "--filter", "@breakingweb/lms", "build"], Path(wab_app.BASE_DIR / "environments")),
        (["pnpm", "--filter", "@breakingweb/patient_portal", "build"], Path(wab_app.BASE_DIR / "environments")),
    ]


def test_auto_build_frontends_respects_disable_flag(monkeypatch) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("BREAKINGWEB_AUTO_BUILD_FRONTENDS", "0")
    monkeypatch.setattr(
        wab_app,
        "_stale_frontend_env_ids",
        lambda: (_ for _ in ()).throw(AssertionError("stale env check should be skipped")),
    )

    assert wab_app._auto_build_frontends_if_needed() == []


def test_auto_build_frontends_raises_clear_error_on_build_failure(monkeypatch) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("BREAKINGWEB_AUTO_BUILD_FRONTENDS", "1")
    monkeypatch.setattr(wab_app, "_stale_frontend_env_ids", lambda: ["lms"])

    def fake_run(command: list[str], cwd: Path, check: bool) -> SimpleNamespace:
        raise subprocess.CalledProcessError(returncode=1, cmd=command)

    monkeypatch.setattr(wab_app.subprocess, "run", fake_run)

    try:
        wab_app._auto_build_frontends_if_needed()
    except RuntimeError as exc:
        assert "Frontend auto-build failed" in str(exc)
    else:
        raise AssertionError("expected RuntimeError when frontend build fails")
