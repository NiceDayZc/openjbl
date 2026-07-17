# OpenJBL

OpenJBL is a safety-first Python toolkit and monochrome terminal interface for inspecting and controlling EQ on speakers supported by JBL Portable. It was built from static analysis of JBL Portable 6.9.12 and hardware validation, without modifying the original APK.

> Independent interoperability project. Not affiliated with or endorsed by JBL or Harman. All trademarks belong to their owners. Do not commit or redistribute APK or firmware files with this repository.

![OpenJBL monochrome Bluetooth EQ control TUI](docs/assets/openjbl-tui.png)

## Highlights

- Clean monochrome TUI with device discovery, model-aware EQ, live status, visible version/build identity, packet preview, and activity logs
- BLE scan, advertisement/manufacturer-data inspection, and full GATT service discovery
- Automatic JBL model/PID detection from Harman advertisement bytes, service UUIDs, names, and Windows paired metadata
- Harman/JBL BLE GATT and Bluetooth Classic SPP transports
- Legacy simple, advanced-level, and parametric EQ codecs
- Protocol 4 `0E02` parametric and Grip-style `0E7F` quantized EQ codecs
- PID-based automatic protocol routing across 37 catalogued models
- 87 sound profiles across three tiers: 24 standard, 63 extended-range LAB curves, and your own saved profiles. See [docs/PROFILES.md](docs/PROFILES.md).
- Read-only multi-generation probing, raw packet capture/decoding, and expert packet transmission
- Verified writes with protocol acknowledgement, automatic EQ read-back, per-band comparison, and detailed transaction logs
- CLI dry-run by default, direct TUI apply, target hashing, and JSONL audit logs

## Install

Install the latest release from PyPI:

```powershell
python -m pip install openjbl
```

OpenJBL never installs anything on its own. Set `auto_update` in `%LOCALAPPDATA%\openjbl\config.json` to have the TUI check PyPI at launch and tell you when a newer release exists; installing it is always an explicit command. Deciding to run new code is yours to make, and pip rewriting site-packages under a process that is about to drive a radio is not something to do in the background.

```powershell
openjbl check-update
openjbl update
```

To install from a cloned repository instead:

```powershell
python -m pip install .
```

For development, use an editable installation with the QA toolchain:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Launch the TUI:

```powershell
openjbl-tui
```

The interface provides DEVICE, EQUALIZER, and ACTIVITY workspaces, plus a detailed SYSTEM / DEVICE / PROTOCOL status strip. EQ remains locked until `SCAN + AUTO VERIFY` or `RE-VERIFY SELECTED` establishes a live BLE connection and receives a supported EQ response; cached Windows pairing metadata never unlocks it. Changing the address/model or encountering a connection failure locks it again. `APPLY TO SPEAKER` reads the state before writing, writes after model and gain validation, checks the acknowledgement, reads the EQ again, and reports `WRITE VERIFIED` only when the acknowledgement is accepted and every decoded band matches. It distinguishes `CHANGED + VERIFIED` from `ALREADY MATCHED + VERIFIED`, and says so only when the pre-write state was actually decoded. Activity opens automatically and records the transaction ID, route, target fingerprint, before/write/after TX/RX frames, decoded responses, requested and actual gains, per-band deltas, elapsed time, and failure stage. Audit records store a hash of the target instead of its Bluetooth address.

