# Security policy

## Supported versions

Only the latest release on the default branch receives security fixes.

## Reporting

Do not publish device identifiers, Bluetooth captures, pairing material, or a working destructive packet in a public issue. Use GitHub's private security advisory feature for vulnerabilities. Include the affected version, platform, reproduction steps, impact, and a sanitized capture if needed.

## Device safety boundary

This project supports documented EQ inspection/control only. OTA flashing, authentication bypass, factory reset automation, hidden diagnostic commands, and destructive fuzzing are out of scope. CLI mutation commands default to dry-run. The TUI uses direct apply after model and gain validation and stores only a SHA-256-derived target fingerprint in its audit log.

Bluetooth addresses and manufacturer data can identify hardware. They are excluded by `.gitignore`; sanitize logs before sharing.
