from pathlib import Path

from engine import rawschema, stage_one, acquire


def q05_raw():
    return rawschema.detect_and_load(
        str(Path(__file__).parent / "golden" / "raw-Q05-汽车之家全表-2026-09-11.json")
    )


def test_stage_plan_requires_earlier_baseline():
    raw = q05_raw()
    try:
        stage_one.validate_plan(raw, [{"target": 1, "base": 2}])
    except ValueError as exc:
        assert "已排在前面" in str(exc)
    else:
        raise AssertionError("future baseline must be rejected")


def test_stage_render_keeps_trim_price_and_relative_changes():
    raw = q05_raw()
    md = stage_one.render(raw, [{"target": 0, "base": None}, {"target": 1, "base": 0}])
    assert "405Air" in md and "405Max" in md
    assert "7.99" in md and "8.99" in md
    assert "较405Air" in md
    assert "R17" in md


def test_stage_render_uses_compact_ladder_and_separate_options():
    raw = q05_raw()
    md = stage_one.render(raw, [{"target": 0, "base": None}, {"target": 1, "base": 0}, {"target": 3, "base": 1}])
    assert "405km：405Air / 405Max" in md
    assert "哨兵模式+内置行车记录仪" in md
    assert "基础L2辅助驾驶+全速自适应巡航(定速巡航)" in md
    assert "\n+基础L2辅助驾驶" not in md
    assert "取消" not in md
    assert "无配置(" not in md
    assert "## 选装" in md
    assert md.index("## 选装") > md.index("## 配置")
    assert "> 选装：" in md


def test_series_id_accepts_name_inputs_used_by_gui():
    assert acquire.series_id("8241") == "8241"
    assert acquire.series_id("https://www.autohome.com.cn/config/series/8241.html") == "8241"
    assert acquire.series_id("https://www.autohome.com.cn/8241/") == "8241"
    assert acquire.series_id("比亚迪元UP") is None


def test_seat_directions_include_standard_supports_only():
    from engine.models import Cell
    raw = q05_raw()
    md = stage_one.render(raw, [{"target": 0, "base": None}, {"target": 1, "base": 0}, {"target": 3, "base": 1}])
    assert "主驾10向调节" not in md
    assert "副驾6向调节（副驾4向调节）" in md
    assert "主驾4向腰托" not in md
    raw.row("主座椅调节方式").cells[1] = Cell(dot="●", text="前后调节", subs=[Cell(dot="●", text="靠背调节"), Cell(dot="●", text="高低调节(2向)"), Cell(dot="○", text="腰部支撑(4向)")])
    raw.row("主座椅调节方式").cells[0] = Cell(dot="●", text="前后调节", subs=[Cell(dot="●", text="靠背调节")])
    md = stage_one.render(raw, [{"target": 0, "base": None}, {"target": 1, "base": 0}])
    assert "主驾6向调节（主驾4向调节）" in md
