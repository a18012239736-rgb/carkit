import io
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zipfile import ZipFile

import pytest

import cli
from api.bridge import Bridge
from engine import (
    acquire,
    comparison_review,
    differ,
    ladder as ladder_mod,
    mapper,
    ppt_import,
    rawschema,
    render_5c,
    rules as rules_mod,
    usb,
    valuer,
    wireless,
)
from engine.feishu_update import FeishuUpdater
from engine.models import Cell, Ladder, LadderItem, RawRow, RawTable, Trim, ValuationItem, ValuationTable
from engine.rules import Rules
from engine.updater import AppUpdater
from test_config_editor_mapping import run_editor
from test_frontend_comparison_state import run_node


ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / 'tests' / 'golden'


def test_valuer_load_xlsx_preserves_band_and_segmented_rows_with_blank_val(tmp_path):
    rules = Rules()
    items = {it['no']: dict(it) for it in valuer.default_valuation(rules)['items']}
    items[1] = {'no': 1, 'name': '纯电续航', 'pricing': 'segmented_per_km', 'val': '',
                'bands': [{'range': [400, 600], 'per_km': 20}], 'note': '分段', 'rule': ''}
    items[5] = {'no': 5, 'name': '安全气囊', 'pricing': 'band', 'val': '',
                'bands': [{'range': [4, 6], 'val': 1000}], 'note': '分档', 'rule': ''}
    path = tmp_path / 'rules.xlsx'
    valuer.make_template_xlsx(str(path), rules, items)
    loaded = valuer.load_xlsx(str(path))
    by_no = {it['no']: it for it in loaded['items']}
    assert 1 in by_no and by_no[1]['bands'] == [{'range': [400, 600], 'per_km': 20}]
    assert 5 in by_no and by_no[5]['bands'] == [{'range': [4, 6], 'val': 1000}]


def test_seat_memory_sunroof_optional_plus_and_numeric_edge_cases():
    # #17: #45 seat memory absent tokens and 主驾+副驾
    assert valuer.dynamic_delta(45, '-', '✕') == 0
    assert valuer.dynamic_delta(45, '无配置', '✕') == 0
    assert valuer.dynamic_delta(45, '主驾+副驾座椅记忆', '✕') == 200
    assert valuer.dynamic_delta(45, '主驾、副驾', '主驾座椅记忆') == 100
    rules = Rules()
    l_both = Ladder(trims=[{'name': 'A'}], items=[LadderItem(no=45, name='座椅记忆', values=['主驾+副驾座椅记忆'])])
    l_one = Ladder(trims=[{'name': 'A'}], items=[LadderItem(no=45, name='座椅记忆', values=['主驾座椅记忆'])])
    cell45 = next(c for c in differ.diff(l_both, l_one, [{'self_trim': 'A', 'comp_trim': 'A'}], rules) if c['no'] == 45)
    assert cell45['verdict'] == '多'

    # #18: 全景天幕 / 光感天幕
    assert valuer.dynamic_delta(18, '全景天幕', '✕') == 2000
    assert valuer.dynamic_delta(18, '光感天幕', '✕') == 2000

    # #19: +○ optional suffix stripped in _standard_configuration
    assert differ._standard_configuration('电调+折叠+○加热') == '电调+折叠'
    assert valuer.dynamic_delta(20, '电调+折叠+○加热', '电调+折叠') == 0

    # #20: stray dots / versions never raise ValueError
    assert differ._num('...') is None
    assert differ._num('No.1 6气囊') == 1.0
    assert valuer._num('...') is None
    assert valuer._num('1.2.3') == 1.2
    assert mapper._num('B.O氛围灯') is None
    assert rawschema._parse_price('....万') is None


