import pytest

from openjbl.models import (
    all_models,
    auto_eq_frames,
    auto_read_frames,
    gain_count_for_pid,
    get_model,
    preset_for_pid,
    presets_for_pid,
)


def test_database_has_all_apk_models_and_presets():
    assert len(all_models()) == 37
    assert get_model("20E3")["deviceName"] == "JBL Charge 6"
    assert len(presets_for_pid("20e3")) == 4
    category, bands = preset_for_pid("20e3", "VOCAL")
    assert category == 3
    assert len(bands) == 7


def test_every_declared_eq_model_builds_a_neutral_packet():
    built = []
    for model in all_models():
        pid = str(model.get("pid"))
        features = set(model.get("features", []))
        if not features.intersection({"PROTOCOL_4", "7_BANDS_EQ", "EQ_BALANCE_SUPPORT", "PRESET_EQ"}):
            continue
        if "PROTOCOL_4" in features or "7_BANDS_EQ" in features:
            count = 7
        elif "EQ_BALANCE_SUPPORT" in features:
            count = 3
        else:
            presets = presets_for_pid(pid)
            count = len(presets[0]["params"]) if presets else 5
        path, frames = auto_eq_frames(pid, [0.0] * count)
        assert path and frames
        built.append(pid)
    assert len(built) == 21


@pytest.mark.parametrize(
    ("pid", "gains", "message"),
    [
        ("0023", [0, 0, 0], "does not declare"),
        ("1f53", [0, 0], "uses 3 gains"),
        ("1f53", [0.5, 0, 0], "integer"),
        ("20dc", [0, 0], "expects"),
        ("20dc", [0.5] * 5, "integer"),
    ],
)
def test_auto_route_rejects_unsafe_or_wrong_shapes(pid, gains, message):
    with pytest.raises(ValueError, match=message):
        auto_eq_frames(pid, gains)


def test_unknown_model_and_preset_errors():
    with pytest.raises(ValueError, match="not in"):
        get_model("ffff")
    with pytest.raises(ValueError, match="not found"):
        preset_for_pid("20e3", "not-a-preset")


@pytest.mark.parametrize(
    ("pid", "count", "read_path"),
    [("20e3", 7, "legacy-advanced/0x98"), ("1f53", 3, "legacy-simple/0x6C"), ("2132", 7, "protocol4-eq/0E01")],
)
def test_model_specific_read_and_gain_count(pid, count, read_path):
    assert gain_count_for_pid(pid) == count
    path, frames = auto_read_frames(pid)
    assert path == read_path
    assert frames
