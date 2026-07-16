import subprocess

from vantadsp import updater


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
    assert captured["command"][-1] == "vantadsp==0.2.3"
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
