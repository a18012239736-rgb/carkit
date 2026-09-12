from engine.differ import _cmp_generic
from engine.valuer import _default_rule_amount

def test_equivalent_multicolor_values():
    for a,b in [('256色氛围灯','多色(256色)'),('64色','256色'),('多色','128色')]:
        assert _cmp_generic(39,{},a,b) == ('同','多色','多色')
        assert _default_rule_amount(39,f'{a}（{b}）','less') == 0
    assert _cmp_generic(39,{},'单色','256色') == ('少','单色','多色')
    assert _default_rule_amount(39,'单色(256色)','less') == 400
