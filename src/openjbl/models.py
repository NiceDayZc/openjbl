"""Model/PID database copied from the analyzed APK asset."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from . import protocol
from .protocol import EQ_CATEGORIES, FILTER_TYPES, ParametricBand

GRIP_STYLE_P4_PIDS = frozenset({"2132", "2168", "218a", "2185"})


def all_models() -> list[dict[str, Any]]:
    path = files("openjbl").joinpath("data/product_list_config.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["productList"]


def find_models(query: str | None = None) -> list[dict[str, Any]]:
    models = all_models()
    if query:
        needle = query.casefold()
        models = [
            model
            for model in models
            if needle in str(model.get("pid", "")).casefold() or needle in str(model.get("deviceName", "")).casefold()
        ]
    return [summarize_model(model) for model in models]


def summarize_model(model: dict[str, Any]) -> dict[str, Any]:
    features = list(model.get("features", []))
    pid = str(model.get("pid", "")).lower()
    if "PROTOCOL_4" in features:
        eq_path = "protocol4-grip-quantized" if pid in GRIP_STYLE_P4_PIDS else "protocol4-parametric"
    elif "7_BANDS_EQ" in features:
        eq_path = "legacy-parametric-7-band"
    elif "PRESET_EQ" in features or "EQ_BALANCE_SUPPORT" in features:
        eq_path = "legacy-advanced-or-simple (probe read commands first)"
    else:
        eq_path = "no EQ feature declared"
    return {
        "name": model.get("deviceName"),
        "pid": model.get("pid"),
        "transport": model.get("protocol"),
        "platform": model.get("platform"),
        "eq_path": eq_path,
        "eq_config": model.get("eqConfig") or model.get("presetEqPath"),
        "features": features,
    }


def get_model(pid: str) -> dict[str, Any]:
    matches = [model for model in all_models() if str(model.get("pid", "")).casefold() == pid.casefold()]
    if not matches:
        raise ValueError(f"PID {pid} is not in the APK model database")
    return matches[0]


def presets_for_pid(pid: str) -> list[dict[str, Any]]:
    model = get_model(pid)
    config = model.get("eqConfig") or model.get("presetEqPath")
    if not config:
        return []
    path = files("openjbl").joinpath(f"data/{config}")
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def preset_for_pid(pid: str, name: str) -> tuple[int, list[ParametricBand]]:
    needle = name.casefold()
    for preset in presets_for_pid(pid):
        if needle in (str(preset.get("categoryId", "")).casefold(), str(preset.get("displayName", "")).casefold()):
            category_name = str(preset["categoryId"]).lower()
            category = EQ_CATEGORIES.get({"reserved_2": "reserved_2"}.get(category_name, category_name))
            if category is None and category_name == "reserved_2":
                category = 0x22
            if category is None:
                raise ValueError(f"unknown category {preset['categoryId']}")
            bands = [
                ParametricBand(
                    FILTER_TYPES[str(param["type"]).replace("_FILTER", "").replace("PEAKING_EQ", "PEAKING").lower()],
                    float(param["gain"]),
                    float(param["frequency"]),
                    float(param["qValue"]),
                )
                for param in preset["params"]
            ]
            return category, bands
    raise ValueError(f"preset {name!r} not found for PID {pid}")


def _model_band_shape(pid: str, gains: list[float]) -> list[ParametricBand]:
    """Use the model's shipped signature preset as its frequency/Q template."""
    presets = presets_for_pid(pid)
    if not presets or not presets[0].get("params"):
        raise ValueError(f"PID {pid} has no EQ band shape in the APK")
    params = presets[0]["params"]
    if len(params) != len(gains):
        raise ValueError(f"PID {pid} expects {len(params)} gains, received {len(gains)}")
    bands = []
    for param, gain in zip(params, gains, strict=True):
        key = str(param["type"]).replace("_FILTER", "").replace("PEAKING_EQ", "PEAKING").lower()
        bands.append(ParametricBand(FILTER_TYPES[key], float(gain), float(param["frequency"]), float(param["qValue"])))
    return bands


# The range every model's own UI offers. Band 1 of the Charge 6 and the
# Grip-style models reaches further down than the rest; see
# docs/DEVICE_CHARGE6_20E3.md and resolve_profile's matching rule.
STANDARD_GAIN_CEILING_DB = 6.0
STANDARD_GAIN_FLOOR_DB = -6.0
STANDARD_BAND1_FLOOR_DB = -9.0
# ParametricBand.validate()'s bound: the furthest the float-parametric wire
# format is trusted to carry, and only with a deliberate opt-in.
EXTENDED_GAIN_LIMIT_DB = 24.0


def _standard_floor(pid: str, index: int) -> float:
    if index == 1 and (pid == "20e3" or pid in GRIP_STYLE_P4_PIDS):
        return STANDARD_BAND1_FLOOR_DB
    return STANDARD_GAIN_FLOOR_DB


