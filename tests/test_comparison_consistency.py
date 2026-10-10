"""Frozen software regressions: both comparison sides use the same evidence."""
from copy import deepcopy
from pathlib import Path

import pytest

from engine import differ, valuer
from engine.ladder import build_ladder
from engine.models import Ladder, LadderItem, RawTable, ValuationItem, ValuationTable
from engine.rules import Rules
from engine.seat_functions import SUBS, from_text


RULES = Rules()
VALUATION = ValuationTable(items=[ValuationItem(**item)
                                 for item in valuer.default_valuation(RULES)['items']])


def seat_ladder(summary, states, *, name='测试版'):
    return Ladder(model='软件回归输入', trims=[{'name': name, 'price_guide': 10}],
                  items=[LadderItem(no=36, name='座椅功能', values=[summary],
                                    subs=[{'sub': key, 'values': [state]} for key, state in states.items()])])


def compare(left, right, valuation=VALUATION):
    pair = {'self_trim': left.trims[0]['name'], 'comp_trim': right.trims[0]['name'],
            'self_floor_price': 100000, 'comp_floor_price': 100000}
    cells = differ.diff(left, right, [pair], RULES, valuation=valuation)
    group = differ.assemble_backup(cells, [pair], left.model, right.model,
                                   {pair['self_trim']: 10}, {pair['comp_trim']: 10}, valuation)[0]
    return cells, group


@pytest.mark.parametrize(('summary', 'front', 'rear'), [
    ('前排通风加热按摩', '前排通风加热按摩', '二排通风加热按摩'),
    ('加热/通风(仅主驾)', '前排通风加热', '二排加热'),
    ('通风加热(仅主驾)', '前排通风加热', '二排通风加热'),
])
def test_same_trim_uses_full_seat_states_on_both_sides(summary, front, rear):
    # Shapes reproduced from the i8 / SU7 / A06 frozen capture failures.
    # They are software input examples, not claims about current vehicle specs.
    ladder = seat_ladder(summary, from_text(front, rear))
    cells, group = compare(ladder, ladder)
    seat = next(cell for cell in cells if cell['no'] == 36)
    assert seat['self_config'] == seat['comp_config'] == from_text(front, rear)
    assert seat['verdict'] == '同'
    assert not group['more'] and not group['less']
    assert all(group['valuation'][key] == 0 for key in ('config_adv', 'flat_adv', 'overall'))


def test_seat_exchange_changes_only_the_sign_with_saved_prices():
    left = seat_ladder('前排通风加热按摩', from_text('前排通风加热按摩', '二排通风加热按摩'))
    right = seat_ladder('前排通风加热按摩', from_text('前排通风加热按摩'))
    custom = deepcopy(VALUATION)
    next(item for item in custom.items if item.no == 36).params.update(ventilation=410, heating=260, massage=610)
    forward, fg = compare(left, right, custom)
    reverse, rg = compare(right, left, custom)
    assert fg['valuation']['config_adv'] == 1280
    assert rg['valuation']['config_adv'] == -1280
    assert next(cell for cell in forward if cell['no'] == 36)['verdict'] == '多'
    assert next(cell for cell in reverse if cell['no'] == 36)['verdict'] == '少'
    assert fg['more'] == rg['less'] == ['二排座椅通风加热按摩']


def test_partial_subrows_override_only_the_recorded_seat_states():
    left = seat_ladder('前排通风加热', {'二排按摩': '●', '副驾通风': '✕'})
    right = seat_ladder('前排通风加热', {'二排按摩': '✕'})
    cells, group = compare(left, right)
    seat = next(cell for cell in cells if cell['no'] == 36)
    assert seat['self_config']['主驾加热'] == seat['self_config']['副驾加热'] == '●'
    assert seat['self_config']['副驾通风'] == '✕'
    assert group['valuation']['config_adv'] == 200  # 600按摩 - 400通风
    assert compare(right, left)[1]['valuation']['config_adv'] == -200


