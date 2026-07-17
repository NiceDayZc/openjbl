import subprocess

import pytest

from openjbl import updater


def test_check_for_update_detects_newer_version(monkeypatch):
    monkeypatch.setattr(updater, "fetch_latest_version", lambda _timeout: "0.2.3")
    result = updater.check_for_update(current="0.2.2")
    assert result.status == "update-available"
    assert result.latest == "0.2.3"


def test_check_for_update_reports_ahead_of_pypi(monkeypatch):
    monkeypatch.setattr(updater, "fetch_latest_version", lambda _timeout: "0.2.1")
    assert updater.check_for_update(current="0.2.2").status == "ahead-of-pypi"


def test_auto_update_skips_editable_checkout(monkeypatch):
    monkeypatch.setattr(updater, "is_editable_install", lambda: True)
    assert updater.auto_update().status == "editable-skip"


def test_safe_check_converts_network_failure_to_status(monkeypatch):
    monkeypatch.setattr(updater, "fetch_latest_version", lambda _timeout: (_ for _ in ()).throw(OSError("offline")))
    result = updater.check_for_update_safe(current="0.2.2")
    assert result.status == "check-failed"
    assert "offline" in result.message


def test_install_version_uses_current_interpreter_and_fixed_project(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, "installed", "")

    monkeypatch.setattr(updater.subprocess, "run", fake_run)
    result = updater.install_version("0.2.3")
    assert result.installed
    assert captured["command"][0] == updater.sys.executable
    assert captured["command"][-1] == "openjbl==0.2.3"
    assert captured["kwargs"]["check"] is False


def test_update_now_installs_available_release(monkeypatch):
    monkeypatch.setattr(
        updater,
        "check_for_update",
        lambda **_kwargs: updater.UpdateResult("0.2.2", "0.2.3", "update-available", "available"),
    )
    monkeypatch.setattr(
        updater,
        "install_version",
        lambda version: updater.UpdateResult("0.2.2", version, "installed", "done", True),
    )
    assert updater.update_now().installed


def test_auto_update_never_installs(monkeypatch):
    """Installing unpinned PyPI code at launch turns one account compromise into
    code execution on every machine, and pip rewrites site-packages under a
    process that is about to drive a radio. The check reports; the user installs.
    """
    installed = []
    monkeypatch.setattr(updater, "is_editable_install", lambda: False)
    monkeypatch.setattr(updater, "fetch_latest_version", lambda timeout=5.0: "99.0.0")
    monkeypatch.setattr(updater, "install_version", lambda *a, **k: installed.append(a) or None)

    result = updater.auto_update()
    assert result.status == "update-available"
    assert result.installed is False
    assert installed == [], "auto_update must not install"
    assert "openjbl update" in result.message, "it has to say how to install deliberately"


def test_auto_update_is_off_by_default():
    from openjbl.config import Settings

    assert Settings().auto_update is False


def test_install_version_validates_the_string_it_actually_passes_to_pip(monkeypatch):
    """_version_key strips before matching, so validation and use must not diverge."""
    seen = []

    class Completed:
        returncode = 0
        stdout = stderr = ""

    monkeypatch.setattr(updater.subprocess, "run", lambda cmd, **k: seen.append(cmd) or Completed())
    updater.install_version("  1.2.3  ")
    assert seen[0][-1] == "openjbl==1.2.3", "the argv must carry the validated value"

    for bad in ("1.0.0; rm -rf /", "1.0.0 --index-url http://evil", "$(whoami)", "1.0.0\n--extra-index-url=http://x"):
        with pytest.raises(ValueError):
            updater.install_version(bad)
