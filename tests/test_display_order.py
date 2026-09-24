from engine.ladder import render_md
from engine.models import Ladder, LadderItem
from engine.render_backup import render_md as render_backup_md
from engine.rules import Rules, display_order_key


def test_seat_memory_follows_seat_functions_in_rule_source():
    numbers = [item['no'] for item in Rules().items]
    assert numbers.index(45) == numbers.index(36) + 1
    assert numbers[numbers.index(45) + 1] == 37


def test_existing_ladder_export_uses_business_display_order():
    ladder = Ladder(
        model='测试车',
        trims=[{'name': '基础型', 'price_guide': 10}],
        items=[
            LadderItem(no=37, name='扬声器数量', values=['6扬声器']),
            LadderItem(no=45, name='座椅记忆', values=['主驾座椅记忆']),
            LadderItem(no=36, name='座椅功能', values=['●']),
        ],
    )
    text = render_md(ladder)
    assert text.index('| 1 | 座椅功能') < text.index('| 2 | 座椅记忆') < text.index('| 3 | 扬声器数量')
    assert display_order_key(36) < display_order_key(45) < display_order_key(37)


def test_filtered_comparison_renumbers_visible_rows_continuously():
    cells = [
        {'no': 1, 'pair': 0, 'name': '纯电续航', 'display': '同'},
        {'no': 3, 'pair': 0, 'name': '高压平台', 'display': '同'},
        {'no': 45, 'pair': 0, 'name': '座椅记忆', 'display': '同'},
    ]
    groups = [{'pair': {'self_trim': '甲', 'comp_trim': '乙'}, 'self_price': 10,
               'comp_price': 11, 'more': [], 'less': [], 'valuation': {}}]
    text = render_backup_md('本品', '竞品', groups, cells)
    assert '| 1 | 纯电续航 |' in text
    assert '| 2 | 高压平台 |' in text
    assert '| 3 | 座椅记忆 |' in text
