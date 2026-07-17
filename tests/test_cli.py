import pytest

from openjbl import cli
from openjbl.cli import main


def test_cli_auto_is_dry_run(capsys):
    main(["set-auto", "--pid", "20e3", "0", "0", "0", "0", "0", "0", "0"])
    output = capsys.readouterr().out
    assert "legacy-parametric/0x97" in output
    assert "DRY-RUN" in output


def test_cli_decode(capsys):
    main(["decode", "AA 42 04 03 00 07 01"])
    assert "3.0.7.1" in capsys.readouterr().out


def test_cli_auto_read_is_model_specific(capsys, monkeypatch):
    monkeypatch.setattr(cli, "send", lambda _args, frames: print(frames[0].hex(" ")))
    main(["get-auto", "--pid", "2132"])
    output = capsys.readouterr().out
    assert "protocol4-eq/0E01" in output
    assert "00 dd" in output


def test_cli_reports_validation_without_traceback():
    with pytest.raises(SystemExit, match="not found"):
        main(["set-preset", "--pid", "20e3", "--preset", "jazz"])


def test_cli_profile_is_model_aware_and_dry_run(capsys):
    main(["set-profile", "--pid", "20e3", "bass"])
    output = capsys.readouterr().out
    assert "Profile: bass" in output
    assert "Gains: 6 4 1 -1 -1 0 1" in output
    assert "DRY-RUN" in output


def test_cli_lab_profile_requires_explicit_unlock(capsys):
    with pytest.raises(SystemExit, match="allow-extended"):
        main(["set-profile", "--pid", "20e3", "lab-test-8k"])
    main(["set-profile", "--pid", "20e3", "lab-test-8k", "--allow-extended"])
    output = capsys.readouterr().out
    assert "Gains: 0 0 0 0 0 0 24" in output
    assert "DRY-RUN" in output
