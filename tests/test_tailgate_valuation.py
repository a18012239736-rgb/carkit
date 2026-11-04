import pytest

from engine.differ import diff
from engine.models import Ladder, LadderItem, ValuationItem, ValuationTable
from engine.rules import Rules
from engine.valuer import (
    _default_rule_amount, default_valuation, explain_rule, load_xlsx,
    make_template_xlsx, normalize_valuation, value_pair,
)


def valuation(item=None):
    if item is None:
        item = next(row for row in default_valuation(Rules())['items'] if row['no'] == 13)
    return ValuationTable(items=[ValuationItem(**item)])


def compare(left, right, prices):
    def ladder(value):
        return Ladder(trims=[{'name': 'A'}], items=[LadderItem(no=13, name='电动后备箱', values=[value])])
    return next(cell for cell in diff(ladder(left), ladder(right),
                                    [{'self_trim': 'A', 'comp_trim': 'A'}], Rules(), prices)
                if cell['no'] == 13)


@pytest.mark.parametrize('left,right,expected', [
    ('●', '✕', 800),
    ('感应电动后备箱', '✕', 1200),
    ('感应电动后备箱', '●', 400),
    ('●', '感应电动后备箱', -400),
    ('✕', '感应电动后备箱', -1200),
    ('感应电动后备箱', '感应电动后备箱', 0),
    ('●(带位置记忆)', '●', 0),
    ('○感应电动后备箱(选装)', '✕', 0),
    ('●(○感应选装)', '●', 0),
    ('电动后备箱(无感应)', '●', 0),
])
def test_sensing_adds_only_400_and_comparison_exports_use_the_same_amount(left, right, expected):
    prices = valuation()
    cell = compare(left, right, prices)
    assert cell['verdict'] == ('多' if expected > 0 else '少' if expected < 0 else '同')
    result = value_pair({}, {}, 10, 10, prices, cells=[cell])
    assert result['config_adv'] == expected
    assert result['total_more'] == max(expected, 0)
    assert result['total_less'] == max(-expected, 0)
    # The summary-only path is also used by existing saved/exported comparisons.
    more = {13: cell['backup_more']} if cell['backup_more'] else {}
    less = {13: cell['backup_less']} if cell['backup_less'] else {}
    assert value_pair(more, less, 10, 10, prices)['config_adv'] == expected
    if expected:
        assert '感应功能另加400元' in result['detail'][0]['rule']


def test_legacy_fixed_base_price_is_preserved_when_sensing_is_added():
    legacy = {'no': 13, 'name': '电动后备箱', 'pricing': 'flat', 'rule': 'flat', 'val': 1250}
    prices = valuation(legacy)
    for left, right, expected in [('●', '✕', 1250), ('感应电动后备箱', '✕', 1650),
                                  ('感应电动后备箱', '●', 400)]:
        cell = compare(left, right, prices)
        assert value_pair({}, {}, 10, 10, prices, cells=[cell])['config_adv'] == expected
    updated = next(row for row in normalize_valuation({'items': [legacy]}, Rules())['items'] if row['no'] == 13)
    assert updated['rule'] == 'dynamic'
    assert updated['params'] == {'electric': 1250, 'sensing_bonus': 400}
    assert '1250元' in explain_rule(prices, 13)


def test_tailgate_parameters_roundtrip_through_the_existing_rule_editor_excel(tmp_path):
    rules = Rules()
    items = {item['no']: item for item in default_valuation(rules)['items']}
    items[13]['params'] = {'electric': 900, 'sensing_bonus': 600}
    path = tmp_path / 'rules.xlsx'
    make_template_xlsx(path, rules, items)
    restored = normalize_valuation(load_xlsx(path), rules)
    item = next(row for row in restored['items'] if row['no'] == 13)
    assert item['params'] == {'electric': 900, 'sensing_bonus': 600}
    prices = valuation(item)
    cell = compare('感应电动后备箱', '●', prices)
    assert value_pair({}, {}, 10, 10, prices, cells=[cell])['config_adv'] == 600


def test_explicitly_missing_legacy_base_price_is_not_replaced_with_800():
    legacy = {'no': 13, 'name': '电动后备箱', 'pricing': 'flat', 'rule': 'flat', 'val': None}
    with pytest.raises(ValueError, match='#13'):
        normalize_valuation({'items': [legacy]}, Rules())
    prices = valuation(legacy)
    cell = compare('感应电动后备箱', '✕', prices)
    result = value_pair({}, {}, 10, 10, prices, cells=[cell])
    assert result['config_adv'] is None and result['missing'] == [13]
    assert value_pair({13: cell['backup_more']}, {}, 10, 10, prices)['missing'] == [13]
    same = compare('●', '●', prices)
    assert value_pair({}, {}, 10, 10, prices, cells=[same])['config_adv'] == 0


def test_tailgate_notes_are_not_parsed_as_a_second_vehicle():
    assert _default_rule_amount(13, '●(带位置记忆)', 'more') == 800
    assert _default_rule_amount(13, '●(带感应)', 'more') == 1200
    assert _default_rule_amount(13, '感应电动后备箱(带位置记忆)', 'more') == 1200


def test_zero_priced_sensing_does_not_leave_an_incorrect_more_verdict():
    item = next(row for row in default_valuation(Rules())['items'] if row['no'] == 13)
    item['params']['sensing_bonus'] = 0
    assert compare('感应电动后备箱', '●', valuation(item))['verdict'] == '同'
