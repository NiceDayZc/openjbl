"""PyPI-backed version checks and self-update support."""

from __future__ import annotations

import json
import re
import subprocess  # nosec B404
import sys
from dataclasses import asdict, dataclass
from importlib import metadata
from urllib.request import Request, urlopen

from . import __version__

PYPI_JSON_URL = "https://pypi.org/pypi/openjbl/json"
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[.-]?(a|b|rc)(\d+))?$")


@dataclass(frozen=True)
class UpdateResult:
    current: str
    latest: str | None
    status: str
    message: str
    installed: bool = False

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _version_key(value: str) -> tuple[int, int, int, int, int]:
    match = _VERSION_RE.fullmatch(value.strip())
    if match is None:
        raise ValueError(f"unsupported version string {value!r}")
    major, minor, patch = (int(match.group(index)) for index in range(1, 4))
    stage = {None: 3, "rc": 2, "b": 1, "a": 0}[match.group(4)]
    serial = int(match.group(5) or 0)
    return major, minor, patch, stage, serial


def is_editable_install() -> bool:
    """Return whether this interpreter imports OpenJBL from an editable checkout."""
    try:
        direct_url = metadata.distribution("openjbl").read_text("direct_url.json")
        if not direct_url:
            return False
        data = json.loads(direct_url)
        return bool(data.get("dir_info", {}).get("editable"))
    except (metadata.PackageNotFoundError, json.JSONDecodeError, AttributeError):
        return False


def fetch_latest_version(timeout: float = 5.0) -> str:
    request = Request(PYPI_JSON_URL, headers={"User-Agent": f"OpenJBL/{__version__} update-check"})
    with urlopen(request, timeout=timeout) as response:  # nosec B310
        data = json.load(response)
    latest = str(data["info"]["version"])
    _version_key(latest)
    return latest


def check_for_update(*, current: str = __version__, timeout: float = 5.0) -> UpdateResult:
    latest = fetch_latest_version(timeout)
    if _version_key(latest) > _version_key(current):
        return UpdateResult(current, latest, "update-available", f"OpenJBL {latest} is available")
    if _version_key(latest) == _version_key(current):
        return UpdateResult(current, latest, "up-to-date", f"OpenJBL {current} is current")
    return UpdateResult(current, latest, "ahead-of-pypi", f"local {current} is newer than PyPI {latest}")


def check_for_update_safe(*, current: str = __version__, timeout: float = 5.0) -> UpdateResult:
    try:
        return check_for_update(current=current, timeout=timeout)
    except Exception as exc:
        return UpdateResult(current, None, "check-failed", f"{type(exc).__name__}: {exc}")


def install_version(version: str, *, timeout: float = 180.0) -> UpdateResult:
    _version_key(version)
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--no-input",
        "--disable-pip-version-check",
        f"openjbl=={version}",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)  # nosec B603
    if completed.returncode:
        detail = (completed.stderr or completed.stdout or "pip failed").strip().splitlines()[-1]
        return UpdateResult(__version__, version, "install-failed", detail)
    return UpdateResult(__version__, version, "installed", f"OpenJBL {version} installed; restart required", True)


def auto_update(*, timeout: float = 5.0) -> UpdateResult:
    if is_editable_install():
        return UpdateResult(
            __version__, None, "editable-skip", "editable development install; automatic update skipped"
        )
    check = check_for_update_safe(timeout=timeout)
    if check.status != "update-available" or check.latest is None:
        return check
    try:
        return install_version(check.latest)
    except (OSError, subprocess.SubprocessError) as exc:
        return UpdateResult(__version__, check.latest, "install-failed", f"{type(exc).__name__}: {exc}")


def update_now(*, timeout: float = 5.0) -> UpdateResult:
    """Run an explicit update, including from an editable environment."""
    check = check_for_update_safe(timeout=timeout)
    if check.status != "update-available" or check.latest is None:
        return check
    try:
        return install_version(check.latest)
    except (OSError, subprocess.SubprocessError) as exc:
        return UpdateResult(__version__, check.latest, "install-failed", f"{type(exc).__name__}: {exc}")
