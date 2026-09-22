from engine.differ import diff
from engine.models import Ladder, LadderItem
from engine.rules import Rules
from engine.valuer import _default_rule_amount


def test_front_trunk_tiers_in_both_directions():
    for left, right, verdict, amount in [
        ('手动前备箱', '✕', '多', 500),
        ('电动前备箱', '✕', '多', 1000),
        ('电动前备箱', '手动前备箱', '多', 500),
        ('手动前备箱', '电动前备箱', '少', 500),
        ('手动前备箱', '手动前备箱', '同', 0),
    ]:
        def ladder(v):
            return Ladder(trims=[{'name': 'A'}], items=[LadderItem(no=12, name='前备箱', values=[v])])
        cell = next(c for c in diff(ladder(left), ladder(right), [{'self_trim':'A','comp_trim':'A'}], Rules()) if c['no']==12)
        assert cell['verdict'] == verdict
        assert _default_rule_amount(12, cell['backup_more'] or cell['backup_less'], 'more') == amount
