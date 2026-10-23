from types import SimpleNamespace

import sensors
from sensors import DaemonState


def _counter(tx, rx):
    return SimpleNamespace(bytes_sent=tx, bytes_recv=rx)


def test_configured_interfaces_sample_when_present_even_if_link_is_down(tmp_path, monkeypatch):
    net_root = tmp_path / "net"
    for name in ("eno1", "enp2s0"):
        (net_root / name).mkdir(parents=True)
    (net_root / "enp2s0" / "operstate").write_text("down\n")
    monkeypatch.setattr(sensors, "SYS_CLASS_NET", net_root)

    samples = [
        {"eno1": _counter(100, 200), "enp2s0": _counter(0, 0), "usb9": _counter(99, 99)},
        {"eno1": _counter(500, 600), "enp2s0": _counter(0, 0), "usb9": _counter(99, 99)},
    ]
    monkeypatch.setattr(sensors.psutil, "net_io_counters", lambda pernic=True: samples.pop(0))
    now = [10.0]
    monkeypatch.setattr(sensors.time, "monotonic", lambda: now[0])
    state = DaemonState()

    first = sensors._read_configured_net_speeds(state, ["eno1", "enp2s0", "usb9"])
    now[0] += 2.0
    second = sensors._read_configured_net_speeds(state, ["eno1", "enp2s0", "usb9"])

    assert list(first) == ["eno1", "enp2s0"]
    assert first["enp2s0"] == (None, None)
    assert second == {"eno1": (200, 200), "enp2s0": (0, 0)}


def test_reappearing_interface_starts_with_fresh_baseline(tmp_path, monkeypatch):
    net_root = tmp_path / "net"
    iface = net_root / "usb0"
    iface.mkdir(parents=True)
    monkeypatch.setattr(sensors, "SYS_CLASS_NET", net_root)
    counters = {"usb0": _counter(100, 200)}
    monkeypatch.setattr(sensors.psutil, "net_io_counters", lambda pernic=True: counters)
    now = [1.0]
    monkeypatch.setattr(sensors.time, "monotonic", lambda: now[0])
    state = DaemonState()

    sensors._read_configured_net_speeds(state, ["usb0"])
    iface.rmdir()
    now[0] += 10.0
    assert sensors._read_configured_net_speeds(state, ["usb0"]) == {}
    iface.mkdir()
    counters["usb0"] = _counter(100_000, 200_000)
    now[0] += 1.0

    assert sensors._read_configured_net_speeds(state, ["usb0"]) == {"usb0": (None, None)}


def test_counter_reset_rebaselines_without_emitting_negative_rate(tmp_path, monkeypatch):
    net_root = tmp_path / "net"
    (net_root / "eno1").mkdir(parents=True)
    monkeypatch.setattr(sensors, "SYS_CLASS_NET", net_root)
    counters = {"eno1": _counter(100, 200)}
    monkeypatch.setattr(sensors.psutil, "net_io_counters", lambda pernic=True: counters)
    now = [1.0]
    monkeypatch.setattr(sensors.time, "monotonic", lambda: now[0])
    state = DaemonState()

    sensors._read_configured_net_speeds(state, ["eno1"])
    counters["eno1"] = _counter(10, 20)
    now[0] += 2.0
    reset = sensors._read_configured_net_speeds(state, ["eno1"])
    counters["eno1"] = _counter(50, 80)
    now[0] += 2.0
    after_reset = sensors._read_configured_net_speeds(state, ["eno1"])

    assert reset == {"eno1": (None, None)}
    assert after_reset == {"eno1": (20, 30)}


def test_invalid_interface_name_is_ignored(tmp_path, monkeypatch):
    net_root = tmp_path / "net"
    (net_root / "eno1").mkdir(parents=True)
    monkeypatch.setattr(sensors, "SYS_CLASS_NET", net_root)
    monkeypatch.setattr(sensors.psutil, "net_io_counters", lambda pernic=True: {
        "eno1": _counter(1, 1), "../outside": _counter(2, 2)})

    result = sensors._read_configured_net_speeds(DaemonState(), ["eno1", "../outside"])

    assert list(result) == ["eno1"]
