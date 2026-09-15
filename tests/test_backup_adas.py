from engine.differ import _backup_display, LESS, MORE
from engine.valuer import _default_rule_amount, value_pair


def test_missing_adas_keeps_competitor_configuration_and_value():
    for ours, theirs, expected in [('✕', '定速巡航', 500), ('定速巡航', '基础L2', 500)]:
        more, less = _backup_display(9, LESS, ours, theirs, ours, theirs)
        assert not more
        assert less == f'{ours}({theirs})'
        assert _default_rule_amount(9, less, 'less') == expected
        reverse, _ = _backup_display(9, MORE, theirs, ours, theirs, ours)
        assert _default_rule_amount(9, reverse, 'more') == expected


def test_detail_currency_is_rounded():
    class Rules:
        def item(self, no):
            return {'rule': 'dynamic'}
    result = value_pair({}, {29: '8.8仪表(全液晶8.8)'}, 6.48, 6.58, Rules())
    assert result['detail'][0]['amount'] == -200