def test_mapper_empty_fallback_cluster_tire_ambient_camera_usb_wireless():
    rules = Rules()
    # #21: empty 液晶仪表尺寸 falls back to 行车电脑显示屏幕 without fabricating 彩色寸仪表
    raw_cluster = RawTable(trims=[Trim(0, 'A'), Trim(1, 'B')], rows=[
        RawRow('液晶仪表尺寸', [Cell(), Cell(dot='●', text='10.2英寸')]),
        RawRow('行车电脑显示屏幕', [Cell(dot='●', text='彩色'), Cell(dot='●', text='彩色')]),
    ])
    assert mapper.n_cluster(raw_cluster, 0, {}) == '彩色仪表'
    assert mapper.n_cluster(raw_cluster, 1, {}) == '10.2寸仪表'

    # #21: empty CLTC falls back to WLTC
    raw_range = RawTable(trims=[Trim(0, 'A')], rows=[
        RawRow('CLTC纯电续航里程(km)', [Cell()]),
        RawRow('WLTC纯电续航里程(km)', [Cell(text='480')]),
    ])
    assert mapper.n_range(raw_range, 0, rules.items_by_no[1]) == '480km'

    # #22a: optional alloy wheel material does not become standard alloy
    raw_tire = RawTable(trims=[Trim(0, 'A')], rows=[
        RawRow('前轮胎规格', [Cell(dot='●', text='205/55 R16')]),
        RawRow('轮圈材质', [Cell(dot='○', text='铝合金')]),
    ])
    assert mapper.n_tire(raw_tire, 0, {}) == 'R16'

    # #22b: ambient color vs brightness level, and pending preserved on solid cell
    raw_amb = RawTable(trims=[Trim(0, 'A'), Trim(1, 'B')], rows=[
        RawRow('车内环境氛围灯', [Cell(dot='●', text='单色(10档亮度可调)'), Cell(dot='●', text='[待定]待核')]),
        RawRow('透明底盘/540度影像', [Cell(dot='●', text='[待定]'), Cell()]),
    ])
    assert mapper.n_ambient(raw_amb, 0, {}) == '单色'
    assert '[待定]' in mapper.n_ambient(raw_amb, 1, {})
    assert '[待定]' in mapper.n_camera540(raw_amb, 0, {})

    # #22c: wireless presence-only + positioned power row
    assert wireless.source_label('有', '前排15W', suffix='') == '前排慢充'
    assert wireless.amount('●前排慢充') == 100

    # #22d: n_usb reads subs & dotless text; usb_total sums 2nd/3rd row ports
    raw_usb = RawTable(trims=[Trim(0, 'A')], rows=[
        RawRow('USB/Type-C接口数量', [Cell(dot='●', text='前排2个', subs=[Cell(dot='●', text='后排2个')])]),
    ])
    assert mapper.n_usb(raw_usb, 0, {}) == 'USB/Type-C 4个'
    assert usb.usb_total('前排2个/后排2个/第三排2个') == 6
    assert usb.usb_total('前排2个/二排2个/三排2个') == 6


def _build_pptx(path: Path, rel_target: str, slide_xml: str):
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '</Types>'
    )
    pres = (
        '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst></p:presentation>'
    )
    rels = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="{rel_target}"/>'
        '</Relationships>'
    )
    with ZipFile(path, 'w') as z:
        z.writestr('[Content_Types].xml', content_types)
        z.writestr('ppt/presentation.xml', pres)
        z.writestr('ppt/_rels/presentation.xml.rels', rels)
        z.writestr('ppt/slides/slide1.xml', slide_xml)


