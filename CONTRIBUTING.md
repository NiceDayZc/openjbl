# Contributing

## Development setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
ruff check .
ruff format --check .
mypy src/vantadsp
bandit -c pyproject.toml -r src/vantadsp
pip-audit
python -m build
twine check dist/*
```

## Protocol evidence

Every new PID or packet variant must include its evidence source, a sanitized capture, an encoder test with a known byte vector, a parser test where applicable, and whether it was static-only or hardware-confirmed. Never commit APK/XAPK files, decompiler output, personal Bluetooth addresses, or proprietary firmware.

## Safety requirements

- Preserve dry-run as the default for mutations.
- Validate lengths, ranges, category mappings, and model capabilities before I/O.
- Hardware tests should begin with reads, then an exact no-op write/read-back.
- Do not add OTA, reset, auth-bypass, or unrestricted fuzzing to the normal interface.
- Tests must not require real Bluetooth hardware unless explicitly marked and opt-in.
