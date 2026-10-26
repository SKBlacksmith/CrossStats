from types import SimpleNamespace

import system_info
from system_info import build_system_info, normalize_package_version, parse_pacman_query, parse_vulkan_summary


OS_RELEASE = '''NAME="Arch Linux"
PRETTY_NAME="Arch Linux"
ID=arch
'''
PACMAN_QUERY = '''plasma-workspace 6.8.1-1
kcoreaddons 6.31.0-1
qt6-base 6.12.0-3
mesa 1:26.2.5-1
vulkan-icd-loader 1.4.363.0-1
vulkan-radeon 1:26.2.5-1
'''
VULKAN_SUMMARY = '''Vulkan Instance Version: 1.4.363
    apiVersion         = 1.4.354
    driverName         = radv
    driverInfo         = Mesa 26.2.5-arch1.1
'''


def test_normalize_pacman_package_version_removes_epoch_and_pkgrel():
    assert normalize_package_version("1:26.2.5-1") == "26.2.5"
    assert normalize_package_version("6.8.1-1") == "6.8.1"


def test_parse_pacman_query_keeps_each_installed_package_version():
    assert parse_pacman_query(PACMAN_QUERY) == {
        "plasma-workspace": "6.8.1-1",
        "kcoreaddons": "6.31.0-1",
        "qt6-base": "6.12.0-3",
        "mesa": "1:26.2.5-1",
        "vulkan-icd-loader": "1.4.363.0-1",
        "vulkan-radeon": "1:26.2.5-1",
    }


def test_parse_vulkan_summary_reports_api_and_active_driver():
    assert parse_vulkan_summary(VULKAN_SUMMARY) == ("1.4.363", "1.4.354", "RADV")


def test_build_system_info_orders_os_runtime_and_graphics_versions():
    packages = parse_pacman_query(PACMAN_QUERY)
    assert build_system_info(OS_RELEASE, "7.2.11-arch1-1", packages,
                             parse_vulkan_summary(VULKAN_SUMMARY)) == {
        "os": "Arch Linux",
        "kernel": "7.2.11-arch1-1",
        "plasma": "6.8.1",
        "frameworks": "6.31.0",
        "qt": "6.12.0",
        "mesa": "26.2.5",
        "vulkan": "1.4.363 / 1.4.354 (RADV)",
    }


def test_build_system_info_degrades_cleanly_when_sources_are_missing():
    assert build_system_info("NAME=Unknown\n", "", {}, ("", "", "")) == {
        "os": "Unknown",
        "kernel": "--",
        "plasma": "--",
        "frameworks": "--",
        "qt": "--",
        "mesa": "--",
        "vulkan": "--",
    }


def test_read_system_info_caches_subprocess_probes_for_five_minutes(monkeypatch):
    now = [100.0]
    calls = []
    monkeypatch.setattr(system_info, "_cache_time", float("-inf"))
    monkeypatch.setattr(system_info, "_cache", {})
    monkeypatch.setattr(system_info.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(system_info, "_read_os_release", lambda: OS_RELEASE)
    monkeypatch.setattr(system_info.os, "uname", lambda: SimpleNamespace(release="7.2.11-arch1-1"))

    def fake_run(argv, timeout=3.0):
        calls.append(tuple(argv))
        return PACMAN_QUERY if argv[0] == "pacman" else VULKAN_SUMMARY

    monkeypatch.setattr(system_info, "_run", fake_run)
    first = system_info.read_system_info()
    now[0] += system_info.CACHE_TTL - 1
    second = system_info.read_system_info()
    assert second == first
    assert len(calls) == 2

    now[0] += 2
    system_info.read_system_info()
    assert len(calls) == 4
