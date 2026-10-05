# Changelog

All notable changes follow Keep a Changelog style. This project uses semantic versioning while its public API stabilizes.

## [Unreleased]

### Added

- **`openjbl-gui`: a desktop GUI in the browser.** A black-and-white shadcn/ui front end (`pip install "openjbl[gui]"`) over the same verified write path as the TUI: the equalizer stays locked until a live link answers with a supported EQ response, every write is read back band by band, and a boost past +6 dB needs an explicit confirmation. It draws the response of the speaker's real filter chain as you drag the per-band sliders, overlays what the speaker reports on a read, and shows the per-band read-back after each write. The server binds to 127.0.0.1 only, and every API call must carry a per-launch token embedded in the page it served and name a loopback Host, so neither another site in the same browser nor a DNS-rebinding page can drive the speaker.
- **A room family of LAB curves around Harman Room Curve.** Five more published in-room targets, each the sound of a kind of room: Harman Listener Target (Olive, Welti & McMullin 2013 -- the listening test behind the Harman curve), B&K House Curve (1974 hi-fi room), Music Studio Room (Dolby Atmos Music target), Cinema X-Curve (SMPTE ST 202, large room) and Vocal Bloom Room (Archimago 2026). Fitted the same way as the other LAB curves; Toole's reflective-room estimate was left out because it lands within a dB of B&K.

### Fixed

- **The GUI could not connect a speaker that did not advertise its model.** A Charge 6 that is paired to a phone sends only a Fast Pair frame and the name `JBLSBIC`, so detection has no PID; auto-setup rightly declines, but the page then offered a disabled Connect button and no way out. Such a speaker now gets a model picker, defaulting to the last model used, and the read-only probe that follows still refuses anything that is not that model. The device list shows JBL speakers only, with the rest one click away.
- **The GUI's default port moved from 8765 to 47800.** 8765 is a common development port; when it was taken the server moved to the next free one, but the documented address then pointed at someone else's server.

### Changed

- **The write transaction moved to `openjbl.eqwrite`** so the TUI and the GUI run one implementation of the path that changes hardware, and auto speaker selection moved to `discovery.pick_auto_candidate`. TUI behaviour is unchanged.
- **The profile catalog is curated down from 88 curves to 13, one per job.** Five standard profiles (Flat, Balanced, Bass Heavy, Vocal Focus, Outdoor) cover every EQ model at full volume. Eight cut-only LAB profiles cover the jobs: Harman Room Curve, Hi-Fi Clarity, Deep Clean Bass, Vocal Presence, Cinema Dialogue, Podcast & Speech, Gaming Footsteps and Late Night. The 18 bench-test boosts of +18 to +24 dB are gone -- the extended range distorts on a boost, which is why the cut-based curves were added in the first place -- along with genre presets and overlapping variants of the same tilt. A boost typed into the gain field is still accepted behind the DANGER confirmation.
- **The six new LAB curves were fitted, not hand-picked.** Each started as a continuous target response, and its gains were solved for against the Charge 6's real filter chain (125 Hz low shelf, Q2 peaks at 250 Hz-4 kHz, 8 kHz high shelf, 48 kHz), then rounded to 0.5 dB. Q2 peaks an octave apart ripple by 2-3 dB between centres when several are cut together, so a curve chosen band by band is not the response that ships. `docs/PROFILES.md` now lists the computed response at the in-between frequencies too.

A whole-system adversarial audit raised 46 findings; 29 survived refutation. 0.3.0 was built but never published, so nothing below ever reached a user.

### Security

- **The audit log's device pseudonym is now salted.** It was an unsalted SHA-256 of the address, which hides nothing: a Bluetooth address is 48 bits, the vendor OUI is public, and the remaining 24 bits fall to a brute-force search in about two seconds of ordinary single-threaded Python -- measured, not estimated. A 32-byte per-install salt now makes `audit.jsonl` safe to attach to a bug report on its own. It is still a pseudonym and not anonymisation: `config.json` keeps the last address in plaintext because the tool has to reconnect to it, and SECURITY.md now says so instead of implying otherwise.
- **The TUI no longer installs anything.** `auto_update` defaulted to true and ran `pip install` at launch against an unpinned, unhashed PyPI version with no prompt, so one compromise of one PyPI account meant code execution on every machine running OpenJBL -- while pip rewrote the live interpreter's site-packages under a process about to open a GATT link and write EQ. It now reports that a release exists; `openjbl update` installs when asked. The default is off entirely.
- `install_version` validated a stripped copy of the version string and then passed the unstripped original to pip. It now validates exactly what it passes.

