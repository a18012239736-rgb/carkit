import copy
import json
from pathlib import Path

import pytest

from api.bridge import Bridge
from engine import render_backup
from engine.differ import assemble_backup
from engine.models import Ladder, LadderItem, ValuationItem, ValuationTable
from engine.valuer import normalize_floor_price, value_pair


def valuation():
    return ValuationTable(items=[ValuationItem(no=40, name='热泵空调', val=2000)])


def test_overall_uses_per_pair_yuan_prices_and_reverses_with_both_sides():
    left = value_pair({40:'热泵空调'}, {}, 10, 11, valuation(),
                      self_floor_price=87000, comp_floor_price=90000)
    right = value_pair({}, {40:'热泵空调'}, 11, 10, valuation(),
                       self_floor_price=90000, comp_floor_price=87000)
    assert left['config_adv'] == 2000 and left['flat_adv'] == 12000
    assert left['overall'] == 5000 and right['overall'] == -5000
    assert left['overall_reason'] == right['overall_reason'] == ''


@pytest.mark.parametrize('guides', [(None, None), (None, 11), (10, None)])
def test_overall_is_independent_of_missing_guide_prices(guides):
    result = value_pair({40:'热泵空调'}, {}, *guides, valuation(),
                        self_floor_price=87000, comp_floor_price=90000)
    assert result['config_adv'] == 2000 and result['overall'] == 5000
    assert result['flat_adv'] is None
    assert result['flat_adv_reason'] == '缺少左侧或右侧指导价'


@pytest.mark.parametrize('left,right,reason', [
    (None, 90000, '缺少左侧底价'), (87000, None, '缺少右侧底价'),
    (None, None, '缺少左侧、右侧底价'), ('', '  ', '缺少左侧、右侧底价'),
])
def test_missing_floor_prices_do_not_fall_back_to_guide_or_zero(left, right, reason):
    result = value_pair({40:'热泵空调'}, {}, 10, 11, valuation(),
                        self_floor_price=left, comp_floor_price=right)
    assert result['config_adv'] == 2000 and result['flat_adv'] == 12000
    assert result['overall'] is None and result['overall_reason'] == reason
    assert result['config_adv_reason'] == result['flat_adv_reason'] == ''


def test_missing_configuration_value_blocks_overall_even_with_both_floor_prices():
    result = value_pair({40:'热泵空调'}, {}, 10, 11, ValuationTable(),
                        self_floor_price=87000, comp_floor_price=90000)
    assert result['missing'] == [40]
    for key in ('config_adv', 'flat_adv', 'overall'):
        assert result[key] is None
        assert result[key+'_reason'] == '缺少配置赋值规则'


def test_legacy_formula_argument_remains_callable_but_cannot_override_fixed_formula():
    result = value_pair({40:'热泵空调'}, {}, 10, 11, valuation(), 'old-custom-formula',
                        self_floor_price=87000, comp_floor_price=90000)
    assert result['overall'] == 5000
    assert value_pair({40:'热泵空调'}, {}, 10, 11, valuation())['overall'] is None


@pytest.mark.parametrize('value', [None, '', '   '])
def test_empty_floor_prices_are_optional(value):
    assert normalize_floor_price(value) is None


@pytest.mark.parametrize('value', [False, True, '不是数字', '8万元', [], {}, 0, -1,
                                 '0', '-1', float('nan'), float('inf'), -float('inf'),
                                 'NaN', 'Infinity', 10**400])
def test_invalid_floor_prices_are_rejected_at_direct_calculation_boundary(value):
    with pytest.raises(ValueError, match='左侧底价.*大于0.*单位元'):
        value_pair({}, {}, 10, 11, valuation(), self_floor_price=value)
    with pytest.raises(ValueError, match='右侧底价.*大于0.*单位元'):
        value_pair({}, {}, 10, 11, valuation(), comp_floor_price=value)


