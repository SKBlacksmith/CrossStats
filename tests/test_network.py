from config import Config, Surface, Section, load_config
from formatter import PanelFormatter
from sensors import HardwareInfo, Readings


def _bare_hw():
    return HardwareInfo(
        cpu_temp_path=None, cpu_freq_path=None, hd_temp_paths={}, fan_paths={},
        battery_sys_ids=[], has_nvidia=False, intel_gpu_freq_path=None, intel_gpu_pci=None,
        net_device="eno1", disk_io_device="sda", cpu_count=4,
        cpu_turbo_supported=False, has_backlight=False, has_wifi=False,
    )


def test_configured_interfaces_are_loaded_in_order(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[network]\ninterfaces = ["eno1", "enp2s0", "usb0"]\n')

    cfg = load_config(path)

    assert cfg.network.interfaces == ["eno1", "enp2s0", "usb0"]


def test_configured_network_speed_rows_identify_each_interface():
    cfg = Config()
    cfg.network.interfaces = ["eno1", "wlp4s0"]
    cfg.tooltip = Surface(sections=[Section(key="io", items=["net_speed"])])
    fmt = PanelFormatter(cfg, _bare_hw())
    readings = Readings(net_speeds={"eno1": (1200, 2400), "wlp4s0": (0, 50)})

    rows = fmt._net_speed(readings, tooltip=True)
    text = " ".join(cell.text for row in rows for cell in row)

    assert "eno1 Up" in text and "eno1 Down" in text
    assert "wlp4s0 Up" in text and "wlp4s0 Down" in text
    assert "1K" in text and "2K" in text
    assert "wlp4s0" in text


def test_configured_network_speed_keeps_interface_names_on_compact_panel():
    cfg = Config()
    cfg.network.interfaces = ["eno1"]
    fmt = PanelFormatter(cfg, _bare_hw())
    readings = Readings(net_speeds={"eno1": (1000, 2000)})

    rows = fmt._net_speed(readings, tooltip=False)
    text = " ".join(cell.text for row in rows for cell in row)

    assert "eno1 Up" in text and "eno1 Down" in text


def test_configured_interface_gate_does_not_require_a_default_route():
    cfg = Config()
    cfg.network.interfaces = ["usb0"]
    hw = _bare_hw()
    hw.net_device = None
    fmt = PanelFormatter(cfg, hw)

    assert not fmt._available("net_speed", Readings())
    assert fmt._available("net_speed", Readings(net_speeds={"usb0": (0, 0)}))


def test_legacy_network_speed_keeps_active_route_layout():
    cfg = Config()
    fmt = PanelFormatter(cfg, _bare_hw())
    readings = Readings(net_up_bps=1200, net_down_bps=2400)

    rows = fmt._net_speed(readings, tooltip=True)
    text = " ".join(cell.text for row in rows for cell in row)

    assert "eno1 Up" not in text
    assert len(rows) == 1
    assert "1K" in text and "2K" in text

def test_configured_network_speed_no_rows_if_none_present():
    cfg = Config()
    cfg.network.interfaces = ["usb0"]
    fmt = PanelFormatter(cfg, _bare_hw())
    readings = Readings(net_speeds={})

    assert fmt._net_speed(readings, tooltip=True) == []
