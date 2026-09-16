from pathlib import Path
import pytest
from engine.acquire import validate
from engine import rawschema, stage_one
from engine.models import Cell, RawRow
from engine.ladder import build_ladder
from engine.rules import Rules
from engine.differ import diff


@pytest.mark.parametrize('energy', ['汽油', '柴油', '油电混合', '纯电动', '插电式混合动力', '增程式', '氢燃料'])
def test_capture_does_not_require_electric_range(energy):
    data = {'headers': ['测试版型'], 'expectedCount': 1, 'rows': [
        {'n': '厂商指导价(元)', 'v': ['10.99万']},
        {'n': '能源类型', 'v': [energy]}, {'n': '车身结构', 'v': ['三厢车']},
    ] + [{'n': f'配置{i}', 'v': ['●']} for i in range(30)]}
    validate(data, live=True)
    data['rows'] = data['rows'][:3]
    with pytest.raises(ValueError):
        validate(data, live=True)


def test_mixed_powertrain_applicability_and_ladder():
    raw = rawschema.detect_and_load(str(Path(__file__).parent/'golden'/'raw-Q05-汽车之家全表-2026-09-11.json'))
    raw.row('能源类型').cells[0] = Cell(text='汽油')
    raw.row('能源类型').cells[1] = Cell(text='油电混合')
    raw.rows.append(RawRow(name='发动机', cells=[Cell(text='1.6T') for _ in raw.trims]))
    rules = Rules()
    lad = build_ladder(raw, rules)
    assert lad.items[0].values[:2] == ['不适用', '不适用']
    assert lad.items[0].values[2] != '不适用'
    assert lad.items[2].values[0] != '不适用'
    assert '1.6T' not in stage_one.render(raw, [{'target': 0, 'base': None}])
    keys = {f['key'] for f in stage_one.features(raw)}
    assert not keys.intersection({'能源类型', '发动机', '变速箱', '最大功率(kW)', '最大扭矩(N·m)'})
    assert raw.row('发动机').cells[0].text == '1.6T'
    cells = diff(lad, lad, [{'self_trim': lad.trims[0]['name'], 'comp_trim': lad.trims[2]['name']}], rules)
    assert '不适用' in str(cells[0])


@pytest.mark.parametrize('energy,excluded', [
    ('汽油', True), ('柴油', True), ('油电混合', True),
    ('纯电动', False), ('插电式混合动力', False), ('增程式', False),
    ('未知', False),
])
def test_only_range_has_powertrain_exclusion(energy, excluded):
    from engine.powertrain import not_applicable
    assert not_applicable(energy, 1) is excluded
    assert all(not not_applicable(energy, no) for no in range(2, 42))
