# Engineering, safety, and release audit

Audit date: 2026-07-17
Audited tree: `0.3.0` plus the fixes below. Never published.

## Outcome

| Gate | Result |
|---|---|
| Unit/integration/headless TUI tests | 150 passed |
| Full-package branch-aware coverage | 76.73% (release gate 65%, `fail_under` in pyproject.toml) |
| Ruff lint and formatting | pass |
| mypy package type check | pass |
| Bandit static security scan | pass; the reviewed B105 filter-name false positive is configured globally |
| Project dependency audit | pass; no known vulnerabilities from `pip-audit .` |
| Wheel and sdist build | pass |
| Twine metadata/render check | pass |
| Charge 6 read-only full probe | pass |
| Charge 6 PID-routed no-op write/read-back | pass; response and read-back matched byte for byte |
| Charge 6 controlled change/restore | pass; band 7 changed 0.0 -> +0.5 -> 0.0 with ACK and zero-delta read-back at both stages |

The first environment-wide dependency scan found vulnerabilities in unrelated
packages in a shared Python environment. A project-path audit was then run so the
result represents this project's resolved graph. CI repeats it in a clean one.

## Whole-system audit, 2026-07-17

Ten review dimensions, every finding adversarially refuted before it counted: 46
raised, 29 survived. The tree was never published, so none of it reached a user.
All of it is fixed. The summary is kept because the patterns are worth not
repeating.

### What was wrong

| Finding | Why it mattered |
|---|---|
| `auto_update` defaulted on and ran `pip install` at TUI launch | Unpinned, unhashed, unprompted: one compromise of one PyPI account meant code execution on every machine, while pip rewrote site-packages under a process about to drive a radio |
| `set-auto` accepted +/-24 dB on 16 of 21 models with no opt-in | The range check lived inside the Charge 6 branch. `set_simple_eq` and `set_advanced_levels` only check that a value fits in a signed byte, which is a fact about the wire, not about the speaker |
| READ and APPLY shared an exclusive worker group | Pressing `r` cancelled a write after the frame was on the wire and before the read-back: one keystroke defeating the evidence |
| The extended-gain confirmation used a decibel argument on level-index encoders | "A cut cannot clip" is true for dB gains and false for a table index, where -100 is not quiet but undefined |
| `apply_worker` authorised once and kept writing across a reconnect | The revocation mechanism did not stop the write it exists to stop |
| A failed subscription cached a connected but deaf link | Writes reached the speaker and then reported a timeout, forever |
| `acquire()` raced the reconnect task | Two GATT clients to one speaker; the orphan held one of its few slots for the process lifetime |
| `frames_written` incremented after the await | The audit record claimed `applied=false` for bytes the speaker had received |
| "ALREADY MATCHED" was claimed about a pre-state never decoded | Unverified and verified had been folded into one |
| Both shelf bands shipped Q=0.7 where the app sends 0.707 | The table was restated in Python instead of read from the APK asset it cites |
| `--apply` had no read-back, no verification, no audit record | The TUI's whole trust story did not exist on the scripted path |

### The patterns behind them

- **The guarantee was a property of the path, not of the API.** Range checking
  lived in one encoder; read-back and audit lived in the TUI. The unguarded paths
  were the ones a user reaches most easily.
- **Authorisation was sampled once and carried.** The generation counter is a
  correct mechanism, checked at the top of a loop that then ran for seconds.
- **State was mutated before it was validated**, so failures left live wreckage:
  a client assigned before subscribing, a link published before connecting.
- **Reasoning true in one domain was applied to another where it is false**: the
  decibel argument on a table index.
- **Tests asserted shape, not behaviour.** The apply gate, the EQ category byte
  and the extended encoder's Q table could each be mutated with the whole suite
  green, because the fake echoed back whatever it was handed.

## Threat and failure review

