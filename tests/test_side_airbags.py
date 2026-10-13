import pytest

from engine.airbags import side_positions
from engine.mapper import n_airbag
from engine.models import Cell, RawRow, RawTable, Trim
from engine.stage_one import features
from engine.valuer import dynamic_delta


@pytest.mark.parametrize('cell,expected', [
    (Cell(dot='●',text='前●/后●'), ['前','后']),
    (Cell(dot='●',text='前●/后-'), ['前']),
    (Cell(dot='●',text='前●/后○ (3300元)'), ['前']),
    (Cell(dot='○',text='前○/后● (2000元)'), ['后']),
    (Cell(dot='●',text='前/后'), ['前','后']),
    (Cell(dot='●',text='前/后-'), ['前']),
    (Cell(dot='○',text='前/后'), []),
    (Cell(dot='●',text='前排',subs=[Cell(dot='●',text='后排')]), ['前','后']),
    (Cell(dot='●',text='前排',subs=[Cell(dot='○',text='后排 (2000元)')]), ['前']),
    (Cell(subs=[Cell(dot='●',text='前排'),Cell(dot='●',text='后排')]), ['前','后']),
    (Cell(dot='●',text='[待定]前/后'), []),
])
def test_side_airbags_standard_positions_count_two_per_row(cell, expected):
    assert side_positions(cell) == expected
    raw = RawTable(trims=[Trim(0,'测试')],rows=[RawRow('前/后排侧气囊',[cell])])
    count, components = n_airbag(raw,0,{})
    assert count == len(expected)*2
    assert components == [pos+'侧' for pos in expected]
    values = next(row for row in features(raw,excluded_rows=[]) if row['key']=='气囊')['values'][0]
    if count:
        assert values == [f'{count}气囊']


def test_four_standard_side_airbags_and_optional_rear_do_not_share_a_count():
    raw = RawTable(trims=[Trim(0,'前后'),Trim(1,'仅前')],rows=[
        RawRow('前/后排侧气囊',[Cell(dot='●',text='前●/后●'),Cell(dot='●',text='前●/后○ (2000元)')]),
    ])
    left, right = (n_airbag(raw,i,{})[0] for i in (0,1))
    assert (left,right) == (4,2)
    assert dynamic_delta(5,str(left),str(right)) == 700
    assert dynamic_delta(5,str(right),str(left)) == -700
