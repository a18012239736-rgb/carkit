from engine import stage_one
from engine.models import Cell, RawRow, RawTable, Trim


def table(rows):
    return RawTable(model='MG 07', series_id='8563', trims=[Trim(0,'基础'),Trim(1,'旗舰')],
                    rows=[RawRow(name=n,cells=v) for n,v in rows.items()])


def test_source_brand_names_are_not_explanatory_nested_comparisons():
    raw = table({'天窗类型':[Cell(dot='●',text='不可开启全景天窗')]*2,
                 '光感天幕':[Cell(),Cell(dot='●')],
                 '零重力座椅':[Cell(),Cell(dot='●',text='副驾驶')]})
    features = stage_one.features(raw)
    changes = stage_one._compact_items(stage_one._change_items(features,1,0),0)
    assert changes == ['光感天幕','副驾驶零重力座椅']
    md = stage_one.render(raw,[{'target':0,'base':None},{'target':1,'base':0}])
    assert md.count('不可开启全景天窗') == 1
    assert '光感天幕  ' in md
    assert '副驾驶零重力座椅  ' in md
    assert '10向' not in md


def test_raw_roof_wording_is_preserved_even_without_a_separate_brand_row():
    raw = table({'天窗类型':[Cell(),Cell(dot='●',text='光感天幕')]})
    assert stage_one.features(raw)[0]['values'] == [[],['光感天幕']]


def test_vanity_mirror_does_not_invent_illumination_and_keeps_explicit_lighting():
    raw = table({'车内化妆镜':[Cell(dot='●',text='主驾+副驾'),
                               Cell(dot='●',text='主驾+照明灯',subs=[Cell(dot='●',text='副驾+照明灯')])]})
    feature = next(f for f in stage_one.features(raw) if f['key']=='车内化妆镜')
    assert feature['values'] == [['主副驾化妆镜'],['主副驾化妆镜照明灯']]


def test_headrest_speaker_source_word_and_scope_are_visible():
    raw = table({'前排座椅功能':[Cell(),Cell(dot='●',text='头枕扬声器(仅驾驶位)',
                                                      subs=[Cell(dot='○',text='按摩(仅副驾驶位)')])]})
    feature = next(f for f in stage_one.features(raw) if f['key']=='前排座椅功能')
    assert feature['values'] == [[],['主驾座椅头枕扬声器']]
    assert stage_one._option_lines(raw,1) == ['前排座椅功能：按摩(仅副驾驶位)']


def test_comparison_preserves_automatic_rearview_wording_without_changing_pricing():
    from engine import differ
    from engine.models import Ladder, LadderItem
    from engine.rules import Rules

    def mirror(value):
        return Ladder(trims=[{'name':'测试版'}],
                      items=[LadderItem(no=31,name='内后视镜功能',values=[value])])

    automatic = mirror('自动防眩目')
    for other, expected, verdict in (
        ('自动防眩目','同 自动防眩目(自动防眩目)','同'),
        ('手动防眩目','同 自动防眩目(手动防眩目)','同'),
        ('●流媒体','少 自动防眩目(流媒体)','少'),
    ):
        cells = differ.diff(automatic, mirror(other),
                            [{'self_trim':'测试版','comp_trim':'测试版'}], Rules())
        cell = next(c for c in cells if c['no']==31)
        assert cell['display'] == expected
        assert cell['verdict'] == verdict


def test_ladder_summary_groups_and_features_choose_the_same_range_standard():
    raw = table({'WLTC纯电续航里程(km)':[Cell(text='185'),Cell()],
                 'CLTC纯电续航里程(km)':[Cell(text='245'),Cell(text='650')]})
    plan = [{'target':0,'base':None},{'target':1,'base':0}]
    md = stage_one.render(raw,plan)
    assert 'CLTC续航245/650km' in md
    assert '245km：基础' in md and '650km：旗舰' in md
    assert '185' not in md and '续航待核' not in md
    raw.rows.pop()
    md = stage_one.render(raw,plan)
    assert 'WLTC续航185km' in md
    assert 'CLTC续航185' not in md
