from engine.differ import _backup_display

def test_power_tailgate_has_specific_label():
    assert _backup_display(13, '多', '●', '✕', '●', '✕') == ('电动后备箱', '')

def test_missing_configuration_has_name_and_preserves_value():
    from engine.valuer import _default_rule_amount
    assert _backup_display(28, '少', '✕', '●', '✕', '●') == ('', '方向盘记忆')
    assert _backup_display(26, '少', '✕', '手动', '✕', '手动') == ('', '方向盘手动调节')
    assert _backup_display(39, '多', '多色', '✕', '多色', '✕') == ('多色氛围灯', '')
    assert _backup_display(99, '少', '✕', '●', '✕', '●', '测试配置') == ('', '测试配置')
    for no, before, after in [(26,'✕(手动)','方向盘手动调节'), (39,'多色','多色氛围灯')]:
        assert _default_rule_amount(no,before,'less') == _default_rule_amount(no,after,'less')

def test_one_sided_and_two_sided_configuration_contract():
    from engine.differ import _cmp_generic
    from engine.valuer import _default_rule_amount
    for ours, theirs, label, amount in [
        ('✕','不可开启全景天窗','不可开启全景天窗',2000),
        ('不可开启全景天窗','可开启全景天窗','不可开启全景天窗(可开启全景天窗)',500),
    ]:
        verdict, ss, cs = _cmp_generic(18, {}, ours, theirs)
        assert verdict == '少'
        assert _backup_display(18,verdict,ours,theirs,ss,cs) == ('',label)
        assert _default_rule_amount(18,label,'less') == amount
        verdict, ss, cs = _cmp_generic(18, {}, theirs, ours)
        more, less = _backup_display(18,verdict,theirs,ours,ss,cs)
        assert verdict == '多' and not less
        assert _default_rule_amount(18,more,'more') == amount
    assert _backup_display(21,'少','✕','15.6','✕','15.6') == ('','15.6中控')
    assert _backup_display(30,'少','HUD','AR-HUD','●','●') == ('','HUD(AR-HUD)')
    assert _default_rule_amount(30,'HUD(AR-HUD)','less') == 1000
