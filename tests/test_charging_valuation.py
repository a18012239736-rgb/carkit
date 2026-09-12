from engine.valuer import _default_rule_amount

def test_charger_power_is_not_quantity():
    assert _default_rule_amount(33, '前排单50W无线充电', 'less') == 350
    assert _default_rule_amount(33, '前排双50W无线充电', 'less') == 700
    assert _default_rule_amount(33, '前排单50W无线充电(前排单15W无线充电)', 'more') == 0
    assert _default_rule_amount(38, '车外扬声器', 'less') == 100
