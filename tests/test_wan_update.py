import io
import json
import time

import pytest

import wan_update
from wan_update import _normalize, fetch, update, write


def _opener(return_value=None, exc=None):
    def open_(url, timeout=None):
        if exc is not None:
            raise exc
        return io.BytesIO(json.dumps(return_value).encode())
    return open_


# ── _normalize: one shape per provider ────────────────────────────────────────

def test_normalize_ipwho_reads_connection_isp():
    info = _normalize("https://ipwho.is/", {
        "ip": "203.0.113.7", "city": "Moscow", "country": "Russia",
        "connection": {"isp": "Provider Ltd"},
    })
    assert info == {"ip": "203.0.113.7", "city": "Moscow", "country": "Russia",
                    "isp": "Provider Ltd"}


def test_normalize_ipinfo_strips_asn_from_org():
    info = _normalize("https://ipinfo.io/json", {
        "ip": "203.0.113.7", "city": "Moscow", "country": "RU",
        "org": "AS12345 Provider Ltd",
    })
    assert info["isp"] == "Provider Ltd"
    assert info["country"] == "RU"


def test_normalize_ifconfig_reads_asn_org():
    info = _normalize("https://ifconfig.co/json", {
        "ip": "203.0.113.7", "city": "Moscow", "country": "Russia",
        "asn_org": "Provider Ltd",
    })
    assert info["isp"] == "Provider Ltd"


def test_normalize_ipwho_failed_lookup_yields_empty_ip():
    info = _normalize("https://ipwho.is/", {"success": False, "ip": "", "connection": {}})
    assert info["ip"] == ""


# ── fetch: first working endpoint wins ────────────────────────────────────────

def test_fetch_uses_first_working_endpoint():
    payloads = iter([
        {"ip": "203.0.113.7", "city": "Moscow", "country": "Russia", "connection": {"isp": "P"}},
        {"ip": "198.51.100.1", "city": "X", "country": "Y"},
    ])
    seen = []
    def open_(url, timeout=None):
        seen.append(url)
        return io.BytesIO(json.dumps(next(payloads)).encode())

    info = fetch(("https://ipwho.is/", "https://ipinfo.io/json"), urlopen=open_)

    assert info["ip"] == "203.0.113.7"
    assert seen == ["https://ipwho.is/"]


def test_fetch_falls_through_on_transport_error():
    payloads = iter([None, {"ip": "198.51.100.1", "city": "X", "country": "Y"}])
    def open_(url, timeout=None):
        payload = next(payloads)
        if payload is None:
            raise OSError("unreachable")
        return io.BytesIO(json.dumps(payload).encode())

    info = fetch(("https://ipwho.is/", "https://ipinfo.io/json"), urlopen=open_)

    assert info["ip"] == "198.51.100.1"


def test_fetch_returns_none_when_all_endpoints_fail():
    def open_(url, timeout=None):
        raise OSError("unreachable")

    assert fetch(("https://a/", "https://b/"), urlopen=open_) is None


def test_fetch_skips_payload_without_ip():
    payloads = iter([
        {"success": False, "ip": "", "connection": {}},
        {"ip": "198.51.100.1", "city": "X", "country": "Y"},
    ])
    def open_(url, timeout=None):
        return io.BytesIO(json.dumps(next(payloads)).encode())

    assert fetch(("https://ipwho.is/", "https://ipinfo.io/json"), urlopen=open_)["ip"] == "198.51.100.1"


# ── write: atomic replace + updated timestamp ─────────────────────────────────

def test_write_records_timestamp_and_leaves_no_temp_files(tmp_path, monkeypatch):
    monkeypatch.setattr(wan_update.time, "time", lambda: 1234.0)
    path = tmp_path / "wan-info.json"

    write(str(path), {"ip": "203.0.113.7", "city": "Moscow"})

    assert json.loads(path.read_text()) == {
        "ip": "203.0.113.7", "city": "Moscow", "updated": 1234}
    assert [p.name for p in tmp_path.iterdir()] == ["wan-info.json"]


# ── update: one refresh cycle ─────────────────────────────────────────────────

def test_update_writes_the_file_on_success(tmp_path, monkeypatch):
    monkeypatch.setattr(wan_update, "fetch",
                        lambda: {"ip": "203.0.113.7", "city": "Moscow",
                                 "country": "Russia", "isp": "P"})
    path = tmp_path / "wan-info.json"

    assert update(str(path)) is True
    assert json.loads(path.read_text())["ip"] == "203.0.113.7"


def test_update_fails_without_touching_previous_file(tmp_path, monkeypatch):
    monkeypatch.setattr(wan_update, "fetch", lambda: None)
    path = tmp_path / "wan-info.json"
    path.write_text("previous")

    assert update(str(path)) is False
    assert path.read_text() == "previous"
