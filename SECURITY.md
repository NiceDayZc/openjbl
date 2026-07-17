# Security policy

## Supported versions

Only the latest release on the default branch receives security fixes.

## Reporting

Do not publish device identifiers, Bluetooth captures, pairing material, or a working destructive packet in a public issue. Use GitHub's private security advisory feature for vulnerabilities. Include the affected version, platform, reproduction steps, impact, and a sanitized capture if needed.

## Device safety boundary

This project supports documented EQ inspection and control only. OTA flashing, authentication bypass, factory reset automation, hidden diagnostic commands, and destructive fuzzing are out of scope.

Writes are guarded on every path:

- CLI mutation commands default to dry-run and need `--apply`.
- Gains outside the model's own UI range are refused unless `--allow-extended` is passed, and the TUI requires a second confirmation before writing a boost past it.
- The TUI keeps EQ locked until a live connection answers with a supported EQ response, and revokes that authorisation if the link drops.
- Both the TUI and `--apply` read the EQ back and compare it band by band before reporting success, and exit non-zero when they cannot.

## Updates

OpenJBL never installs anything by itself. The TUI can check PyPI and report that a newer release exists; `openjbl update` installs one when you ask for it.

This is deliberate. Auto-installing an unpinned, unhashed version at launch would turn a single compromise of one PyPI account into code execution on every machine running OpenJBL, and pip would be rewriting the live interpreter's site-packages under a process that is about to drive a radio.

## What the audit log does and does not hide

`audit.jsonl` records a **salted pseudonym** of the target, not its address. The salt is 32 random bytes generated per installation and kept in `audit-salt` beside the log.

The salt is load-bearing. A Bluetooth address is only 48 bits, the vendor OUI is public, and an unsalted hash of one falls to a brute-force search of the remaining 24 bits in about two seconds of ordinary single-threaded Python. Hashing alone would not have hidden anything.

**This is a pseudonym, not anonymisation.** Anyone with the whole `%LOCALAPPDATA%\openjbl\` directory can still link records to a device: `config.json` stores the last address in plaintext, because the tool has to reconnect to it. The property the salt buys is narrower and specific: `audit.jsonl` on its own is safe to attach to a bug report.

Bluetooth addresses and manufacturer data identify hardware. Local configuration, captures and audit logs are excluded by `.gitignore`. Sanitize anything else before sharing.
