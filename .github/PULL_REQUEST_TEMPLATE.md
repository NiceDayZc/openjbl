## Summary

## Protocol evidence and affected PID(s)

## Safety impact

- [ ] Mutation still defaults to dry-run or an equivalent explicit guard.
- [ ] No APK, firmware, device address, pairing data, or unsanitized capture is included.
- [ ] Known byte vectors and failure cases have tests.
- [ ] Static-only versus hardware-confirmed behavior is documented.

## QA

- [ ] `pytest`
- [ ] `ruff check . && ruff format --check .`
- [ ] `mypy src/jbl_pc`
- [ ] `bandit -c pyproject.toml -r src/jbl_pc`
- [ ] `python -m build && twine check dist/*`
