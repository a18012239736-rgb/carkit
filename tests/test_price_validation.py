from engine.acquire import validate


def test_one_missing_price_is_allowed_as_pending():
    data = {'headers': ['A', 'B'], 'expectedCount': 2, 'rows': [
        {'n': '厂商指导价(元)', 'v': ['10.99万', '暂无']},
        {'n': '能源类型', 'v': ['汽油', '汽油']},
        {'n': '车身结构', 'v': ['三厢车', '三厢车']},
    ] + [{'n': f'配置{i}', 'v': ['●', '●']} for i in range(30)]}
    validate(data, live=True)