def test_ppt_import_absolute_target_duplicate_names_table_prices(tmp_path):
    ns = ('xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
          'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"')
    # 1. Absolute slide target + duplicate trim name in footnote + comma/yuan prices
    slide_blocks = (
        f'<p:sld {ns}><p:cSld><p:spTree>'
        '<p:sp><p:spPr><a:xfrm><a:off x="100000" y="100000"/><a:ext cx="500000" cy="200000"/></a:xfrm></p:spPr>'
        '<p:txBody><a:p><a:r><a:t>基础版</a:t></a:r></a:p></p:txBody></p:sp>'
        '<p:sp><p:spPr><a:xfrm><a:off x="900000" y="100000"/><a:ext cx="500000" cy="200000"/></a:xfrm></p:spPr>'
        '<p:txBody><a:p><a:r><a:t>高配版</a:t></a:r></a:p></p:txBody></p:sp>'
        '<p:sp><p:spPr><a:xfrm><a:off x="100000" y="400000"/><a:ext cx="500000" cy="600000"/></a:xfrm></p:spPr>'
        '<p:txBody><a:p><a:r><a:t>基础配置：</a:t></a:r></a:p><a:p><a:r><a:t>LED大灯</a:t></a:r></a:p></p:txBody></p:sp>'
        '<p:sp><p:spPr><a:xfrm><a:off x="900000" y="400000"/><a:ext cx="500000" cy="600000"/></a:xfrm></p:spPr>'
        '<p:txBody><a:p><a:r><a:t>基础版+：</a:t></a:r></a:p><a:p><a:r><a:t>电动后备箱</a:t></a:r></a:p></p:txBody></p:sp>'
        '<p:sp><p:spPr><a:xfrm><a:off x="100000" y="2000000"/><a:ext cx="500000" cy="200000"/></a:xfrm></p:spPr>'
        '<p:txBody><a:p><a:r><a:t>基础版</a:t></a:r></a:p></p:txBody></p:sp>'
        '</p:spTree></p:cSld></p:sld>'
    )
    p1 = tmp_path / 'abs.pptx'
    _build_pptx(p1, '/ppt/slides/slide1.xml', slide_blocks)
    pages = ppt_import.list_pages(str(p1))
    assert len(pages) == 1
    parsed = ppt_import.parse_page(str(p1), 1)
    assert [c['name'] for c in parsed['columns']] == ['基础版', '高配版']
    assert parsed['columns'][1]['base'] == '基础版'

    # 2. Native table: guide price preserved over later TP price, empty first cell does not inherit 指导价
    tbl_xml = (
        f'<p:sld {ns}><p:cSld><p:spTree><p:graphicFrame>'
        '<p:xfrm><a:off x="0" y="0"/><a:ext cx="1000000" cy="1000000"/></p:xfrm>'
        '<a:graphic><a:graphicData><a:tbl>'
        '<a:tblGrid><a:gridCol w="300000"/><a:gridCol w="300000"/><a:gridCol w="300000"/></a:tblGrid>'
        '<a:tr h="100000"><a:tc><a:txBody><a:p><a:r><a:t>版型</a:t></a:r></a:p></a:txBody></a:tc>'
        '<a:tc><a:txBody><a:p><a:r><a:t>基础版</a:t></a:r></a:p></a:txBody></a:tc>'
        '<a:tc><a:txBody><a:p><a:r><a:t>高配版</a:t></a:r></a:p></a:txBody></a:tc></a:tr>'
        '<a:tr h="100000"><a:tc><a:txBody><a:p><a:r><a:t>指导价</a:t></a:r></a:p></a:txBody></a:tc>'
        '<a:tc><a:txBody><a:p><a:r><a:t>109,800元</a:t></a:r></a:p></a:txBody></a:tc>'
        '<a:tc><a:txBody><a:p><a:r><a:t>12.98万</a:t></a:r></a:p></a:txBody></a:tc></a:tr>'
        '<a:tr h="100000"><a:tc><a:txBody><a:p><a:r><a:t>TP价格</a:t></a:r></a:p></a:txBody></a:tc>'
        '<a:tc><a:txBody><a:p><a:r><a:t>9.98万</a:t></a:r></a:p></a:txBody></a:tc>'
        '<a:tc><a:txBody><a:p><a:r><a:t>11.98万</a:t></a:r></a:p></a:txBody></a:tc></a:tr>'
        '<a:tr h="100000"><a:tc><a:txBody><a:p/></a:txBody></a:tc>'
        '<a:tc><a:txBody><a:p><a:r><a:t>电动后备箱</a:t></a:r></a:p></a:txBody></a:tc>'
        '<a:tc><a:txBody><a:p><a:r><a:t>热泵</a:t></a:r></a:p></a:txBody></a:tc></a:tr>'
        '</a:tbl></a:graphicData></a:graphic></p:graphicFrame></p:spTree></p:cSld></p:sld>'
    )
    p2 = tmp_path / 'tbl.pptx'
    _build_pptx(p2, 'slides/slide1.xml', tbl_xml)
    parsed_tbl = ppt_import.parse_page(str(p2), 1)
    assert parsed_tbl['price_kind'] == '指导价'
    assert parsed_tbl['columns'][0]['price'] == 10.98
    assert parsed_tbl['columns'][1]['price'] == 12.98
    assert '电动后备箱' in parsed_tbl['columns'][0]['text']
    assert '热泵' in parsed_tbl['columns'][1]['text']

    # 3. _parse_table_page comma and yuan price parsing
    blocks = [
        {'x': 0, 'y': 0, 'w': 100000, 'h': 50000, 'lines': ['项目']},
        {'x': 200000, 'y': 0, 'w': 100000, 'h': 50000, 'lines': ['基础版']},
        {'x': 400000, 'y': 0, 'w': 100000, 'h': 50000, 'lines': ['高配版']},
        {'x': 0, 'y': 300000, 'w': 100000, 'h': 50000, 'lines': ['指导价']},
        {'x': 200000, 'y': 300000, 'w': 100000, 'h': 50000, 'lines': ['109,800元']},
        {'x': 400000, 'y': 300000, 'w': 100000, 'h': 50000, 'lines': ['129800元']},
    ]
    tbl_page = ppt_import._parse_table_page(str(p2), 1, blocks)
    assert tbl_page['columns'][0]['price'] == 10.98
    assert tbl_page['columns'][1]['price'] == 12.98


