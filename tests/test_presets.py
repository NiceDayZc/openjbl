import pytest

from openjbl.models import all_models, auto_eq_frames
from openjbl.presets import (
    ALL_PROFILES,
    LAB_PROFILES,
    PROFILES,
    STANDARD_MAX_BOOST_DB,
    get_profile,
    resolve_profile,
    sparkline,
)


def test_subtractive_lab_profiles_never_boost():
    """Their whole point is spending the extended range on cuts, which cannot
    clip. A boost sneaking in would silently reintroduce the problem."""
    subtractive = [profile for profile in LAB_PROFILES if "subtractive" in profile.tags]
    assert len(subtractive) >= 30
    for profile in subtractive:
        assert max(profile.gains) <= STANDARD_MAX_BOOST_DB, f"{profile.key} boosts past the standard range"
        assert profile.boosts_past_standard is False, f"{profile.key} would demand a needless confirmation"
        assert min(profile.gains) < -6.0, f"{profile.key} fits in the standard range and does not need LAB"


def test_no_two_profiles_share_a_curve():
    """A duplicate curve under a second name is a menu that lies about its size."""
    seen: dict[tuple[float, ...], str] = {}
    for profile in ALL_PROFILES:
        clash = seen.get(profile.gains)
        assert clash is None, f"{profile.key} has the same curve as {clash}"
        seen[profile.gains] = profile.key


def test_the_reference_family_removes_colouration_rather_than_adding_anything():
    """Its whole premise is that an expensive speaker is defined by an absence.
    Any boost here would be adding a colouration back."""
    reference = [profile for profile in LAB_PROFILES if "reference" in profile.tags]
    assert len(reference) >= 8
    for profile in reference:
        assert max(profile.gains) <= 0, f"{profile.key} adds a boost; the point is to take things away"
        # 1 kHz carries the voice and instrument fundamentals. The family either
        # leaves it alone and clears around it, or tilts gently past it -- but it
        # must never be the band cut hardest, which is what gutting the mids means.
        assert profile.gains[3] > min(profile.gains), f"{profile.key} guts the midrange it should protect"


def test_the_bass_family_gets_its_weight_from_the_tilt_not_a_boost():
    """The whole family leaves 125 Hz alone and cuts above it, so the tilt the ear
    hears as bass costs level rather than headroom."""
    bass = [profile for profile in LAB_PROFILES if "bass" in profile.tags and "subtractive" in profile.tags]
    assert len(bass) >= 8
    for profile in bass:
        assert profile.gains[0] == 0, f"{profile.key} should leave the 125 Hz band untouched"
        tilt = profile.gains[0] - min(profile.gains)
        assert tilt >= 10, f"{profile.key} only tilts {tilt} dB, which the standard range already covers"


def test_lab_membership_and_danger_are_separate_questions():
    """A deep cut needs the extended encoder but not the confirmation: labelling
    it DANGER is what makes people stop reading the real warnings."""
    stunt = get_profile("lab-max-bass")
    assert stunt.dangerous is True and stunt.boosts_past_standard is True

    deep_cut = get_profile("lab-night")
    assert deep_cut.dangerous is True, "it leaves the model's step grid, so it needs the LAB encoder"
    assert deep_cut.boosts_past_standard is False, "but it only cuts, so it cannot clip"

    for profile in PROFILES:
        assert profile.boosts_past_standard is False, f"standard profile {profile.key} must never need confirming"


def test_profile_catalog_is_large_and_unique():
    assert len(PROFILES) >= 24
    assert len(LAB_PROFILES) >= 20
    assert len({profile.key for profile in ALL_PROFILES}) == len(ALL_PROFILES)
    assert get_profile("bass").name == "Bass Heavy"
    assert get_profile("lab-test-8k").dangerous
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
    assert sparkline([6, 0, -6]).isascii()


def test_lab_profiles_build_extended_charge6_packets():
    for profile in LAB_PROFILES:
        gains = resolve_profile("20e3", profile.key)
        path, frames = auto_eq_frames("20e3", gains, allow_extended=True)
        assert path == "legacy-parametric/0x97"
        assert frames
        assert all(-24 <= value <= 24 for value in gains)
    assert any(24 in profile.gains or -24 in profile.gains for profile in LAB_PROFILES)
    with pytest.raises(ValueError, match=r"-6\.\.\+6"):
        auto_eq_frames("20e3", resolve_profile("20e3", "lab-test-8k"))


def test_lab_profiles_reject_non_parametric_models():
    with pytest.raises(ValueError, match="float-parametric"):
        resolve_profile("1f53", "lab-test-8k")
