import pytest

from vantadsp.models import all_models, auto_eq_frames
from vantadsp.presets import PROFILES, get_profile, resolve_profile, sparkline


def test_profile_catalog_is_large_and_unique():
    assert len(PROFILES) >= 24
    assert len({profile.key for profile in PROFILES}) == len(PROFILES)
    assert get_profile("bass").name == "Bass Heavy"
    with pytest.raises(ValueError, match="unknown"):
        get_profile("missing")


def test_every_profile_builds_for_every_eq_model():
    built = 0
    for model in all_models():
        pid = str(model.get("pid"))
        features = set(model.get("features", []))
        if not features.intersection({"PROTOCOL_4", "7_BANDS_EQ", "EQ_BALANCE_SUPPORT", "PRESET_EQ"}):
            continue
        for profile in PROFILES:
            gains = resolve_profile(pid, profile.key)
            _path, frames = auto_eq_frames(pid, gains)
            assert frames
            built += 1
    assert built == 21 * len(PROFILES)


def test_model_specific_quantization():
    assert resolve_profile("20e3", "night")[0] == -4.5
    assert all(float(value).is_integer() for value in resolve_profile("1f53", "balanced"))
    assert len(resolve_profile("20dc", "bass")) == 5
    assert len(sparkline([6, 0, -6])) == 3
