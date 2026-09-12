from engine.valuer import _default_rule_amount as amount

def test_confirmed_price_differences():
    for no, text, expected in [
        (3,'800V(400V)',2000),(3,'400V(✕)',0),
        (4,'R17铝轮毂(R16钢轮毂)',1200),
        (7,'540影像(倒车影像)',500),
        (9,'基础L2(定速巡航)',500),(9,'高速NOA(基础L2)',2000),
        (9,'城市NOA(高速NOA)',5000),
        (9,'基础L2(定速巡航(无L2))',500),
        (18,'不可开启全景天窗(电动天窗)',1000),
        (34,'NAPPA真皮(真皮)',1000),
        (35,'主驾6向电调+副驾6向电调(主驾6向电调+副驾4向手调)',500),
    ]:
        assert amount(no,text,'more') == expected
