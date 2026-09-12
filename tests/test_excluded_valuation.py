from engine.valuer import default_valuation, load_xlsx
from engine.rules import Rules


def test_slash_excludes_but_zero_base_tiers_remain(tmp_path):
    from openpyxl import Workbook
    rows = {i['no']: i for i in default_valuation(Rules())['items']}
    assert {n for n, i in rows.items() if i['rule'] == 'excluded'} == {2, 8, 19, 24}
    assert all(rows[n]['rule'] == 'dynamic' for n in (9, 20, 25))
    wb = Workbook(); ws = wb.active; ws.title = '赋值表'
    ws.append(['编号', '项目', '方式', '金额'])
    ws.append([2, '电芯品牌', 'flat', '/'])
    ws.append([9, '辅助驾驶', 'flat', 0])
    path = tmp_path / 'rules.xlsx'; wb.save(path)
    items = load_xlsx(path)['items']
    assert items[0]['rule'] == 'excluded'
    assert items[1]['rule'] != 'excluded'
