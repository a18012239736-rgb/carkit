from engine.differ import _backup_display, _cmp_generic, MORE, LESS
from engine.valuer import _default_rule_amount
from engine.usb import usb_label


def test_usb_summary_names_item_and_counts_both_rows():
    ours, theirs = '前2/后1', '前2/后0'
    assert _cmp_generic(32, {}, ours, theirs)[0] == MORE
    more, _ = _backup_display(32, MORE, ours, theirs, ours, theirs)
    assert more == 'USB/Type-C 3个（USB/Type-C 2个）'
    assert _default_rule_amount(32, more, 'more') == 50
    _, less = _backup_display(32, LESS, theirs, ours, theirs, ours)
    assert _default_rule_amount(32, less, 'less') == 50
    assert _default_rule_amount(32, '前2/后1(前2/后0)', 'more') == 50


def test_usb_total_only_display_and_old_values():
    for raw, expected in [('前排2个/后排1个',3), ('前2后2',4), ('4个',4), ('✕',3)]:
        assert usb_label(raw) == f'USB/Type-C {expected}个'


def test_usb_absence_and_total_only():
    from engine.differ import diff
    from engine.models import Ladder, LadderItem
    from engine.rules import Rules
    left = Ladder(trims=[{'name':'本品'}], items=[])
    right = Ladder(trims=[{'name':'竞品'}], items=[LadderItem(no=32,name='USB数量',values=['前2/后1'])])
    cells = diff(left,right,[{'self_trim':'本品','comp_trim':'竞品'}],Rules())
    assert not any(c['no']==32 and c['verdict'] in (MORE, LESS) for c in cells)
    right.item(32).values[0]='前2/后2'
    cells = diff(left,right,[{'self_trim':'本品','comp_trim':'竞品'}],Rules())
    usb = next(c for c in cells if c['no']==32)
    assert usb['verdict']==LESS
    assert usb['backup_less']=='USB/Type-C 3个（USB/Type-C 4个）'
    assert _default_rule_amount(32, usb['backup_less'], 'less')==50