Runtime configuration and audit files are stored under `%LOCALAPPDATA%\openjbl\` on Windows. Bluetooth must be enabled, and Windows must permit desktop apps to use Bluetooth and location. For SPP, pair the speaker first and locate its outgoing COM port in Device Manager.

## Safe workflow

Close JBL Portable on nearby phones first so it does not compete for the connection.

```powershell
openjbl scan
openjbl services --address DEVICE_FROM_SCAN
openjbl probe --address DEVICE_FROM_SCAN
openjbl models
openjbl models 20e3
openjbl check-update
```

Known default BLE values extracted from the APK:

```text
service  65786365-6C70-6F69-6E74-2E636F6D0000
RX       65786365-6C70-6F69-6E74-2E636F6D0001
TX       65786365-6C70-6F69-6E74-2E636F6D0002
```

Some products derive a service UUID from PID/MID. Use `services` to discover it, then pass `--service`, `--rx`, and `--tx` overrides if necessary.

Read legacy and Protocol 4 EQ without changing the speaker:

```powershell
openjbl get-simple --address DEVICE
openjbl get-advanced --address DEVICE
openjbl get-p4-eq --address DEVICE
```

## EQ and sound profiles

Mutating commands only print the encoded TX packet unless `--apply` is supplied. The recommended path is PID-aware routing:

```powershell
openjbl set-auto --pid 20e3 5 3 -2.5 -3 -2 -.5 1
openjbl set-profile --pid 20e3 bass
openjbl set-profile --pid 20e3 clear --address DEVICE --apply
openjbl profiles
```

`set-auto` chooses legacy simple, advanced-level, legacy parametric, Protocol 4 `0E02`, or Grip-style `0E7F` from the APK-derived model profile. It refuses products for which the APK does not declare EQ support.

The 24 standard profiles stay inside each model's own UI range: Flat, Balanced, Bass Heavy, Deep Bass, Punch Bass, Warm, Loudness, Crystal Clear, Bright, Detail Monitor, Vocal, Podcast, Acoustic, Rock, Metal, Hip-Hop, EDM, Pop, Jazz, Classical, Cinema, Gaming, Outdoor, and Night.

A further 63 LAB profiles reach beyond it, up to +/-24 dB, and need `--allow-extended`. Most of them spend that range on cuts, which is what it is good for: a large boost has to come out of the DSP's headroom and the speaker's limiter, so it distorts and then gets quieter, while a cut costs level the volume knob gives back. The 18 that do boost are labelled DANGER and need a second, deliberate confirmation in the TUI. Run `openjbl profiles` for the full list, or see [Sound profiles](docs/PROFILES.md).

Examples for direct codec control:

```powershell
# Legacy 3-band signed levels
openjbl set-simple --bass 4 --mid 1 --treble -1

# Legacy advanced signed levels
openjbl set-levels 3 2 1 0 -1 -2 -3

# Legacy parametric bands: type,frequency,gain,q
openjbl set-parametric --category custom_c2 `
  --band "low_shelf,125,3,0.707" `
  --band "peaking,250,2,2" `
  --band "peaking,500,0,2" `
  --band "peaking,1000,-1,2" `
  --band "peaking,2000,0,2" `
  --band "peaking,4000,1,2" `
  --band "high_shelf,8000,2,0.707"

# Charge 6 custom-band order: 125, 250, 500, 1k, 2k, 4k, 8kHz
openjbl set-charge6 5 3 -2.5 -3 -2 -.5 1
```

Filter types are `low-shelf`, `peaking`, `high-shelf`, `low-pass`, and `high-pass`. Charge 6 custom band 1 supports -9..+6 dB with asymmetric negative quantization; bands 2-7 support -6..+6 dB in 0.5 dB steps, matching the APK UI mapping.

## Capture, decode, and expert mode

```powershell
openjbl listen --address DEVICE --seconds 15 --log capture.log
openjbl decode "AA980000"
openjbl raw "AA6C00"
openjbl raw "AA6C00" --address DEVICE --apply --i-understand
```

Raw transmission requires both `--apply` and `--i-understand`. No OTA, authentication bypass, factory reset, destructive command, or amplifier/limiter overclock path is implemented.

For Bluetooth Classic SPP, use an outgoing COM port instead of a BLE address:

```powershell
openjbl raw "AA6C00" --port COM7 --apply --i-understand
```

## Python API

```python
from openjbl.protocol import describe_frame, set_simple_eq

packet = set_simple_eq(category=0xC1, bass=4, mid=1, treble=-1)
print(packet.hex(), describe_frame(packet))
```

Protocol builders perform no Bluetooth I/O, so they are deterministic and reusable. Real transmission is isolated in `openjbl.transport`; applications should retain an explicit safety confirmation layer.

## Documentation

- [Protocol reference](docs/PROTOCOL.md)
- [Supported models](docs/SUPPORTED_MODELS.md)
- [Hardware-confirmed Charge 6 profile](docs/DEVICE_CHARGE6_20E3.md)
- [Sound profiles](docs/PROFILES.md)
- [Security and QA audit](docs/AUDIT.md)

## Quality assurance

```powershell
ruff format --check .
ruff check .
mypy src/openjbl
pytest
bandit -q -c pyproject.toml -r src/openjbl
pip-audit .
python -m build
twine check dist/*
```

GitHub Actions tests Windows and Linux on Python 3.10 and 3.12 with coverage, linting, typing, security, and package validation. APK/XAPK files, decompilation output, captures, local configuration, and audit logs are excluded from version control.
