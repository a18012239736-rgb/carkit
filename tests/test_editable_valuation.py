from engine.models import ValuationItem, ValuationTable
from engine.rules import Rules
from engine.valuer import default_valuation, load_xlsx, make_template_xlsx, normalize_valuation, value_pair


def _table(data):
    return ValuationTable(items=[ValuationItem(**item) for item in data['items']])


def test_saved_params_change_dynamic_and_fixed_amounts():
    rules = Rules()
    data = default_valuation(rules)
    by_no = {item['no']: item for item in data['items']}
    by_no[9]['params']['highway_noa'] = 6200
    by_no[40]['val'] = 2600
    normalized = normalize_valuation(data, rules)
    table = _table(normalized)

    assert value_pair({9: '高速NOA(基础L2)'}, {}, 10, 10, table)['config_adv'] == 5200
    assert value_pair({40: '热泵空调'}, {}, 10, 10, table)['config_adv'] == 2600


def test_valuation_excel_roundtrip_keeps_dynamic_params(tmp_path):
    rules = Rules()
    data = default_valuation(rules)
    by_no = {item['no']: item for item in data['items']}
    by_no[9]['params']['highway_noa'] = 6100
    path = tmp_path / 'valuation.xlsx'
    make_template_xlsx(path, rules, by_no)

    loaded = normalize_valuation(load_xlsx(path), rules)
    assert {item['no']: item for item in loaded['items']}[9]['params']['highway_noa'] == 6100


def test_invalid_editor_values_are_rejected():
    rules = Rules()
    data = default_valuation(rules)
    {item['no']: item for item in data['items']}[9]['params']['highway_noa'] = -1

    try:
        normalize_valuation(data, rules)
    except ValueError as error:
        assert '大于等于0' in str(error)
    else:
        raise AssertionError('负数赋值应被拒绝')
