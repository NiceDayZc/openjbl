# Engineering, safety, and release audit

Audit date: 2026-07-16
Audited release candidate: `0.2.4`

## Outcome

| Gate | Result |
|---|---|
| Unit/integration/headless TUI tests | 140 passed |
| Full-package branch-aware coverage | 76.26% (release gate 65%, `fail_under` in pyproject.toml) |
| Ruff lint and formatting | pass |
| mypy package type check | pass |
| Bandit static security scan | pass; no findings after reviewed B105 filter-name false positive is configured globally |
| Project dependency audit | pass; no known vulnerabilities from `pip-audit .` |
| Wheel and sdist build | pass |
| Twine metadata/render check | pass |
| Charge 6 read-only full probe | pass |
| Charge 6 PID-routed no-op write/read-back | pass; response and read-back matched byte-for-byte |
| Charge 6 controlled change/restore | pass; band 7 changed 0.0 -> +0.5 -> 0.0 with ACK and zero-delta read-back at both stages |
| Protocol-aware verification | legacy parametric/levels/simple and Protocol 4 0E02/0E7F covered |

The first environment-wide dependency scan found vulnerabilities in unrelated packages installed in the user's shared Python environment. A project-path audit was then run so the result represents this project's resolved dependency graph. CI runs in a clean environment and repeats that project audit.

## Threat and failure review

| Risk | Control | Residual risk |
|---|---|---|
| Wrong protocol sent to a model | PID capability database, `auto_read_frames`, `auto_eq_frames`, range/count validation | APK data or a future firmware can still differ; run `probe` first |
| Cached paired device mistaken for a live speaker | Scan rows identify `LIVE` vs `PAIRED CACHE`; only a live connection plus supported EQ response unlocks the TUI | A speaker can stop advertising after verification; every read/write reconnects and failures immediately relock EQ |
| Address/model changed after verification | Verified target is an exact `(address, PID)` tuple; either field changing invalidates it | Windows/BLE identity behavior can vary after reboot or re-pairing; rescan and verify again |
| Accidental mutation | CLI dry-run; TUI clearly labels direct apply; preview shows encoded bytes | A TUI apply click writes immediately; raw mode remains expert-only |
| Device identifier leakage | APK/captures/config/audit ignored by Git; audit stores 16-char SHA-256-derived fingerprint | Terminal screenshots and manually copied output can still reveal addresses |
| Corrupt or partial BLE response | frame length validation and decode errors | Protocol 4 multi-notification reassembly is limited to the notifications returned by one transaction window |
| Concurrent app connection | documented instruction to close the mobile app | OS/firmware arbitration differs by platform |
| Unsupported gain damages sound/hardware | model-specific UI range for Charge 6 and quantized Grip tables; conservative generic parametric validation | Generic expert commands can encode values beyond a model's UI; limiter behavior is firmware-specific |
| Supply-chain issue | bounded dependency ranges, project-path vulnerability scan, clean CI | No lockfile/hash pinning yet; releases should add a reviewed lock/SBOM workflow |
| Proprietary material accidentally published | `.gitignore` and `MANIFEST.in` exclude APK/XAPK/decompile output | Contributors must still inspect staged files before pushing |

## QA layers

- Known byte-vector tests cover legacy requests, simple EQ, long-frame parametric EQ, Protocol 4 query, category mapping, and Grip quantization.
- Database tests assert 37 APK models and build neutral packets for all 21 models declaring EQ.
- Profile matrix tests resolve and encode all 24 profiles across all 21 EQ-capable PIDs (504 model/profile combinations).
- Negative tests cover invalid gain counts, non-integer legacy levels, invalid UI steps, unknown PID/preset, malformed configuration, cached/offline devices, and the TUI connection gate.
- Fake transports exercise write response selection, false post-connect state, and probe classification without requiring Bluetooth hardware.
- Textual `run_test` verifies the locked startup state, live verification unlock, target-change relock, cached-device rejection, and verified write path.
- Hardware verification is intentionally opt-in and currently covers JBL Charge 6 PID `20E3`, firmware `3.0.7.1`.

## Known limitations

- Hardware confirmation cannot be claimed for models not physically tested; their routing is static-analysis-backed.
- BLE random addresses change and should be rescanned.
- Protocol 4 Grip preset tails can be firmware-specific; custom gain routing uses only the confirmed APK table portion.
- Older products for which APK 6.9.12 declares no EQ are rejected rather than probed with undocumented mutations.
- This project does not implement OTA flashing, authentication bypass, factory reset automation, destructive fuzzing, A2DP audio processing, or amplifier power changes.

## Release checklist

1. Inspect `git status` and confirm no APK, capture, address, local config, or generated reverse-engineering output is staged.
2. Run every QA command from the README in a clean virtual environment.
3. Verify version consistency between `pyproject.toml`, `openjbl.__version__`, and changelog.
4. Build from a clean tree and install the wheel into a new environment; smoke-test `openjbl --help` and `openjbl-tui`.
5. Tag a signed release and attach only the wheel/sdist, checksums, changelog, and sanitized documentation.
