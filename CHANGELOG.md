# Changelog

All notable changes follow Keep a Changelog style. This project uses semantic versioning while its public API stabilizes.

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
