# Security policy

## Supported versions

Only the latest release on the default branch receives security fixes.

## Reporting

Do not publish device identifiers, Bluetooth captures, pairing material, or a working destructive packet in a public issue. Use GitHub's private security advisory feature for vulnerabilities. Include the affected version, platform, reproduction steps, impact, and a sanitized capture if needed.

## Device safety boundary

This project supports documented EQ inspection/control only. OTA flashing, authentication bypass, factory reset automation, hidden diagnostic commands, and destructive fuzzing are out of scope. Mutation commands default to dry-run. The TUI requires a switch and an exact `APPLY` confirmation, and stores only a SHA-256-derived target fingerprint in its audit log.

Bluetooth addresses and manufacturer data can identify hardware. They are excluded by `.gitignore`; sanitize logs before sharing.