def test_report_groups_keep_prices_per_pair_without_mutating_caller():
    pairs = [{'self_trim':'A', 'comp_trim':'B', 'self_floor_price':'87000', 'comp_floor_price':90000},
             {'self_trim':'A', 'comp_trim':'B', 'self_floor_price':88000, 'comp_floor_price':89500}]
    original = copy.deepcopy(pairs)
    groups = assemble_backup([], pairs, '左', '右', {'A':10}, {'B':11}, valuation())
    assert pairs == original
    assert [group['valuation']['overall'] for group in groups] == [3000, 1500]
    for group, left, right in zip(groups, (87000, 88000), (90000, 89500)):
        assert group['self_floor_price'] == group['pair']['self_floor_price'] == left
        assert group['comp_floor_price'] == group['pair']['comp_floor_price'] == right
    assert json.loads(json.dumps({'groups':groups}))['groups'][1]['self_floor_price'] == 88000


def test_report_group_validation_applies_even_without_valuation():
    with pytest.raises(ValueError, match='第1组左侧底价'):
        assemble_backup([], [{'self_trim':'A','comp_trim':'B','self_floor_price':False}],
                        '左', '右', {}, {}, None)


@pytest.fixture
def bridge(tmp_path):
    instance = Bridge(str(tmp_path/'work'))
    try:
        yield instance
    finally:
        instance.shutdown()


def comparison_files(bridge, tmp_path):
    paths = [tmp_path/'left.json', tmp_path/'right.json']
    for path, name, model in zip(paths, ('A', 'B'), ('本品', '竞品')):
        items = [LadderItem(no=item['no'], name=item['name'],
                  values=['●' if name=='A' and item['no']==40 else '✕']) for item in bridge.rules.items]
        Ladder(model=model, trims=[{'name':name, 'price_guide':None}], items=items).save(path)
    return paths


@pytest.mark.parametrize('key', ['self_floor_price', 'comp_floor_price'])
@pytest.mark.parametrize('value', [True, '不是数字', 0, -1, float('nan'), float('inf')])
def test_bridge_rejects_bad_price_before_reading_sources_or_writing_report(bridge, key, value):
    pair = {'self_trim':'A', 'comp_trim':'B', key:value}
    result = bridge.run_diff('not-read-left.json', 'not-read-right.json', [pair], left_is_competitor=True)
    assert not result['ok']
    assert '底价' in result['error'] and '单位元' in result['error']
    assert list((Path(bridge.workdir)/'结果').iterdir()) == []


def test_bridge_report_receives_pair_prices_without_saving_them_to_vehicle_models(bridge, tmp_path, monkeypatch):
    paths = comparison_files(bridge, tmp_path)
    source_bytes = [path.read_bytes() for path in paths]
    pairs = [{'self_trim':'A','comp_trim':'B','self_floor_price':'87000','comp_floor_price':90000}]
    original = copy.deepcopy(pairs)
    render = render_backup.render_md
    rendered_groups = []

    def capture(*args, **kwargs):
        rendered_groups.extend(copy.deepcopy(args[2]))
        return render(*args, **kwargs)

    monkeypatch.setattr(render_backup, 'render_md', capture)
    result = bridge.run_diff(str(paths[0]), str(paths[1]), pairs, left_is_competitor=True)
    assert result['ok'], result
    assert pairs == original
    assert [path.read_bytes() for path in paths] == source_bytes
    group = rendered_groups[0]
    assert group == result['groups'][0]
    assert group['self_floor_price'] == group['pair']['self_floor_price'] == 87000
    assert group['comp_floor_price'] == group['pair']['comp_floor_price'] == 90000
    assert group['valuation']['config_adv'] == 2000
    assert group['valuation']['overall'] == 5000 and group['valuation']['flat_adv'] is None
    assert Path(result['md_path']).read_text(encoding='utf-8') == result['md']
    assert len(list((Path(bridge.workdir)/'结果').iterdir())) == 1
