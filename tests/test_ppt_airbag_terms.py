import pytest

from engine.ppt_import import _apply


@pytest.mark.parametrize('text,expected', [
    ('前排中间气囊', '5气囊'),
    ('前排中央气囊', '5气囊'),
    ('前排中央安全气囊', '5气囊'),
    ('主驾膝部气囊+副驾膝部气囊', '6气囊'),
    ('前排中间气囊+主驾膝部气囊+副驾膝部气囊', '7气囊'),
    ('后排中央安全气囊', '4气囊'),
    ('后排座椅防下滑气囊', '4气囊'),
    ('9气囊，前排中间气囊+主驾膝部气囊+副驾膝部气囊', '9气囊'),
    ('8气囊（侧气帘+中央安全气囊）', '8气囊'),
])
def test_ppt_airbag_terms_keep_explicit_totals_and_unknown_types(text, expected):
    values, evidence, remaining = {5: '4气囊'}, {}, []
    _apply(text, values, evidence, remaining)
    assert values[5] == expected
    if text.startswith('后排'):
        assert remaining == [text]


def test_ppt_same_middle_alias_and_knee_terms_do_not_count_twice():
    values, evidence, remaining = {5: '4气囊'}, {}, []
    _apply('前排中间气囊\n前排中央安全气囊\n中央安全气囊\n主驾膝部气囊\n主驾驶膝部气囊', values, evidence, remaining)
    assert values[5] == '6气囊'


def test_ppt_no_airbag_base_keeps_review_required():
    values, evidence, remaining = {}, {}, []
    _apply('前排中间气囊', values, evidence, remaining)
    assert values[5].startswith('[待定]')


def test_ppt_optional_airbags_do_not_increment_standard_total():
    values, evidence, remaining = {5: '4气囊'}, {}, []
    _apply('选装主驾膝部气囊', values, evidence, remaining)
    assert values[5].startswith('[待定]')