### Fixed

- **`set-auto` wrote +/-24 dB with no opt-in on 16 of 21 models.** The gain range was checked inside the Charge 6 branch, so every other model reached the wire with whatever the caller passed -- `set_simple_eq` and `set_advanced_levels` only check that a value fits in a signed byte, which is a fact about the wire, not about the speaker. The check now lives in `auto_eq_frames` and applies to every branch; `set-auto` gained the `--allow-extended` flag `set-profile` already had.
- **The extended-gain confirmation used a decibel argument on encoders that do not carry decibels.** "A cut cannot clip" holds for float-parametric gains; on `EQ_BALANCE` and `PRESET_EQ` models the wire value is an index into a firmware table, where -100 is not "very quiet" but an entry that does not exist. Those models now confirm on magnitude in either direction.
- **Pressing `r` cancelled an apply after the frame was already on the wire.** READ and APPLY shared an exclusive worker group, so one keystroke discarded the readback that the whole apply path exists to produce. Read has its own group.
- **`apply_worker` authorised once and kept writing across a reconnect that had already revoked it.** The link generation is now re-checked before every frame.
- **A failed subscription cached a connected but deaf link forever**: writes reached the speaker and then reported a timeout, because the reply had nowhere to arrive. `connect()` now publishes nothing until the subscription is up, and disconnects on failure.
- **`acquire()` raced the reconnect task**, building a second GATT client to one speaker and orphaning the first permanently -- speakers cap concurrent links -- while invalidating a link that was up. `connect()` is single-flight and `acquire()` joins an in-flight recovery instead of racing it.
- The audit record claimed `applied=false` for frames the speaker had already received, because the counter incremented after the await rather than before the write.
- "ALREADY MATCHED" was claimed about a pre-write state that was never decoded; unverified and verified had been folded together. Three states are now reported as three.
- The EQ lock disabled the buttons, but key bindings do not consult `disabled`, so `r`/`v`/`w` bypassed it entirely. `check_action` gates them.
- An empty MY PROFILES tier parked the dropdown on a sentinel that is not a profile, and the next model change raised `ValueError` out of the Textual message pump and killed the app.
- `curve_from_model_gains`' band-count check compared a list against itself, so `--gains 5 3 -2` on a seven-band speaker silently padded four bands the user never entered.
- The saved-profile loader trusted the length that save enforced, so a hand-edited `profiles.json` raised `IndexError` past every handler.
- **Both shelf bands went to hardware with Q=0.7 where the app sends 0.707** -- including on the extended-gain path. The band table is now read from the APK's own `custom_c2_eq.json` instead of restated in Python, which is how it drifted.
- `openjbl set-auto --apply` and `set-profile --apply` now read the EQ back, compare it band by band, write an audit record, and exit non-zero on a rejected or unverified write. Only the TUI did that before; the CLI printed reply bytes and exited 0.
- README's Python API example raised `ImportError`, its `set-parametric` example exited 2, its `decode` example was a byte short, it documented 24 of 87 profiles, and it told users to press a button that does not exist. Every offline example in the README is now executed by hand against the built package.

### Documentation

- Rewrote the README around what a reader needs first: the first runnable command moved from line 55 to line 19, and the 1066-character paragraph that covered the workspaces, the lock, the apply flow, the verification outcomes and the audit record in one breath is now a scannable safety list plus a section for what "verified" actually means. Fixed the screenshot, which pointed at a file the rename had missed.
- `docs/PROFILES.md` is generated from the code and documents all 87 profiles; it had covered 24 and predated the LAB tier entirely.
- `docs/PROTOCOL.md` now documents which reply answers which request, taken from each SDK command class's own `getResponseCommands()`. The advanced setters are answered by the `99` RET frame rather than a `DEV_ACK`, which is exactly the asymmetry that gets guessed wrong.
- `docs/AUDIT.md` covers the current tree and the whole-system audit. It had been a 0.2.4 record with today's numbers pasted into it.
- `docs/DEVICE_CHARGE6_20E3.md` records the unresolved shelf Q question: it read `0.7` off the hardware, the APK asset ships `0.707`, and the code now sends `0.707`. Which the firmware holds is unknown, and the doc says so rather than quietly disagreeing with the code.

