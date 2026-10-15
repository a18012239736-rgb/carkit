import pytest

from engine.ppt_import import _apply, make_snapshot


@pytest.mark.parametrize('text', [
    '540°透明底盘',
    '540º透明底盘',
    '540度透明底盘',
    '舒适型：540°透明底盘',
    '540影像',
    '540°全景影像',
])
def test_ppt_540_terms_map_to_same_imaging_equipment(text):
    values, evidence, remaining = {}, {}, []
    _apply(text, values, evidence, remaining)
    assert values[7] == '540影像'
    assert evidence[7] == [text]
    assert not remaining


@pytest.mark.parametrize('text', ['360影像', '360°全景影像'])
def test_ppt_360_terms_remain_360_imaging(text):
    values = {}
    _apply(text, values, {}, [])
    assert values[7] == '360影像'


def test_optional_540_underbody_is_not_standard_equipment():
    values = {}
    _apply('选装540°透明底盘', values, {}, [])
    assert values.get(7) != '540影像'


def test_ppt_540_underbody_import_keeps_trim_inheritance():
    snap = make_snapshot({'model': '测试车型', 'columns': [
        {'name': '基础型', 'text': '360影像'},
        {'name': '舒适型', 'base': '基础型', 'text': '舒适型：540°透明底盘'},
        {'name': '豪华型', 'base': '舒适型', 'text': ''},
    ]})
    imaging = next(cell for cell in snap.cells if cell['no'] == 7)
    assert imaging['values'] == {
        '基础型': '360影像', '舒适型': '540影像', '豪华型': '540影像',
    }
