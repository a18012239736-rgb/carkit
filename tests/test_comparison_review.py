"""Source review is explanatory only, including optional markers and corrections."""
from copy import deepcopy

from engine import differ, valuer
from engine.comparison_review import build_review
from engine.ladder import build_ladder
from engine.models import Cell, Ladder, LadderItem, RawRow, RawTable, Snapshot, Trim, ValuationItem, ValuationTable
from engine.rules import Rules


RULES = Rules()
VALUATION = ValuationTable(items=[ValuationItem(**item) for item in valuer.default_valuation(RULES)['items']])
PAIR = {'self_trim': '左版', 'comp_trim': '右版'}


def source(rows, name='右版'):
    return RawTable(series_id='1234', model='示例车型', source='rich', scraped_at='2026-10-14T10:00:00',
                    trims=[Trim(idx=0, short=name, price_guide=10)],
                    rows=[RawRow(name=key, cells=[value], group='座椅配置') for key, value in rows.items()])


def manual(values=None, name='左版'):
    values = values or {}
    return Ladder(side='self', model='本品', trims=[{'name': name, 'price_guide': 10}], items=[
        LadderItem(no=item['no'], name=item['name'], values=[values.get(item['no'], '✕')]) for item in RULES.items])


def report(left, right, valuation=VALUATION):
    cells = differ.diff(left, right, [PAIR], RULES, valuation=valuation)
    groups = differ.assemble_backup(cells, [PAIR], left.model, right.model, {'左版': 10}, {'右版': 10}, valuation)
    before = deepcopy((left.to_dict(), right.to_dict(), cells, groups))
    result = build_review(left, right, [PAIR], RULES, valuation, cells, groups)
    assert (left.to_dict(), right.to_dict(), cells, groups) == before
    return result, groups


def evidence(result, no):
    return next(row for row in result['evidence'] if row['no'] == no)


def test_ladder_preserves_raw_without_path_and_loads_old_format():
    raw = source({'主/副驾驶座电动调节': Cell(dot='', text='主●/副○')})
    ladder = build_ladder(raw, RULES)
    assert ladder.evidence == {'raw': raw.to_dict()}
    assert Ladder.from_dict(ladder.to_dict()).evidence == ladder.evidence
    old = ladder.to_dict()
    old.pop('evidence')
    assert Ladder.from_dict(old).evidence == {}


def test_original_markers_and_seat_counting_are_traceable_without_price_changes():
    raw = source({
        '主/副驾驶座电动调节': Cell(text='主●/副○'),
        '主座椅调节方式': Cell(dot='●', subs=[Cell(dot='●', text=text) for text in
            ('前后调节', '靠背调节', '高低调节(4向)', '腿托调节', '腰部支撑(4向)', '侧翼支撑(主动)')]),
        '副座椅调节方式': Cell(dot='●', subs=[Cell(dot='●', text='前后调节'), Cell(dot='●', text='靠背调节'),
            Cell(dot='●', text='高低调节(2向)'), Cell(dot='○', text='腿托调节'), Cell(dot='●', text='腰部支撑(4向)')]),
    })
    right = build_ladder(raw, RULES)
    result, groups = report(manual({35: '主驾6向手调+副驾4向手调'}), right)
    row = evidence(result, 35)
    original = next(row for row in row['right']['rows'] if row['name'] == '主/副驾驶座电动调节')
    assert original['cell'] == {'dot': '', 'text': '主●/副○', 'subs': []}
    assert row['right']['source_value'] == '主驾8向电调+副驾6向手调'
    assert any('主驾原文：' in line and '＝8向' in line for line in row['right']['calculation'])
    assert any('副驾原文：' in line and '＝6向' in line for line in row['right']['calculation'])
    assert any('腿托、腰托、侧翼不计方向' in line for line in row['right']['calculation'])
    assert evidence(result, 46)['right']['source_value'] == '主驾腿托'
    assert evidence(result, 47)['right']['source_value'] == '前排腰托'
    assert any('1个电调座椅' in line for line in row['right']['calculation'])
    assert row['right']['source_url'] == 'https://www.autohome.com.cn/config/series/1234.html'
    assert row['right']['captured_at'] == raw.scraped_at
    assert row['amount'] == next(item['amount'] for item in groups[0]['valuation']['detail'] if item['no'] == 35)
    assert not [item for item in result['review'] if item['no'] == 35]