def test_comparison_review_no_false_positive_for_unmodified_optional_source():
    rules = Rules()
    raw = rawschema.detect_and_load(str(GOLDEN / 'raw-Q05-汽车之家全表-2026-09-11.json'), series_id='8241')
    comp_lad = ladder_mod.build_ladder(raw, rules, model='启源Q05', series_id='8241', date='2026-09-11')
    vt = ValuationTable(items=[ValuationItem(**it) for it in valuer.default_valuation(rules)['items']])
    pairs = [{'self_trim': '405Max', 'comp_trim': '506Max'}]
    cells = differ.diff(comp_lad, comp_lad, pairs, rules, valuation=vt)
    prices = {t['name']: t.get('price_guide') for t in comp_lad.trims}
    groups = differ.assemble_backup(cells, pairs, comp_lad.model, comp_lad.model, prices, prices, vt)
    review = comparison_review.build_review(comp_lad, comp_lad, pairs, rules, vt, cells, groups)
    for row in review['evidence']:
        for side in ('left', 'right'):
            notes = row[side]['notes']
            assert not any('计算用配置与原文识别不同' in n for n in notes), (row['no'], side, notes)


def test_render_5c_parameter_rows_missing_prices_and_empty_trims():
    empty_raw = RawTable(model='空车', trims=[], rows=[])
    assert '暂无版型数据' in render_5c.render_md(empty_raw)

    raw = RawTable(
        model='参数车',
        series_id='999',
        scraped_at='2026-11-25',
        trims=[Trim(0, '标准版', price_guide=9.98), Trim(1, '待定版', price_guide=None)],
        rows=[
            RawRow('电池能量(kWh)', [Cell(text='50'), Cell(text='60')]),
            RawRow('全景天窗', [Cell(dot='○', text='选装'), Cell(dot='●', text='')]),
        ],
    )
    md = render_5c.render_md(raw)
    assert '指导价 9.98 万' in md
    assert '电池能量(kWh)：50' in md
    assert '电池能量(kWh)：50 → 60' in md
    assert '**较标准版（价格待定）:（待定版）**' in md
    assert '+-' not in md


def test_feishu_missing_platform_package_is_not_integrity_error(tmp_path, monkeypatch):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    from engine import feishu_update

    key = Ed25519PrivateKey.generate()
    pub_bytes = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    fallback = Mock(spec=AppUpdater, _release=None)
    client = FeishuUpdater('0.3.7', pub_bytes, tmp_path / 'carkit.app' / 'Contents' / 'MacOS' / 'carkit',
                           installed=False, fallback=fallback)
    client.target = ('macos-x86_64', '.dmg', 'macOS Intel')
    manifest = json.dumps({
        'version': '0.3.8',
        'notes': 'release',
        'packages': {
            'macos-arm64': {'name': 'carkit-0.3.8-macos-arm64.dmg', 'size': 100, 'sha256': 'b' * 64},
        },
    }, ensure_ascii=False).encode()
    sig = key.sign(manifest)
    files = [('carkit-update.json', len(manifest)), ('carkit-update.json.sig', len(sig))]
    blocks = {f'B{i}': {'id': f'B{i}', 'data': {'type': 'file', 'file': {'name': n, 'token': f'T{i}', 'size': sz}}}
              for i, (n, sz) in enumerate(files)}
    doc = ('window.DATA = {clientVars: Object(' + json.dumps({'data': {'block_map': blocks}}) + ')}').encode()
    responses = {feishu_update.WIKI_URL: doc}
    for n, payload in [('carkit-update.json', manifest), ('carkit-update.json.sig', sig)]:
        _, url = feishu_update._attachment(feishu_update._files(doc.decode()), n)
        responses[url] = payload
    monkeypatch.setattr(client, '_open', lambda url: io.BytesIO(responses[url]))
    info = client.check()
    assert info['ok'] is True
    assert info['can_download'] is False
    assert '暂未提供' in info['reason']
    fallback.check.assert_not_called()


