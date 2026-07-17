import json

import pytest

from openjbl.audit import append_audit, target_fingerprint
from openjbl.config import Settings


def test_settings_roundtrip_and_unknown_keys(tmp_path):
    path = tmp_path / "config.json"
    settings = Settings(last_address="AA:BB", last_pid="2132", timeout=4.5)
    assert settings.save(path) == path
    loaded = Settings.load(path)
    assert loaded == settings

    data = json.loads(path.read_text(encoding="utf-8"))
    data["future_key"] = True
    path.write_text(json.dumps(data), encoding="utf-8")
    assert Settings.load(path) == settings


def test_settings_rejects_non_object(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="root"):
        Settings.load(path)


def test_audit_hashes_target_and_appends_jsonl(tmp_path):
    path = tmp_path / "audit.jsonl"
    address = "AA:BB:CC:DD:EE:FF"
    append_audit("preview", address=address, pid="20e3", applied=False, details={"gain": 5}, path=path)
    append_audit("apply", address=address, pid="20e3", applied=True, path=path)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[0]["target"] == target_fingerprint(address)
    assert address not in path.read_text(encoding="utf-8")
    assert rows[1]["applied"] is True
