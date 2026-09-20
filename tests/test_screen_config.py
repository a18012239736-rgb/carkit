import pytest

from engine.screen_config import normalize_screen, validate_snapshot_screens
from engine.ppt_import import _apply
from engine.models import Snapshot
from engine.differ import _num


@pytest.mark.parametrize('text', ['15.6寸中控屏', '15.6中控液晶显示屏', '中控屏15.6英寸', '2K 15.6寸中控屏'])
def test_screen_import_and_size(text):
    values = {}
    _apply(text, values, {}, [])
    assert _num(values[21]) == 15.6
    assert '[待定]' not in values[21]


@pytest.mark.parametrize('text', ['有', '大屏', '2K', '4K中控屏', '', '-5寸', '0寸', '120寸'])
def test_invalid_size_is_pending_or_rejected(text):
    assert normalize_screen(text, 21).startswith('[待定]')
    with pytest.raises(ValueError):
        normalize_screen(text, 21, strict=True)


@pytest.mark.parametrize('text', ['●14.6,○15.6选装', '10.17寸(○全液晶选装)', '○12.3寸副驾屏'])
def test_optional_details_preserved(text):
    assert normalize_screen(text, 29) == text


def test_compound_import_and_uncertainty():
    values = {}
    _apply('15.6寸中控屏+12.3寸副驾屏+10.25寸全液晶仪表', values, {}, [])
    assert [_num(values[no]) for no in (21,22,29)] == [15.6,12.3,10.25]
    assert '全液晶' in values[29]
    _apply('15.6寸中控屏和10.25寸仪表', values, {}, [])
    assert values[21].startswith('[待定]') and values[29].startswith('[待定]')


def test_save_validation_reports_trim_and_allows_explicit_pending():
    snap = Snapshot(cells=[{'no':21, 'values':{'舒适版':'大屏'}}])
    with pytest.raises(ValueError, match='舒适版.*中控屏'):
        validate_snapshot_screens(snap)
    snap.cells[0]['values']['舒适版'] = '[待定]尺寸未确认'
    assert validate_snapshot_screens(snap) is snap


@pytest.mark.parametrize('left,right', [('大屏','15.6'), ('15.6','大屏')])
def test_unknown_screen_excluded_on_either_side(left, right):
    from engine.models import Ladder, LadderItem
    from engine.rules import Rules
    from engine.differ import diff
    a = Ladder(trims=[{'name':'A'}], items=[LadderItem(no=21,name='中控屏',values=[left])])
    b = Ladder(trims=[{'name':'B'}], items=[LadderItem(no=21,name='中控屏',values=[right])])
    cell = next(c for c in diff(a,b,[{'self_trim':'A','comp_trim':'B'}],Rules()) if c['no']==21)
    assert cell['verdict'] == '不计'


def test_bridge_rejects_invalid_screen_before_writing(tmp_path):
    from api.bridge import Bridge
    bridge = Bridge(str(tmp_path))
    snap = Snapshot(model='测试', trims=[{'name':'舒适版'}], cells=[{'no':21,'values':{'舒适版':'大屏'}}])
    import json
    data = json.loads(snap.to_json())
    assert not bridge.save_ppt_snapshot(data, True)['ok']
    path = tmp_path/'invalid.json'
    assert not bridge.save_snapshot(str(path), data)['ok']
    assert not path.exists()


def test_optional_screen_not_compared_as_standard():
    from engine.models import Ladder, LadderItem
    from engine.rules import Rules
    from engine.differ import diff
    a = Ladder(trims=[{'name':'A'}], items=[LadderItem(no=21,name='中控屏',values=['12.3寸'])])
    b = Ladder(trims=[{'name':'B'}], items=[LadderItem(no=21,name='中控屏',values=['○15.6寸'])])
    cell = next(c for c in diff(a,b,[{'self_trim':'A','comp_trim':'B'}],Rules()) if c['no']==21)
    assert cell['verdict']=='多'
    assert '选装按无配置计' in cell['display']
