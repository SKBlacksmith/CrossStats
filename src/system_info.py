"""Read and format OS, desktop, toolkit and graphics-stack versions.

The package query and Vulkan probe are cached: release versions do not need
poll-interval precision, and launching pacman/vulkaninfo every sensor poll
would be needless work. A five-minute TTL makes upgrades visible while keeping
the normal daemon hot path free of subprocesses.
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path

CACHE_TTL = 300.0
_PACKAGES = (
    "plasma-workspace", "kcoreaddons", "qt6-base", "mesa",
    "vulkan-icd-loader", "vulkan-radeon",
)
_VERSION_FIELDS = {
    "plasma": "plasma-workspace",
    "frameworks": "kcoreaddons",
    "qt": "qt6-base",
    "mesa": "mesa",
}
_cache_time = float("-inf")
_cache: dict[str, str] = {}


def normalize_package_version(version: str) -> str:
    """Drop Arch's epoch and pkgrel, retaining the upstream software version."""
    version = version.rsplit(":", 1)[-1]
    return re.sub(r"-\d+(?:\.\d+)*$", "", version)


def parse_pacman_query(output: str) -> dict[str, str]:
    """Parse `pacman -Q` output; tolerate missing-package diagnostics."""
    result: dict[str, str] = {}
    for line in output.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0] in _PACKAGES:
            result[parts[0]] = parts[1].strip()
    return result


def parse_vulkan_summary(output: str) -> tuple[str, str, str]:
    """Return instance version, physical-device API version and active driver."""
    instance_api = ""
    device_api = ""
    driver_name = ""
    for line in output.splitlines():
        if not instance_api:
            match = re.search(r"Vulkan Instance Version:\s*(\S+)", line)
            if match:
                instance_api = match.group(1)
        match = re.match(r"\s*apiVersion\s*=\s*(\S+)\s*$", line)
        if match:
            device_api = match.group(1)
        match = re.match(r"\s*driverName\s*=\s*(\S.*)\s*$", line)
        if match:
            driver_name = match.group(1).strip()
    return instance_api, device_api, driver_name.upper()



def _parse_os_release(text: str) -> str:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, raw = line.partition("=")
        if not sep or not key or key.startswith("#"):
            continue
        try:
            values = shlex.split(raw, posix=True)
            fields[key] = values[0] if values else ""
        except ValueError:
            fields[key] = raw.strip().strip('"\'')
    return fields.get("PRETTY_NAME") or fields.get("NAME") or "--"


def build_system_info(os_release: str, kernel_release: str,
                      packages: dict[str, str], vulkan: tuple[str, str, str]) -> dict[str, str]:
    """Build the stable display order from OS, active kernel and package/runtime data."""
    values = {name: normalize_package_version(packages[pkg])
              for name, pkg in _VERSION_FIELDS.items() if packages.get(pkg)}
    instance_api, device_api, driver = vulkan
    if instance_api:
        api_versions = instance_api
        if device_api and device_api != instance_api:
            api_versions += " / " + device_api
        values["vulkan"] = f"{api_versions} ({driver})" if driver else api_versions
    elif packages.get("vulkan-icd-loader"):
        values["vulkan"] = "loader " + normalize_package_version(packages["vulkan-icd-loader"])
    else:
        values["vulkan"] = "--"
    return {
        "os": _parse_os_release(os_release),
        "kernel": kernel_release or "--",
        "plasma": values.get("plasma", "--"),
        "frameworks": values.get("frameworks", "--"),
        "qt": values.get("qt", "--"),
        "mesa": values.get("mesa", "--"),
        "vulkan": values["vulkan"],
    }


def _run(argv: list[str], timeout: float = 3.0) -> str:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
        return proc.stdout if proc.returncode == 0 else proc.stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _read_os_release() -> str:
    for path in (Path("/etc/os-release"), Path("/usr/lib/os-release")):
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            continue
    return ""


def read_system_info() -> dict[str, str]:
    """Return a cached snapshot; update it at most once per five minutes."""
    global _cache_time, _cache
    now = time.monotonic()
    if _cache and now - _cache_time < CACHE_TTL:
        return dict(_cache)

    package_output = _run(["pacman", "-Q", *_PACKAGES])
    vulkan_output = _run(["vulkaninfo", "--summary"])
    _cache = build_system_info(
        _read_os_release(), os.uname().release,
        parse_pacman_query(package_output), parse_vulkan_summary(vulkan_output),
    )
    _cache_time = now
    return dict(_cache)
