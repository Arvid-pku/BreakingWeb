"""Keep existing experiment settings usable after the benchmark rename."""

from __future__ import annotations

from typing import Any

import pytest

from breakingweb.app import _auto_frontend_build_enabled, _dev_frontend_overrides
from breakingweb.config import getenv
from breakingweb.runner import controller_headers, ensure_controller_secret, start_server


@pytest.mark.parametrize("value", ["configured", ""])
def test_new_setting_takes_precedence(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("WEBSTRESS_API_KEY", "legacy")
    monkeypatch.setenv("BREAKINGWEB_API_KEY", value)
    assert getenv("BREAKINGWEB_API_KEY", "default") == value


def test_settings_are_read_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BREAKINGWEB_API_KEY", raising=False)
    monkeypatch.delenv("WEBSTRESS_API_KEY", raising=False)
    assert getenv("BREAKINGWEB_API_KEY", "default") == "default"
    monkeypatch.setenv("WEBSTRESS_API_KEY", "legacy")
    assert getenv("BREAKINGWEB_API_KEY") == "legacy"


def test_legacy_frontend_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BREAKINGWEB_AUTO_BUILD_FRONTENDS", raising=False)
    monkeypatch.delenv("BREAKINGWEB_DEV_FRONTENDS", raising=False)
    monkeypatch.setenv("WEBSTRESS_AUTO_BUILD_FRONTENDS", "0")
    monkeypatch.setenv("WEBSTRESS_DEV_FRONTENDS", "gmail=http://localhost:4173/env/gmail")
    assert _auto_frontend_build_enabled() is False
    assert _dev_frontend_overrides() == {"gmail": "http://localhost:4173/env/gmail"}


def test_legacy_controller_secret_reaches_new_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BREAKINGWEB_CONTROLLER_SECRET", raising=False)
    monkeypatch.setenv("WEBSTRESS_CONTROLLER_SECRET", "legacy-controller")
    assert ensure_controller_secret() == "legacy-controller"
    assert controller_headers() == {"X-WAB-Controller-Secret": "legacy-controller"}

    def fake_popen(command: list[str], **kwargs: Any) -> object:
        assert "breakingweb.app:app" in command
        assert kwargs["env"]["BREAKINGWEB_CONTROLLER_SECRET"] == "legacy-controller"
        return process

    process = object()
    monkeypatch.setattr("breakingweb.runner.subprocess.Popen", fake_popen)
    assert start_server("127.0.0.1", 8080) is process
