"""Desktop geometry and fit: the desktop widget publishes usable/advance/fit in
DESKTOP_GEOM_FILE; the daemon prefers its advance for the graphs page and, in fit
mode, renders the pages to the published width. The panel's geom file (GEOM_FILE)
is untouched by all of this — a desktop-only setup must not need one."""

import pytest

import config
from config import (
    DESKTOP_WIDTH_MAX,
    TOOLTIP_WIDTH_FLOOR,
    _apply_desktop_width,
    _read_desktop_geom,
    apply_canonical_width,
)


class _Cfg:
    """Minimal stand-in: the width path only touches display.tooltip_width and
    pages.graph_width."""

    def __init__(self, width=50, graph=0):
        self.display = type("D", (), {"tooltip_width": width})()
        self.pages = type("P", (), {"graph_width": graph})()


def _publish(monkeypatch, tmp_path, text):
    f = tmp_path / "geom-desktop"
    f.write_text(text)
    monkeypatch.setattr(config, "DESKTOP_GEOM_FILE", f)


def _panel(monkeypatch, tooltip_adv):
    monkeypatch.setattr(config, "detect_panel_geometry",
                        lambda: config.PanelGeometry(tooltip_adv=tooltip_adv))


# ── Reading DESKTOP_GEOM_FILE ────────────────────────────────────────────────

def test_reads_usable_advance_and_fit(monkeypatch, tmp_path):
    _publish(monkeypatch, tmp_path, "960 8.0 1\n")
    desk = _read_desktop_geom()
    assert desk.usable_px == pytest.approx(960)
    assert desk.glyph_adv == pytest.approx(8.0)
    assert desk.fit is True


def test_fit_flag_zero_is_read_as_off(monkeypatch, tmp_path):
    _publish(monkeypatch, tmp_path, "960 8.0 0\n")
    assert _read_desktop_geom().fit is False


def test_absent_file_is_none():
    assert _read_desktop_geom() is None


@pytest.mark.parametrize("text", [
    "", "\n", "960", "960 8.0", "abc 8.0 1", "960 abc 1", "960 8.0 x",
    "0 8.0 1", "-3 8.0 1", "960 0 1", "960 -8.0 1",
    "nan 8.0 1", "960 nan 1", "inf 8.0 1", "960 inf 1",
])
def test_unusable_content_is_none(monkeypatch, tmp_path, text):
    _publish(monkeypatch, tmp_path, text)
    assert _read_desktop_geom() is None


def test_trailing_extra_tokens_are_ignored(monkeypatch, tmp_path):
    # A concurrent reader can see a mid-write file: the first three fields stand.
    _publish(monkeypatch, tmp_path, "960 8.0 1 42\n")
    desk = _read_desktop_geom()
    assert desk.usable_px == 960 and desk.glyph_adv == 8.0 and desk.fit is True


# ── Fit width ────────────────────────────────────────────────────────────────

def test_fit_mode_uses_the_published_width():
    cfg = _Cfg()
    _apply_desktop_width(cfg, config.DesktopGeometry(usable_px=960, glyph_adv=8.0,
                                                     fit=True))
    assert cfg.display.tooltip_width == 120       # floor(960 / 8)


def test_without_fit_the_width_is_left_alone():
    cfg = _Cfg(50)
    _apply_desktop_width(cfg, config.DesktopGeometry(usable_px=960, glyph_adv=8.0,
                                                     fit=False))
    assert cfg.display.tooltip_width == 50


def test_no_desktop_geometry_is_a_no_op():
    cfg = _Cfg(50)
    _apply_desktop_width(cfg, None)
    assert cfg.display.tooltip_width == 50


def test_fit_mode_clamps_to_floor_and_ceiling():
    narrow = _Cfg()
    _apply_desktop_width(narrow, config.DesktopGeometry(usable_px=40, glyph_adv=8.0,
                                                        fit=True))
    assert narrow.display.tooltip_width == TOOLTIP_WIDTH_FLOOR

    wide = _Cfg()
    _apply_desktop_width(wide, config.DesktopGeometry(usable_px=40000, glyph_adv=8.0,
                                                      fit=True))
    assert wide.display.tooltip_width == DESKTOP_WIDTH_MAX


def test_sub_column_width_is_a_no_op():
    cfg = _Cfg(50)
    _apply_desktop_width(cfg, config.DesktopGeometry(usable_px=4, glyph_adv=8.0,
                                                     fit=True))
    assert cfg.display.tooltip_width == 50


# ── Wiring: apply_canonical_width ────────────────────────────────────────────

def test_fit_overrides_canonical_and_sizes_graphs_from_the_desktop_advance(
        monkeypatch, tmp_path):
    _publish(monkeypatch, tmp_path, "960 8.0 1\n")
    _panel(monkeypatch, 11.0)
    cfg = _Cfg()
    apply_canonical_width(cfg, 78)
    assert cfg.display.tooltip_width == 120
    assert cfg.pages.graph_width == 960           # 120 cols × 8 px


def test_without_fit_canonical_stands_and_desktop_advance_sizes_the_graphs(
        monkeypatch, tmp_path):
    _publish(monkeypatch, tmp_path, "960 8.0 0\n")
    _panel(monkeypatch, 11.0)
    cfg = _Cfg()
    apply_canonical_width(cfg, 78)
    assert cfg.display.tooltip_width == 78
    assert cfg.pages.graph_width == round(78 * 8.0)   # the widget's own advance


def test_no_desktop_widget_falls_back_to_the_panel_advance(monkeypatch):
    _panel(monkeypatch, 11.0)
    cfg = _Cfg()
    apply_canonical_width(cfg, 78)
    assert cfg.display.tooltip_width == 78
    assert cfg.pages.graph_width == round(78 * 11.0)


def test_a_broken_desktop_file_falls_back_to_the_panel(monkeypatch, tmp_path):
    _publish(monkeypatch, tmp_path, "garbage")
    _panel(monkeypatch, 11.0)
    cfg = _Cfg()
    apply_canonical_width(cfg, TOOLTIP_WIDTH_FLOOR)
    assert cfg.pages.graph_width == round(TOOLTIP_WIDTH_FLOOR * 11.0)


def test_nothing_published_keeps_the_default_graph_width(monkeypatch):
    _panel(monkeypatch, None)
    cfg = _Cfg(graph=315)
    apply_canonical_width(cfg, 78)
    assert cfg.pages.graph_width == 315
