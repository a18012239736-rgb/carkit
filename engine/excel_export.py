"""Export the current report results as formatted Excel tables."""
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE


def export_report(path, kind, data):
    book = Workbook()
    book.remove(book.active)

    def sheet(name, rows):
        ws = book.create_sheet(name)
        for row in rows:
            ws.append([ILLEGAL_CHARACTERS_RE.sub('', x) if isinstance(x, str) else x for x in row])
        for row in ws:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = 's'
                cell.font = Font(name='Calibri', size=11)
                cell.alignment = Alignment(vertical='top', wrap_text=True)
                if isinstance(cell.value, (int, float)):
                    cell.number_format = '#,##0.##;[Red]-#,##0.##'
        for cell in ws[1]:
            cell.fill = PatternFill('solid', fgColor='245E6B')
            cell.font = Font(name='Calibri', bold=True, color='FFFFFF')
        for i in range(1, ws.max_column + 1):
            ws.column_dimensions[get_column_letter(i)].width = 30 if i < 4 else 48
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions

    if kind == 'ladder':
        sheet('配置阶梯', [['车型', '版型', '指导价（万元）', '比较基准', '基础配置或差异配置', '选装配置']] + [
            [data['model'], c['name'], c.get('price'), c.get('base') or '基础配置',
             '\n'.join(c['items']), '\n'.join(c['options'])] for c in data['columns']])
    elif kind == 'diff':
        groups = data['groups']
        sheet('对比汇总', [['左侧车型', '左侧版型', '右侧车型', '右侧版型', '左侧指导价（万元）', '右侧指导价（万元）', '多配置', '少配置', '配置优势（元）', '拉平指导价优势（元）', '综合竞争力', '待赋值项目编号']] + [
            [data.get('self_model'), g['pair']['self_trim'], data.get('comp_model'), g['pair']['comp_trim'],
             g.get('self_price'), g.get('comp_price'), '\n'.join(g['more']), '\n'.join(g['less']),
             g.get('valuation', {}).get('config_adv'), g.get('valuation', {}).get('flat_adv'),
             g.get('valuation', {}).get('overall') if g.get('valuation', {}).get('overall') is not None else '未计算',
             '、'.join(map(str, g.get('valuation', {}).get('missing', [])))] for g in groups])
        sheet('赋值明细', [['左侧版型', '右侧版型', '多或少', '配置差异', '计价依据', '金额（元）']] + [
            [g['pair']['self_trim'], g['pair']['comp_trim'], d['side'], d.get('display'), d.get('rule'), d.get('amount')]
            for g in groups for d in g.get('valuation', {}).get('detail', [])])
        sheet('配置判定', [['左侧版型', '右侧版型', '项目编号', '配置名称', '左侧配置', '右侧配置', '判定', '差异说明']] + [
            [groups[c['pair']]['pair']['self_trim'], groups[c['pair']]['pair']['comp_trim'], c['no'],
             c.get('name'), c.get('self_val'), c.get('comp_val'), c.get('verdict'), c.get('display')]
            for c in data['cells']])
    else:
        raise ValueError('不支持的导出类型')
    book.save(path)
