from engine.valuer import _default_rule_amount

def test_charger_power_is_not_quantity():
    assert _default_rule_amount(33, '前排单50W无线充电', 'less') == 350
    assert _default_rule_amount(33, '前排双50W无线充电', 'less') == 700
    assert _default_rule_amount(33, '前排单50W无线充电(前排单15W无线充电)', 'more') == 250
    assert _default_rule_amount(38, '车外扬声器', 'less') == 100


def test_fast_slow_positions_and_unknown_power_share_one_rule():
    from engine.differ import cmp_wireless
    from engine.valuer import dynamic_delta
    from engine.wireless import label, units
    assert label('●前排40W') == '前排50W手机无线充电'
    assert label('●前排80W') == '前排50W手机无线充电'
    assert label('●前排15W') == '前排慢充手机无线充电'
    assert label('●前排') == '前排手机无线充电'
    assert units('50W前排+后排') == [('前排', 1, 'fast'), ('后排', 1, 'fast')]
    assert units('前排15W+后排') == [('前排', 1, 'slow'), ('后排', 1, 'unknown')]
    assert units('前排+后排15W') == [('前排', 1, 'unknown'), ('后排', 1, 'slow')]
    assert dynamic_delta(33, '前排50W+后排15W', '前排15W') == 350
    assert dynamic_delta(33, '前排15W', '前排50W+后排15W') == -350
    assert dynamic_delta(33, '前排双50W', '2个无线充电') == 0
    assert dynamic_delta(33, '○前排50W', '✕') == 0
    assert dynamic_delta(33, '前排50W(○后排选装)', '✕') == 350
    assert dynamic_delta(33, '前排', '✕') == 350
    assert dynamic_delta(33, '前排50W+后排无', '✕') == 350
    assert dynamic_delta(33, '前排●/后排-', '✕') == 350
    assert dynamic_delta(33, '前排●/后排✕', '✕') == 350
    assert dynamic_delta(33, '前排15W+后排', '✕') == 450
    assert cmp_wireless('前排40W', '前排15W')[0] == '多'
    assert cmp_wireless('前排40W', '前排15W', params={'per_charger':50,'slow_charger':100})[0] == '少'


def test_mapping_keeps_standard_rear_and_never_promotes_options():
    from engine.mapper import n_wireless_charge
    from engine.models import Cell, RawRow, RawTable
    raw = RawTable(rows=[RawRow(name='手机无线充电功能', cells=[
        Cell(dot='●',text='前排',subs=[Cell(dot='●',text='后排')]),
        Cell(dot='●',text='前排',subs=[Cell(dot='○',text='后排')]),
        Cell(dot='○',text='前排',subs=[Cell(dot='●',text='后排')]),
    ]),RawRow(name='手机无线充电功率',cells=[Cell(dot='●',text='40W')]*3)])
    assert n_wireless_charge(raw,0,{}) == '●前排50W+后排50W'
    assert n_wireless_charge(raw,1,{}) == '●前排50W'
    assert n_wireless_charge(raw,2,{}) == '●后排50W'
    raw.row('手机无线充电功率').cells[0] = Cell(dot='●',text='前排50W',subs=[Cell(dot='●',text='后排15W')])
    assert n_wireless_charge(raw,0,{}) == '●前排50W+后排慢充'
    from engine.valuer import dynamic_delta
    assert dynamic_delta(33,n_wireless_charge(raw,0,{}),'✕') == 450


def test_stage_uses_canonical_fast_slow_labels_without_promoting_optional_function():
    from engine.models import Cell, RawRow, RawTable, Trim
    from engine.stage_one import features
    raw = RawTable(trims=[Trim(0,'快'),Trim(1,'慢'),Trim(2,'选配')],rows=[
        RawRow(name='手机无线充电功能',cells=[Cell(dot='●',text='前排')]*2+[Cell(dot='○',text='前排')]),
        RawRow(name='手机无线充电功率',cells=[Cell(dot='●',text=v) for v in ('40W','15W','50W')]),
    ])
    feature = next(item for item in features(raw, excluded_rows=[]) if item['key']=='手机无线充电')
    assert feature['values'] == [['前排50W手机无线充电'],['前排慢充手机无线充电'],[]]
