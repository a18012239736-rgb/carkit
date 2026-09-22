from engine.ppt_import import make_snapshot, _apply


def test_t13t_wording_and_driver_only_upgrade():
    base = '''90kW电机
仿皮方向盘+座椅
软质包覆（扶手及周边）
R17 钢轮
定速巡航、胎压监测
主驾一键升降+防夹
主驾手动6向调节+副驾手动4向
EPB+AUTOHOLD
主驾无钥匙进入
电动空调
行车记录仪（接口）'''
    upgrade = '''主驾电动6向调节
L2驾驶辅助（单V）+APA
电动尾门
多色氛围灯'''
    snap = make_snapshot({'model': 'T13T', 'columns': [
        {'name': '基础型', 'text': base},
        {'name': '舒适型', 'base': '基础型', 'text': upgrade}]})
    cells = {c['no']: c['values'] for c in snap.cells}
    assert cells[25]['基础型'] == cells[34]['基础型'] == '仿皮'
    assert cells[4]['基础型'] == 'R17钢轮毂'
    assert cells[9] == {'基础型': '定速巡航', '舒适型': '基础L2'}
    assert cells[35]['基础型'] == '主驾6向手调+副驾4向手调'
    assert cells[35]['舒适型'] == '主驾6向电调+副驾4向手调'
    assert cells[13]['舒适型'] == '●'
    assert cells[39]['舒适型'] == '多色氛围灯'
    assert not any(snap.rulings[0]['remaining'].values())


def test_unknown_and_uncertain_equipment_still_requires_review():
    values, evidence, remaining = {}, {}, []
    _apply('陌生配置\n选装电动尾门', values, evidence, remaining)
    assert values[13].startswith('[待定]')
    assert len(remaining) == 2
