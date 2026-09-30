from engine.acquire import filter_years


def test_selected_year_is_kept_when_site_filter_did_not_apply():
    data = {
        'headers': ['元UP 2027款 301KM 领先型', '元UP 2027款 401KM 超越型', '元UP 2025款 301KM 领先型'],
        'rows': [{'n': '厂商指导价(元)', 'v': ['7.48万', '9.98万', '7.48万']}],
        'expectedCount': 3,
    }
    filter_years(data, ['2027'])
    assert data['headers'] == ['元UP 2027款 301KM 领先型', '元UP 2027款 401KM 超越型']
    assert data['rows'][0]['v'] == ['7.48万', '9.98万']
    assert data['expectedCount'] == 2