### Added

- Byte-exact wire tests (`tests/test_wire_format.py`) with golden vectors from the hardware-validated Charge 6 record, plus a non-echoing fake speaker that clamps like real firmware. The apply gate, the C2 category byte and the extended encoder's frequency/Q table could each be mutated with the whole suite green; they now fail.

## [0.3.0] - 2026-07-17

### Changed

- **Renamed the project to OpenJBL.** The import package is now `openjbl`, and the console commands are `openjbl` and `openjbl-tui` (previously `vantactl` and `vantatui`).
- **The BLE link is now held open instead of being rebuilt for every frame.** Previously each frame opened and destroyed its own connection -- the CLI even created a fresh event loop per frame -- which made multi-frame writes slow and turned any transient blip into a hard failure. One link per address is now held for the session, matching the Android app, which keeps a single GATT open for its whole process lifetime.
- Notifications are subscribed once per link and left subscribed, as the app does, rather than being re-subscribed and torn down around every transaction.

### Added

- **MY PROFILES**: a third profile tier for curves you make yourself. Edit the gains, press SAVE AS, name it, and it is stored in `profiles.json` next to the config and offered back on every launch. `openjbl save-profile`, `openjbl profiles --mine`, and `openjbl delete-profile` do the same from the CLI. A saved profile is kept as a seven-point tonal curve rather than one speaker's band values, so it still means something on a model with a different band count. Whether a saved curve needs the extended encoder, and whether it needs the extended-gain confirmation, are recomputed from the gains on load rather than trusted from the file -- a hand-edited store cannot talk a +24 dB curve past the confirmation.
- A nine-strong LAB reference family aimed at clean, uncoloured playback: the Harman room curve (Harman's own listener panels -- JBL is Harman -- found people prefer an in-room low shelf under a gentle downward tilt over a literally flat response), a steeper studio tilt, and corrections that take the shop-shelf smiley back off (neutral correction, studio reference, tight bass, detail without glare, silk treble, vocal purity, late-night hi-fi). EQ cannot buy a better driver or more resolution; what it can do is remove colouration, and an expensive speaker is largely defined by that absence -- no port boom, no boxiness, no upper-mid shout, no fake sizzle. Every curve in the family is cuts only and leaves the midrange as the band it protects.
- Thirty-four subtractive LAB profiles, taking the catalog to 87. They spend the extended range on cuts rather than boosts: a ten-strong bass family (tilts from mild to extreme, plus punch, warm, 808, dub, club, basshead and sub-focus), genre curves, placement fixes (corner, shelf, desk, tiled room, outdoors), use-case curves (game footsteps, movie dialogue), and single-problem repairs (rumble, honk, hiss, sibilance, mud, harshness, driver protection). The twenty original LAB profiles all push +18 to +24 dB, which is the one thing the extended range is bad at: a large boost has to come out of the DSP's headroom and the speaker's limiter, so it distorts and then gets quieter. The bass family instead leaves 125 Hz at 0 dB and lowers everything above it -- the tilt is what the ear hears as bass, and a tilt built from cuts costs level, which the volume knob gives back, instead of headroom, which it cannot.
- Automatic setup: one press of SCAN picks the strongest live JBL, connects, verifies the EQ route, and opens the Equalizer. It declines to choose when the signal is too weak or two speakers are within 6 dB, and it never writes.
- Automatic recovery from an unexpected drop: a flat 1 s retry, three attempts, straight to the cached address with no re-scan -- the app's exact strategy. No keepalive is sent, because the app has none.
- A reply demultiplexer built from each SDK command class's own declared response commands, so a push from the speaker can no longer be counted as a write acknowledgement.

### Fixed

- **EQ writes could be acknowledged by an unrelated notification.** Any frame arriving in the timeout window counted as an acknowledgement, so an unsolicited `NOTIFY_EQ_CHANGE` could make an unverified write look verified.
- **Verification authorised an address, not a link.** The probe's connection was already closed before the write opened a new one, so "verified" described a link that no longer existed. It is now bound to the live link's identity and revoked the moment that link drops.
- **A dropped link during a probe was reported as "no supported EQ response"**, blaming the speaker for lacking a capability when the connection had simply died.
- **A programmatically selected model could be paired with the previous model's gains.** `Select.Changed` is posted rather than called, so a chained scan could have written the wrong band shape to real hardware. The write path now resolves its identity once, up front, and never re-reads the widgets.
- The dangerous-profile arm is keyed to the profile and gains it was armed for, so any edit between the two clicks invalidates it instead of a queued event silently clearing it.
- **A hand-typed +24 dB wrote on a single click.** The confirmation was keyed to the selected profile's name, but the gain field is free text, so leaving the tier on STANDARD and typing +24 skipped it entirely on any float-parametric model. It now follows the actual gains. Conversely, the confirmation is no longer demanded for curves that only cut: needing it to apply a -12 dB corner correction was crying wolf, which is what makes people stop reading the real warnings.
- Workers no longer share one exclusive group, so they can no longer cancel each other; a cancelled apply still writes its audit record, and pressing SCAN at launch no longer cancels the update check while its `pip` install keeps running.
- Four UI messages pointed the user at a "CONNECT + VERIFY" button that does not exist.

## [0.2.4] - 2026-07-16

### Fixed

- Locked the Equalizer tab and every EQ control until a live connection and supported EQ response are verified.
- Invalidated the verified target whenever the address/model changes or a read/write connection fails.
- Distinguished live BLE advertisements from cached Windows paired-device metadata and stopped auto-selecting offline cache rows.
- Added a strict post-connect `is_connected` transport check and cleared stale clients after disconnect.
- Replaced theme-colored Footer elements and DataTable/scrollbar accents with deterministic monochrome styling.

## [0.2.3] - 2026-07-16

### Changed

- Added the installed version and release build ID to the always-visible TUI header.
- Added version/build identity to the Activity startup log for support screenshots and diagnostics.

## [0.2.2] - 2026-07-16

### Changed

- Reworked the TUI into a guided Scan, Select, Probe, Tune, Preview, and Apply workflow.
- Replaced Unicode-heavy borders, separators, and curve blocks with legacy-console-safe ASCII.
- Added visible success, warning, and error notifications plus direct `1`/`2`/`3` workspace shortcuts.
- Reduced nested framing and verified the interface at an 80x24 terminal size.
- Added automatic JBL/PID selection from Harman company data, `DFFD`/`FDDF`/`FC69` service data, derived service UUIDs, unique names, and Windows paired-device metadata.
- Replaced the TUI write interlock with direct apply while retaining model and gain validation.
- Added pre-write state capture, write acknowledgement inspection, automatic read-back, per-band delta verification, transaction IDs, detailed Activity evidence, and explicit verified/mismatch/unverified outcomes.
- Added automatic PyPI update checks/installations for TUI users, editable-install protection, and manual `check-update` / `update` CLI commands.

## [0.2.1] - 2026-07-16

### Changed

- Rebranded the distribution, Python package, CLI, TUI, documentation, and repository as VantaDSP (renamed again to OpenJBL in 0.3.0).
- Published the project on PyPI with `pip install vantadsp` as the primary installation path.

## [0.2.0] - 2026-07-16

### Added

- Textual TUI with BLE discovery, model selection, read-only probe, EQ read, packet preview, guarded apply, and privacy-aware audit logging.
- Monochrome workstation layout with detailed system/device/protocol/safety state, live curve display, and 24 curated model-aware sound profiles.
- `profiles` and `set-profile` CLI commands with frequency interpolation and per-model gain quantization.
- PID-based routing across legacy simple, advanced level, legacy parametric, Protocol 4 `0E02`, and Grip-style `0E7F` EQ.
- Persistent local settings, typed package marker, build metadata, CI, lint, typing, security, coverage, and packaging checks.
- Full model coverage matrix and hardware-confirmed Charge 6 profile.

### Safety

- Writes remain dry-run in the CLI and double-confirmed in the TUI.
- APKs, captures, decompiler output, and local audit/config data are excluded from Git.

## [0.1.0] - 2026-07-16

- Initial BLE/SPP transport, packet codecs, model database, CLI, and Charge 6 validation.
