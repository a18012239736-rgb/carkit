from pathlib import Path
from api.bridge import Bridge
from engine import rawschema


def test_filters_and_custom_export(tmp_path):
    bridge = Bridge(str(tmp_path / 'work'))
    bridge.stage_raw = rawschema.detect_and_load(str(Path(__file__).parent / 'golden' / 'raw-Q05-汽车之家全表-2026-09-11.json'))
    result = bridge.stage_filters()
    assert result['ok']
    assert any(f['label'] == '能源类型' for f in result['filters'])
    assert all(len(f['values']) == len(bridge.stage_raw.trims) for f in result['filters'])
    plan = [{'target': 0, 'base': None}]
    bridge.save_file_dialog = lambda *args: None
    assert bridge.stage_export(plan, choose_path=True)['cancelled']
    assert not list((tmp_path / 'work' / '阶梯').glob('*.md'))
    bridge.save_file_dialog = lambda *args: str(tmp_path / '自选位置')
    result = bridge.stage_export(plan, choose_path=True)
    assert result['ok']
    assert Path(result['path']) == tmp_path / '自选位置.md'
    assert Path(result['path']).read_text() == result['md']