def test_acquirer_closed_page_and_filter_resume_and_rules_isolation(tmp_path):
    acq = acquire.Acquirer()
    fake_page = SimpleNamespace(
        is_closed=lambda: True,
        goto=lambda *a, **k: None,
    )
    acq.page = fake_page
    restarted = []
    new_page = SimpleNamespace(
        is_closed=lambda: False,
        goto=lambda *a, **k: None,
        locator=lambda *a, **k: SimpleNamespace(first=SimpleNamespace(wait_for=lambda **kw: (_ for _ in ()).throw(TimeoutError('captcha')))),
    )
    def fake_start():
        restarted.append(True)
        acq.page = new_page
    acq.start = fake_start
    res = acq.fetch('8241')
    assert restarted == [True]
    assert res['needs_browser'] is True
    assert acq.mode == 'filters'
    res2 = acq.resume()
    assert res2['needs_browser'] is True

    # Rules isolation
    orig_dir = rules_mod.RULES_DIR
    custom = tmp_path / 'custom_rules'
    custom.mkdir()
    for name in ('checklist_v1.json', 'exemptions.json', 'aliases.json'):
        (custom / name).write_text((Path(orig_dir) / name).read_text(encoding='utf-8'), encoding='utf-8')
    Rules(str(custom))
    assert rules_mod.RULES_DIR == orig_dir


def test_bridge_dialogs_workdir_template_left_check_and_path_safety(tmp_path, monkeypatch):
    # Relative workdir normalized (#30)
    monkeypatch.chdir(tmp_path)
    bridge = Bridge('rel_work')
    try:
        assert Path(bridge.workdir).is_absolute()

        # #29: open_file_dialog / save_file_dialog pass () when file_types is None
        seen_ft = []
        class Webview(SimpleNamespace):
            pass
        wv = Webview(
            FileDialog=SimpleNamespace(OPEN='open', SAVE='save'),
            windows=[SimpleNamespace(create_file_dialog=lambda *a, **kw: seen_ft.append(kw['file_types']) or ('/tmp/a',))],
        )
        monkeypatch.setitem(sys.modules, 'webview', wv)
        bridge.open_file_dialog()
        bridge.save_file_dialog('a.xlsx')
        assert seen_ft == [(), ()]

        # #31: make_valuation_template creates distinct files without overwriting
        t1 = bridge.make_valuation_template()
        t2 = bridge.make_valuation_template()
        assert t1['ok'] and t2['ok'] and t1['path'] != t2['path']

        # #33: list_files blocks traversal & abs paths; symlink rejected
        assert bridge.list_files('..') == []
        assert bridge.list_files('/etc') == []
        outside = tmp_path / 'outside.json'
        outside.write_text('{}', encoding='utf-8')
        sym = Path(bridge.workdir) / 'raw' / 'link.json'
        os.symlink(outside, sym)
        assert bridge.open_history('link.json')['ok'] is False
        assert bridge.prepare_competitor('link.json')['ok'] is False
        assert bridge.remove_vehicle_history('link.json')['ok'] is False

        # #32: run_diff rejects legacy left competitor missing #43/#44/#45
        rules = Rules()
        legacy_items = [LadderItem(no=it['no'], name=it['name'], values=['✕']) for it in rules.items if it['no'] not in (43, 44, 45)]
        full_items = [LadderItem(no=it['no'], name=it['name'], values=['✕']) for it in rules.items]
        left_p = tmp_path / 'left_old.json'
        right_p = tmp_path / 'right_new.json'
        Ladder(model='Left', trims=[{'name': 'A'}], items=legacy_items).save(str(left_p))
        Ladder(model='Right', trims=[{'name': 'B'}], items=full_items).save(str(right_p))
        diff_res = bridge.run_diff(str(left_p), str(right_p), [{'self_trim': 'A', 'comp_trim': 'B'}], left_is_competitor=True)
        assert diff_res['ok'] is False and '左侧竞品' in diff_res['error']

        # #30: opened plan with relative workdir still runs diff
        snap = ppt_import.make_snapshot({'model': 'Self', 'price_kind': '指导价', 'columns': [{'name': 'S', 'base': None, 'price': 10.0, 'text': 'LED大灯'}]})
        snap.status = '已确认'
        snap_p = Path(bridge.workdir) / '快照' / 'self.json'
        snap.save(str(snap_p))
        ok_diff = bridge.run_diff(str(snap_p), str(right_p), [{'self_trim': 'S', 'comp_trim': 'B'}])
        assert ok_diff['ok'] is True
        saved = bridge.save_comparison_plan('相对路径方案', ok_diff['comparison_id'])
        assert saved['ok'] is True
        plans = bridge.comparison_plans()['plans']
        opened = bridge.open_comparison_plan(plans[0]['file'])
        assert opened['ok'] is True
        rerun = bridge.run_diff(opened['paths']['left'], opened['paths']['right'],
                                opened['inputs']['pairs'], opened['paths']['valuation'],
                                plan_session=opened['session'])
        assert rerun['ok'] is True
    finally:
        bridge.shutdown()