def test_direct_seat_comparator_does_not_erase_confirmed_summary_with_sparse_subrows():
    verdict, _, backup = differ.cmp_seat36(from_text('前排通风加热'), '前排通风加热',
                                          comp_sub_vals={'二排按摩': '●'})
    assert verdict == '少'
    assert backup == '二排座椅按摩'


def test_seat_optional_and_unknown_states_remain_per_seat():
    states = from_text('前排通风加热', '二排按摩')
    states['副驾通风'] = '○选装'
    states['二排按摩'] = '[待定]请核对'
    left = seat_ladder('前排通风加热按摩', states)
    right = seat_ladder('前排通风加热', from_text('前排通风加热'))
    assert compare(left, right)[1]['valuation']['config_adv'] == -400
    assert compare(right, left)[1]['valuation']['config_adv'] == 400
    assert compare(left, left)[1]['valuation']['config_adv'] == 0


@pytest.mark.parametrize('unknown', ['[待定]USB/Type-C 1个', '?'])
@pytest.mark.parametrize('unknown_on_left', [True, False])
def test_pending_usb_survives_load_and_is_not_priced(unknown, unknown_on_left):
    def loaded(value):
        return Ladder.from_dict({'trims': [{'name': '测试版'}], 'items': [
            {'no': 32, 'name': 'USB数量', 'values': [value]},
        ]})
    uncertain, certain = loaded(unknown), loaded('USB/Type-C 6个')
    left, right = (uncertain, certain) if unknown_on_left else (certain, uncertain)
    cells, group = compare(left, right)
    usb = next(cell for cell in cells if cell['no'] == 32)
    assert uncertain.item(32).values[0] == unknown
    assert usb['verdict'] == '不计' and usb['exempt_id'] == 'pending'
    assert not any(detail['no'] == 32 for detail in group['valuation']['detail'])


@pytest.mark.parametrize('optional_on_left', [True, False])
def test_optional_usb_survives_load_and_does_not_count_as_standard(optional_on_left):
    uncertain = Ladder.from_dict({'trims': [{'name': '测试版'}], 'items': [
        {'no': 32, 'name': 'USB数量', 'values': ['○USB/Type-C 6个']},
    ]})
    absent = Ladder.from_dict({'trims': [{'name': '测试版'}], 'items': [
        {'no': 32, 'name': 'USB数量', 'values': ['✕']},
    ]})
    left, right = (uncertain, absent) if optional_on_left else (absent, uncertain)
    cells, group = compare(left, right)
    assert uncertain.item(32).values[0] == '○USB/Type-C 6个'
    assert next(cell for cell in cells if cell['no'] == 32)['verdict'] == '同'
    assert group['valuation']['config_adv'] == 0
    assert not any(detail['no'] == 32 and detail['amount'] for detail in group['valuation']['detail'])


def test_frozen_mg07_all_directed_pairs_are_self_zero_and_antisymmetric():
    raw = RawTable.load(Path(__file__).parent / 'golden' / 'raw-MG07-terms-2026-10-10.json')
    ladder = build_ladder(raw, RULES)
    names = [trim['name'] for trim in ladder.trims]
    prices = {trim['name']: trim['price_guide'] for trim in ladder.trims}
    pairs = [{'self_trim': a, 'comp_trim': b,
              'self_floor_price': 100000, 'comp_floor_price': 100000}
             for a in names for b in names]
    cells = differ.diff(ladder, ladder, pairs, RULES, valuation=VALUATION)
    groups = differ.assemble_backup(cells, pairs, ladder.model, ladder.model, prices, prices, VALUATION)
    indexed = {(group['pair']['self_trim'], group['pair']['comp_trim']): group for group in groups}
    for (a, b), group in indexed.items():
        reverse = indexed[(b, a)]
        for key in ('config_adv', 'flat_adv', 'overall'):
            assert group['valuation'][key] == pytest.approx(-reverse['valuation'][key])
        if a == b:
            assert group['valuation']['config_adv'] == 0
            assert not group['more'] and not group['less']
