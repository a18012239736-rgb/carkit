from engine.differ import _backup_display, _cmp_generic, MORE, LESS
from engine.valuer import _default_rule_amount


def test_usb_summary_names_item_and_counts_both_rows():
    ours, theirs = '前2/后1', '前2/后0'
    assert _cmp_generic(32, {}, ours, theirs)[0] == MORE
    more, _ = _backup_display(32, MORE, ours, theirs, ours, theirs)
    assert more == 'USB/Type-C：前2后1（前2后0）'
    assert _default_rule_amount(32, more, 'more') == 50
    _, less = _backup_display(32, LESS, theirs, ours, theirs, ours)
    assert _default_rule_amount(32, less, 'less') == 50
    assert _default_rule_amount(32, '前2/后1(前2/后0)', 'more') == 50


def test_usb_absence_and_total_only():
    more, _ = _backup_display(32, MORE, '2个', '✕', '2个', '✕')
    assert more == 'USB/Type-C：2个（0个）'
    assert _default_rule_amount(32, more, 'more') == 100