| Risk | Control | Residual risk |
|---|---|---|
| Wrong protocol sent to a model | PID capability database, `auto_read_frames`, `auto_eq_frames`, range and count validation on every branch | APK data or newer firmware can still differ; run `probe` first |
| Gain outside a model's real range | `auto_eq_frames` bounds every branch against the model's own UI range; `--allow-extended` is needed to exceed it, and only float-parametric protocols accept it at all | Limiter behaviour is firmware-specific, and only the Charge 6 is hardware-confirmed |
| Accidental mutation | CLI dry-run by default; the TUI needs a verified link, and a second confirmation for any boost past the UI range | A confirmed apply writes immediately; raw mode stays expert-only |
| Cached paired device mistaken for a live speaker | Scan rows mark `LIVE` vs `PAIRED CACHE`; only a live connection plus a supported EQ response unlocks EQ | A speaker can stop advertising after verification; a drop revokes access immediately |
| Address or model changed after verification | The verified target is `(address, PID, link generation)`; any of the three changing revokes it, and the generation is re-checked before every frame | BLE identity can change after re-pairing; rescan and verify again |
| Write claimed but not delivered | The TUI and `--apply` both read back and compare band by band, and exit non-zero when they cannot verify | Read-back compares gain only; frequency, Q and category are not re-checked |
| Device identifier leakage | The audit log records a salted per-install pseudonym; APK, captures, config and audit are Git-ignored | `config.json` keeps the last address in plaintext by design, so the whole state directory still links records to a device |
| Corrupt or partial BLE response | Frame length validation, connection-scoped reassembly, single-flight transactions | Protocol 4 group reassembly is bounded by one transaction window |
| Supply chain | Nothing is installed automatically; bounded dependency ranges; project-path vulnerability scan in clean CI | No lockfile or hash pinning yet; a release should add a reviewed lock/SBOM workflow |
| Concurrent app connection | Documented instruction to close the mobile app | OS and firmware arbitration differ by platform |
| Proprietary material published | `.gitignore` and `MANIFEST.in` exclude APK/XAPK/decompiler output | Contributors must still inspect staged files |

## QA layers

- Byte-exact wire tests with golden vectors from the hardware-validated Charge 6
  record: frame headers, the EQ category byte, the sample rate, the band table,
  and the deliberate field-order difference between legacy and Protocol 4.
- A fake speaker that clamps instead of echoing, so the read-back gate can fail.
  Deleting the gate fails the suite; so does moving READ back into the write group.
- Database tests assert 37 APK models and build neutral packets for all 21 that
  declare EQ.
- Profile matrix tests resolve and encode all 87 profiles across every EQ-capable
  PID, and assert no standard profile can exceed the UI range.
- Negative tests cover invalid gain counts, non-integer legacy levels, invalid UI
  steps, unknown PID/preset, malformed configuration, hand-edited profile stores,
  cached/offline devices, and the TUI connection gate.
- Connection tests cover the drop/reconnect race, subscribe failure, single-flight
  connect, stale-client callbacks, and reply demultiplexing against a fake bleak.
- Textual `run_test` covers the locked startup state, verification unlock,
  target-change relock, cached-device rejection, key bindings bypassing the lock,
  and the extended-gain confirmation.
- Hardware verification is opt-in and currently covers JBL Charge 6 PID `20E3`,
  firmware `3.0.7.1`.

## Known limitations

- **Only the Charge 6 is hardware-confirmed.** The other 20 EQ-capable models rest
  on static analysis. This audit can say the code sends what it intends to; it
  cannot say the firmware likes it.
- The protocol was spot-checked against the APK, not systematically diffed. The
  Q=0.707 divergence was found by one comparison against one asset; more of the
  same shape are plausible, and read-back cannot catch them because it compares
  gain only.
- The concurrency findings were traced and unit-tested, not exercised against a
  real BLE stack under load.
- Findings assume Windows/WinRT and the pinned Textual version. Linux/BlueZ and
  macOS/CoreBluetooth are unexamined.
- The audit log is an unsigned local JSONL written by the same process that writes
  EQ. It is evidence for the user, not for anyone else.
- BLE random addresses rotate and should be rescanned.
- No OTA flashing, authentication bypass, factory reset automation, destructive
  fuzzing, A2DP audio processing, or amplifier power change is implemented.

## Release checklist

1. Inspect `git status`; confirm no APK, capture, address, local config or
   generated reverse-engineering output is staged.
2. Run every QA command from the README in a clean virtual environment.
3. Verify version consistency between `pyproject.toml`, `openjbl.__version__` and
   the changelog.
4. Build from a clean tree, install the wheel into a new environment, and
   smoke-test `openjbl --help` and `openjbl-tui`.
5. Tag a signed release; attach only the wheel/sdist, checksums, changelog and
   sanitized documentation.
6. Publish with a scoped PyPI token or Trusted Publishing. Never paste a token
   into a chat, an issue, or a commit.