def _reject_out_of_range(pid: str, gains: list[float], *, allow_extended: bool) -> None:
    """Bound the gains before any encoder sees them.

    This has to live here rather than in the encoders. Only two of them carried a
    per-model grid, so every other model reached the wire with whatever the caller
    passed: set_simple_eq and set_advanced_levels check only that the value fits
    in a signed byte, which is a fact about the wire, not about the speaker. On
    those two encoders the byte is a level index into a firmware table, so an
    out-of-range value is not "louder" or "quieter" -- it is undefined.
    """
    for index, value in enumerate(gains, 1):
        gain = float(value)
        if allow_extended:
            if not -EXTENDED_GAIN_LIMIT_DB <= gain <= EXTENDED_GAIN_LIMIT_DB:
                raise ValueError(
                    f"band {index} gain {gain:g} dB is outside the protocol's "
                    f"+/-{EXTENDED_GAIN_LIMIT_DB:g} dB bound"
                )
            continue
        floor = _standard_floor(pid, index)
        if not floor <= gain <= STANDARD_GAIN_CEILING_DB:
            raise ValueError(
                f"band {index} gain {gain:g} is outside the {floor:g}..{STANDARD_GAIN_CEILING_DB:g} "
                f"range PID {pid} offers; pass allow_extended to go beyond it"
            )


def auto_eq_frames(pid: str, gains: list[float], *, allow_extended: bool = False) -> tuple[str, list[bytes]]:
    """Select the APK-declared EQ wire format for a model PID."""
    model = get_model(pid)
    normalized_pid = str(model.get("pid", "")).lower()
    features = set(model.get("features", []))
    _reject_out_of_range(normalized_pid, gains, allow_extended=allow_extended)

    if "PROTOCOL_4" in features and normalized_pid in GRIP_STYLE_P4_PIDS:
        if allow_extended:
            raise ValueError("Grip-style table EQ does not support extended float gains")
        return "protocol4-grip-quantized/0E7F", protocol.p4_set_grip_eq(EQ_CATEGORIES["custom_c2"], gains)
    if "PROTOCOL_4" in features:
        bands = _model_band_shape(pid, gains)
        if len(bands) != 7:
            raise ValueError("Protocol 4 parametric EQ requires the model's 7 gains")
        return "protocol4-parametric/0E02", protocol.p4_set_parametric_eq(EQ_CATEGORIES["custom_c2"], bands)
    if "7_BANDS_EQ" in features:
        if normalized_pid == "20e3":
            bands = protocol.charge6_extended_bands(gains) if allow_extended else protocol.charge6_bands(gains)
        else:
            bands = _model_band_shape(pid, gains)
        return "legacy-parametric/0x97", [protocol.set_parametric_eq(EQ_CATEGORIES["custom_c2"], bands)]
    if "EQ_BALANCE_SUPPORT" in features:
        if allow_extended:
            raise ValueError("legacy simple EQ does not support extended float gains")
        if len(gains) != 3:
            raise ValueError(f"PID {pid} uses 3 gains: bass mid treble")
        ints = [int(value) for value in gains]
        if any(float(value) != integer for value, integer in zip(gains, ints, strict=True)):
            raise ValueError("legacy 3-band EQ accepts integer wire levels")
        return "legacy-simple/0x6E", [protocol.set_simple_eq(EQ_CATEGORIES["custom"], *ints)]
    if "PRESET_EQ" in features:
        if allow_extended:
            raise ValueError("legacy level EQ does not support extended float gains")
        expected = len(presets_for_pid(pid)[0].get("params", [])) if presets_for_pid(pid) else 5
        if len(gains) != expected:
            raise ValueError(f"PID {pid} expects {expected} level values")
        ints = [int(value) for value in gains]
        if any(float(value) != integer for value, integer in zip(gains, ints, strict=True)):
            raise ValueError("legacy level EQ accepts integer wire levels")
        return "legacy-advanced-level/0x97", [protocol.set_advanced_levels(EQ_CATEGORIES["custom"], ints)]
    raise ValueError(f"PID {pid} does not declare an EQ feature in this APK")


def gain_count_for_pid(pid: str) -> int:
    """Return the custom EQ control count declared by the APK model profile."""
    model = get_model(pid)
    features = set(model.get("features", []))
    if "PROTOCOL_4" in features or "7_BANDS_EQ" in features:
        return 7
    if "EQ_BALANCE_SUPPORT" in features:
        return 3
    if "PRESET_EQ" in features:
        presets = presets_for_pid(pid)
        return len(presets[0].get("params", [])) if presets else 5
    return 0


def auto_read_frames(pid: str) -> tuple[str, list[bytes]]:
    """Select the least invasive model-specific EQ read request."""
    model = get_model(pid)
    features = set(model.get("features", []))
    if "PROTOCOL_4" in features:
        return "protocol4-eq/0E01", protocol.p4_request_eq()
    if "7_BANDS_EQ" in features or "PRESET_EQ" in features:
        return "legacy-advanced/0x98", [protocol.request_advanced_eq()]
    if "EQ_BALANCE_SUPPORT" in features:
        return "legacy-simple/0x6C", [protocol.request_simple_eq()]
    raise ValueError(f"PID {pid} does not declare an EQ feature in this APK")