def test_cli_diff_rejects_legacy_ladder_missing_new_items(tmp_path):
    rules = Rules()
    snap = ppt_import.make_snapshot({'model': 'S', 'price_kind': '指导价', 'columns': [{'name': 'A', 'base': None, 'price': 10.0, 'text': 'LED大灯'}]})
    sp = tmp_path / 'snap.json'
    snap.save(str(sp))
    legacy_items = [LadderItem(no=it['no'], name=it['name'], values=['✕']) for it in rules.items if it['no'] not in (43, 44, 45)]
    lp = tmp_path / 'lad.json'
    Ladder(model='C', trims=[{'name': 'B'}], items=legacy_items).save(str(lp))
    with pytest.raises(SystemExit) as exc:
        cli.cmd_diff(SimpleNamespace(snapshot=str(sp), ladder=str(lp), pairs='A:B', valuation=None, o=None, json=None))
    assert '缺少新配置项' in str(exc.value)


def test_macos_workflow_and_pyproject_packaging_guards():
    wf = (ROOT / '.github' / 'workflows' / 'macos.yml').read_text(encoding='utf-8')
    assert "if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')" in wf
    assert 'exit 1' in wf.splitlines()[-1]
    py = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    assert '"ui"' in py and 'ui = [' in py


def test_frontend_medium_fixes():
    # #36 single toast, #37 left save preserves pairs, #38 snapshot save & invalidate, #39 option value,
    # #40 scrape_continue recovery, #41 capture-filters hidden, #44 same-vehicle sync
    run_node(r"""
const toasts=[];
context.toast=(msg,cls)=>toasts.push([msg,cls]);
context.window={...context.window,pywebview:{api:{failMethod:async()=>({ok:false,error:'后端报错'})}}};
load('async function api(', '/* ---------- 导航 ---------- */');
await assert.rejects(context.api('failMethod'), /后端报错/);
assert.strictEqual(toasts.length,1);
assert.deepStrictEqual(toasts[0],['后端报错','err']);

// #37 + #44: left save preserves pairs and syncs when both sides share path
load("$('#diff-edit-self').onclick", "$('#back-to-diff').onclick");
context.collectLadderEdits=()=>{};
context.setPairGuidePrices=()=>{};
node('#diff-mode').value='competitor';
node('#diff-self-editor').hidden=false;
node('#diff-competitor-editor').hidden=true;
pair('T1','T2');
ST.leftLadder={model:'Same',trims:[{name:'T1'}],items:[{no:3,values:['800V']}]};
ST.leftLadderPath='阶梯/same.json';
ST.ladder={model:'Same',trims:[{name:'T1'}],items:[{no:3,values:['400V']}]};
ST.ladderPath='阶梯/same.json';
node('#diff-ladder-table-wrap').model=ST.ladder;
context.api=async()=>({ok:true});
await node('#diff-save-self').onclick();
assert.strictEqual(node('#pairs-editor').rows.length,1,'pairs preserved');
assert.strictEqual(ST.ladder.items[0].values[0],'800V','right synced');
assert.strictEqual(node('#diff-ladder-table-wrap').model,undefined,'right editor unmounted');

// #40 + #41: capture-filters hidden on search/load & btn-scrape-capture recoverable
load('$("#btn-scrape-open").addEventListener', 'function renderCaptureFilters(');
node('#scrape-series').value='启源Q05';
const filtersNode=node('#capture-filters');filtersNode.hidden=false;filtersNode.open=true;
context.api=async()=>{throw new Error('请完成验证');};
await node('#btn-scrape-open').listeners.click[0]();
assert.strictEqual(filtersNode.hidden,true);
assert.strictEqual(node('#scrape-status').textContent,'请完成验证');
node('#btn-scrape-capture').hidden=false;
await node('#btn-scrape-capture').listeners.click[0]();
assert.strictEqual(node('#btn-scrape-capture').hidden,false,'stays visible on failure for retry');
assert.strictEqual(node('#btn-scrape-capture').disabled,false);

// #38: invalidateDraftPreview clears snapshot table
load('function invalidateDraftPreview()', 'function updateProductDraftCopy(');
ST.snapshot={model:'X'};ST.snapshotPath='快照/x.json';
node('#snapshot-table-wrap').model=ST.snapshot;
context.invalidateDraftPreview();
assert.strictEqual(ST.snapshot,null);
assert.strictEqual(node('#snapshot-table-wrap').model,undefined);
assert.strictEqual(node('#btn-save-snapshot').hidden,true);
""")

    # #39: option value preserves consecutive spaces in pair row
    run_node(r"""
context.document={createElement(){
  const fields={},row={listeners:{},
    addEventListener(event,handler){(this.listeners[event] ||= []).push(handler);},
    querySelector:selector=>fields[selector]};
  let html='';
  Object.defineProperty(row,'innerHTML',{get(){return html;},set(value){
    html=value;
    for(const name of ['pair-self','pair-comp','pair-del']) {
      const m=value.match(new RegExp('<select class="'+name+'"[^>]*>([\\s\\S]*?)</select>'));
      const o=m?.[1].match(/<option(?: value="([^"]*)")?[^>]*>(.*?)<\/option>/);
      fields['.'+name]={value:o?(o[1]??o[2]):'',addEventListener(){}};
    }
  }});
  return row;
}};
node('#pairs-editor').appendChild=row=>node('#pairs-editor').rows.push(row);
load('function addPairRow(', 'function collectComparisonPairs(');
context.addPairRow(['2026款  尊享版'],['405Max']);
assert.strictEqual(node('#pairs-editor').rows[0].querySelector('.pair-self').value,'2026款  尊享版');
""")

    # #42: ConfigEditor.validate blurs focused input inside root
    run_editor(r"""
let blurred=false;
const fakeActive={blur(){blurred=true;}};
context.document={activeElement:fakeActive};
const root={contains:el=>el===fakeActive,querySelectorAll:()=>[{reportValidity:()=>true}]};
assert.strictEqual(context.window.ConfigEditor.validate(root),true);
assert.strictEqual(blurred,true);
""")

    # #43: PptDraftEditor clearing trim name updates model and invalidates
    run_node(r"""
let invalidated=0, def;
context.Vue={ref:v=>({value:v}),computed:fn=>({get value(){return fn();}}),createApp:opts=>{def=opts;return {mount(){},unmount(){}};}};
vm.runInContext(fs.readFileSync('ui/ppt-draft-editor.js','utf8'),context);
const draft={columns:[{name:'基础',base:null},{name:'高配',base:'基础'}]};
context.window.PptDraftEditor.mount({classList:{add(){}}},draft,{onInvalidate:()=>{invalidated++;}});
const setup=def.setup();
setup.rename(0,{target:{value:'   '}});
assert.strictEqual(draft.columns[0].name,'');
assert.strictEqual(draft.columns[1].base,null);
assert.strictEqual(invalidated,1);
""")
