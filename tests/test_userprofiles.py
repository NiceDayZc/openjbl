import json

import pytest

from openjbl.presets import PROFILE_BY_KEY, curve_from_model_gains, curve_summary, get_profile, resolve_curve
from openjbl.userprofiles import (
    ProfileStoreError,
    delete_user_profile,
    load_user_profiles,
    save_user_profile,
    user_profile_options,
)


@pytest.fixture
def store(tmp_path):
    return tmp_path / "profiles.json"


def test_save_and_load_round_trip(store):
    saved = save_user_profile("My Room Fix", [-12, -7, -2, 0, 0, 0, 0], path=store)
    assert saved.key == "user-my-room-fix"
    loaded = load_user_profiles(store)
    assert [profile.key for profile in loaded] == ["user-my-room-fix"]
    assert loaded[0].gains == (-12, -7, -2, 0, 0, 0, 0)
    assert loaded[0].name == "My Room Fix"


def test_missing_store_is_empty_not_an_error(store):
    assert load_user_profiles(store) == []
    assert user_profile_options(store) == []


def test_a_saved_profile_can_never_shadow_a_built_in(store):
    """The key prefix is what guarantees it, so naming one after a built-in is
    harmless rather than rejected."""
    assert all(not key.startswith("user-") for key in PROFILE_BY_KEY)
    saved = save_user_profile("bass", [0] * 7, path=store)
    assert saved.key == "user-bass" and saved.key not in PROFILE_BY_KEY
    assert get_profile("bass").name == "Bass Heavy", "the built-in is untouched"


def test_saving_twice_needs_overwrite(store):
    save_user_profile("Mine", [1] * 7, path=store)
    with pytest.raises(ValueError, match="already exists"):
        save_user_profile("Mine", [2] * 7, path=store)
    save_user_profile("Mine", [2] * 7, path=store, overwrite=True)
    loaded = load_user_profiles(store)
    assert len(loaded) == 1 and loaded[0].gains == (2,) * 7


def test_the_encoder_and_confirmation_flags_are_recomputed_not_trusted(store):
    """A hand-edited store must not be able to talk its way past the confirmation."""
    save_user_profile("Sneaky", [24, 0, 0, 0, 0, 0, 0], path=store)
    raw = json.loads(store.read_text(encoding="utf-8"))
    raw["profiles"][0]["dangerous"] = False
    raw["profiles"][0]["boosts_past_standard"] = False
    store.write_text(json.dumps(raw), encoding="utf-8")

    profile = load_user_profiles(store)[0]
    assert profile.dangerous is True, "a +24 dB curve still needs the extended encoder"
    assert profile.boosts_past_standard is True, "and still needs confirming"


def test_a_cut_only_saved_profile_needs_the_encoder_but_not_the_confirmation(store):
    profile = save_user_profile("Deep Cut", [0, -3, -12, -18, -20, -18, -14], path=store)
    assert profile.dangerous is True, "it leaves the model's step grid"
    assert profile.boosts_past_standard is False, "but a cut cannot clip"


@pytest.mark.parametrize(
    "gains, message",
    [
        ([0, 0, 0], "seven-point"),
        ([0] * 7 + [0], "seven-point"),
        ([25, 0, 0, 0, 0, 0, 0], "outside the protocol"),
        ([-25, 0, 0, 0, 0, 0, 0], "outside the protocol"),
        ([float("nan"), 0, 0, 0, 0, 0, 0], "real numbers"),
        ([float("inf"), 0, 0, 0, 0, 0, 0], "real numbers"),
    ],
)
def test_rejects_unusable_curves(store, gains, message):
    with pytest.raises(ValueError, match=message):
        save_user_profile("Bad", gains, path=store)


def test_rejects_a_nameless_profile(store):
    with pytest.raises(ValueError, match="at least one letter or digit"):
        save_user_profile("   ", [0] * 7, path=store)


def test_delete(store):
    save_user_profile("One", [1] * 7, path=store)
    save_user_profile("Two", [2] * 7, path=store)
    assert delete_user_profile("user-one", store) is True
    assert [profile.key for profile in load_user_profiles(store)] == ["user-two"]
    assert delete_user_profile("user-nothing", store) is False


def test_a_corrupt_store_is_reported_not_silently_dropped(store):
    store.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ProfileStoreError, match="cannot read"):
        load_user_profiles(store)
    store.write_text('{"version": 1}', encoding="utf-8")
    with pytest.raises(ProfileStoreError, match="not a profile store"):
        load_user_profiles(store)
    store.write_text('{"version": 1, "profiles": [{"name": "no gains"}]}', encoding="utf-8")
    with pytest.raises(ProfileStoreError, match="unusable profile"):
        load_user_profiles(store)


def test_a_saved_profile_outlives_the_speaker_it_was_made_on(store):
    """It is stored as a tonal curve, so it still means something on a model with
    a different number of bands."""
    three_band = curve_from_model_gains("2050", [6, 0, -3])
    assert len(three_band) == 7
    profile = save_user_profile("Travelled", three_band, path=store)
    seven_band = resolve_curve("20e3", profile)
    assert len(seven_band) == 7
    assert seven_band[0] > seven_band[-1], "the bass-forward shape must survive the move"


def test_a_seven_band_model_resamples_to_itself():
    gains = [6, 3, 0, -2, -4, -2, 0]
    assert list(curve_from_model_gains("20e3", gains)) == pytest.approx(gains)


@pytest.mark.parametrize(
    "gains, expected",
    [
        ([6, 4, 0, 0, 0, 4, 6], "V-shaped"),
        ([0, -3, -7, -10, -12, -12, -10], "bass-forward"),
        ([-12, -7, -2, 0, 0, 0, 0], "bass-light"),
        ([0, 0, -2, -3, -5, -13, -8], "dark tilt"),
        ([0, 0, 0, 0, 0, -6, -16], "dark"),
        ([0, 0, 0, 0, 0, 0, 0], "flat"),
    ],
)
def test_curve_summary_describes_the_shape(gains, expected):
    assert curve_summary(gains).startswith(expected)