def test_manual_correction_is_kept_and_distinguished_from_source_identification():
    right = build_ladder(source({'主/副驾驶座电动调节': Cell(dot='●', text='主/副'),
                                 '主座椅调节方式': Cell(dot='●', text='6向'),
                                 '副座椅调节方式': Cell(dot='●', text='4向')}), RULES)
    right.item(35).values[0] = '主驾12向电调+副驾8向电调'
    result, _ = report(manual(), right)
    row = evidence(result, 35)['right']
    assert row['value'] == '主驾12向电调+副驾8向电调'
    assert row['source_value'] == '主驾6向电调+副驾4向电调'
    assert any('可能有人工修正或识别版本差异' in line for line in row['notes'])
    assert any('主驾12向电调' in line for line in row['calculation'])


def test_old_ladder_and_snapshot_describe_input_basis_not_fabricated_source():
    snapshot = Snapshot(model='本品', date='2026-10-14', version='项目草案',
                        trims=[{'name': '左版'}], cells=[{'no': 35, 'values': {'左版': '主副手调'}, 'basis': '产品规划表确认'}])
    right = manual({35: '主驾6向电调+副驾4向手调'}, name='右版')
    right.side, right.source = 'competitor', '历史导入'
    right.item(35).note = '历史来源说明'
    result, _ = report(snapshot.to_ladder(RULES.items), right)
    row = evidence(result, 35)
    assert row['left']['source_kind'] == 'input'
    assert row['left']['notes'] == ['输入依据：产品规划表确认']
    assert row['right']['source_kind'] == 'unavailable'
    assert any('无法追溯原文' in note for note in row['right']['notes'])
    assert row['left']['rows'] == row['right']['rows'] == []
    assert row['left']['source_value'] is None


def test_review_collects_pending_unmapped_unknown_count_and_missing_rule():
    left = manual({35: '主驾电调+副驾电调', 21: '[待定]中控屏尺寸', 14: '●', 11: '●'})
    left.item(14).unmapped = True
    valuation = ValuationTable(items=[item for item in VALUATION.items if item.no != 11])
    result, _ = report(left, manual(name='右版'), valuation)
    warnings = {(item['no'], item['code'], item['side']) for item in result['review'] if item['level'] == 'warning'}
    assert (35, 'unknown_count', 'left') in warnings
    assert (21, 'pending', 'left') in warnings
    assert (14, 'unmapped', 'left') in warnings
    assert (11, 'missing_valuation', 'both') in warnings


def test_optional_absent_powertrain_and_explicit_exclusions_are_not_errors():
    left = manual({2: '[待定]电芯', 8: '[待定]激光雷达', 1: '不适用', 35: '○主驾电调选装',
                   37: '✕', 11: '○选装'})
    result, _ = report(left, build_ladder(source({}), RULES))
    assert not [item for item in result['review'] if item['level'] == 'warning']
    row = evidence(result, 11)['right']
    assert row['rows'] == [] and row['source_value'] == '✕'
    assert any('没有对应配置行' in note for note in row['notes'])
    assert any(item['code'] == 'source_row_absent' and item['level'] == 'info' for item in result['review'])
    assert evidence(result, 8)['rule'] == '本项不参与赋值计算。'


def test_wireless_uses_shared_units_and_keeps_unknown_power_policy():
    result, _ = report(manual({33: '前排40W无线充电+后排15W无线充电'}),
                       manual({33: '前排手机无线充电'}, name='右版'))
    row = evidence(result, 33)
    assert '前排：1个，快充' in row['left']['calculation']
    assert '后排：1个，慢充' in row['left']['calculation']
    assert any('功率未注明，沿用快充单价，不补写功率' in text for text in row['right']['calculation'])


def test_unrecognized_wireless_text_is_flagged_without_altering_existing_amount():
    result, groups = report(manual({33: '前排无线充电'}), manual(name='右版'))
    assert any(item['no'] == 33 and item['code'] == 'unknown_count' for item in result['review'])
    assert any('现有识别未确认无线充电' in text for text in evidence(result, 33)['left']['calculation'])
    assert groups[0]['valuation']['config_adv'] == 0


def test_malformed_evidence_and_unmatched_trim_never_guess_source():
    right = manual({35: '主驾6向电调+副驾4向手调'}, name='右版')
    right.side = 'competitor'
    right.evidence = {'raw': {'trims': [{'unexpected': True}]}}
    result, _ = report(manual(), right)
    assert evidence(result, 35)['right']['source_value'] is None
    assert any('格式不完整' in note for note in evidence(result, 35)['right']['notes'])
    right.evidence = {'raw': source({'主/副驾驶座电动调节': Cell(dot='●')}, name='其他版').to_dict()}
    result, _ = report(manual(), right)
    assert evidence(result, 35)['right']['source_value'] is None
    assert evidence(result, 35)['right']['rows'] == []
    assert any('无法唯一对应' in note for note in evidence(result, 35)['right']['notes'])
