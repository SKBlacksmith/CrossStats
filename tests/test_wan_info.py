from config import load_config


def test_wan_info_file_path_is_loaded_from_config(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[wan_info]\nfile = "/run/user/1000/pirostats/state/wan-info.json"\n')

    cfg = load_config(path)

    assert cfg.wan_info.file == "/run/user/1000/pirostats/state/wan-info.json"


import json

import sensors


def _wan_file(tmp_path, data):
    p = tmp_path / "wan-info.json"
    p.write_text(json.dumps(data))
    return str(p)


def test_wan_file_parses_fresh_data(tmp_path, monkeypatch):
    now = 1_000_000.0
    monkeypatch.setattr(sensors.time, "time", lambda: now)
    path = _wan_file(tmp_path, {
        "ip": "203.0.113.7", "city": "Moscow", "country": "Russia",
        "isp": "Provider", "updated": now - 60,
    })

    wan = sensors._read_wan_file(path, 900)

    assert wan["ip"] == "203.0.113.7"
    assert sensors._wan_geo_str(wan) == "Moscow, Russia"


def test_wan_file_stale_beyond_max_age_is_rejected(tmp_path, monkeypatch):
    now = 1_000_000.0
    monkeypatch.setattr(sensors.time, "time", lambda: now)
    path = _wan_file(tmp_path, {"ip": "203.0.113.7", "updated": now - 1000})

    assert sensors._read_wan_file(path, 900) is None


def test_wan_file_without_timestamp_is_accepted(tmp_path, monkeypatch):
    # Hand-written files stay usable: no updated field → cannot prove staleness.
    monkeypatch.setattr(sensors.time, "time", lambda: 1_000_000.0)
    path = _wan_file(tmp_path, {"ip": "203.0.113.7", "city": "Moscow"})

    assert sensors._read_wan_file(path, 900)["ip"] == "203.0.113.7"


def test_wan_file_unparsable_or_missing_or_non_object_returns_none(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json {")

    assert sensors._read_wan_file(str(bad), 900) is None
    assert sensors._read_wan_file(str(tmp_path / "absent.json"), 900) is None
    assert sensors._read_wan_file(_wan_file(tmp_path, [1, 2]), 900) is None


def test_wan_geo_str_ignores_missing_fields():
    assert sensors._wan_geo_str({"city": "Moscow"}) == "Moscow"
    assert sensors._wan_geo_str({"city": "Moscow", "country": "Russia"}) == "Moscow, Russia"
    assert sensors._wan_geo_str({}) is None


# ── render / gate wiring (registry) ──────────────────────────────────────────

from config import Config
from formatter import PanelFormatter
from registry import item_gate, render_item
from sensors import HardwareInfo, Readings


def _bare_hw():
    return HardwareInfo(
        cpu_temp_path=None, cpu_freq_path=None, hd_temp_paths={}, fan_paths={},
        battery_sys_ids=[], has_nvidia=False, intel_gpu_freq_path=None, intel_gpu_pci=None,
        net_device="eno1", disk_io_device="sda", cpu_count=4,
        cpu_turbo_supported=False, has_backlight=False, has_wifi=False,
    )


def _wan_fmt():
    cfg = Config()
    cfg.wan_info.file = "/run/user/1000/pirostats/wan-info.json"
    cfg.labels.update({"wan_ip": "WAN IP", "wan_geo": "Geo"})
    return PanelFormatter(cfg, _bare_hw())


def test_wan_ip_row_renders_label_and_value():
    rows = render_item(_wan_fmt(), "wan_ip", Readings(wan_ip="203.0.113.7"), tooltip=True)
    text = " ".join(cell.text for row in rows for cell in row)

    assert "WAN IP" in text
    assert "203.0.113.7" in text


def test_wan_geo_row_renders_label_and_value():
    rows = render_item(_wan_fmt(), "wan_geo", Readings(wan_geo="Moscow, Russia"), tooltip=True)
    text = " ".join(cell.text for row in rows for cell in row)

    assert "Geo" in text
    assert "Moscow, Russia" in text


def test_wan_rows_render_placeholder_without_data():
    fmt = _wan_fmt()
    for metric in ("wan_ip", "wan_geo"):
        rows = render_item(fmt, metric, Readings(), tooltip=True)
        text = " ".join(cell.text for row in rows for cell in row)

        assert rows, f"{metric} renders no row despite a configured file"
        assert "203.0.113" not in text


def test_wan_gate_follows_configured_file():
    assert item_gate(_wan_fmt(), "wan_ip", Readings()) is True
    assert item_gate(_wan_fmt(), "wan_geo", Readings()) is True

    fmt = PanelFormatter(Config(), _bare_hw())
    assert item_gate(fmt, "wan_ip", Readings()) is False


