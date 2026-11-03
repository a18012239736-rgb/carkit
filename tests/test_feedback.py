import base64
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from engine import feedback


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')


def image(content=PNG, name='C:\\Users\\private-name\\Desktop\\secret.png', kind='png'):
    return {'name': name, 'data_url': f'data:image/{kind};base64,' + base64.b64encode(content).decode()}


def test_feedback_preserves_text_and_selected_images_without_local_path_leaks(tmp_path, monkeypatch):
    monkeypatch.setattr(feedback.platform, 'system', lambda: 'Windows')
    result = feedback.prepare_feedback(tmp_path, {'title': '座椅显示问题 <test>',
                                               'description': '第一步：修改座椅\n实际：没有显示',
                                               'images': [image()]}, '0.2.3')
    assert result['ok'] and result['has_images'] and not result['requires_paste']
    folder = Path(result['folder'])
    assert folder.parent == tmp_path / '反馈'
    assert (folder / '截图-1.png').read_bytes() == PNG
    note = (folder / '反馈说明.md').read_text(encoding='utf-8')
    assert '程序版本：0.2.3' in note and '系统：Windows' in note
    assert 'private-name' not in note and str(tmp_path) not in note
    assert '尚未上传或提交' in note
    url = urlsplit(result['issue_url'])
    assert (url.scheme, url.netloc, url.path) == ('https', 'github.com', '/a18012239736-rgb/carkit/issues/new')
    query = parse_qs(url.query)
    assert query['title'] == ['[使用反馈] 座椅显示问题 <test>']
    assert query['body'] == [result['body']]
    again = feedback.prepare_feedback(tmp_path, {'title': '第二次', 'description': '文字反馈'}, '0.2.3')
    assert again['folder'] != result['folder'] and folder.is_dir()


def test_text_only_and_image_only_feedback_are_allowed(tmp_path):
    text = feedback.prepare_feedback(tmp_path, {'title': '建议', 'description': '增加搜索'}, '0.2.3')
    assert not text['has_images'] and text['image_names'] == []
    screenshot = feedback.prepare_feedback(tmp_path, {'title': '截图反馈', 'images': [image()]}, '0.2.3')
    assert screenshot['has_images'] and '请见截图' in screenshot['body']


@pytest.mark.parametrize('payload,expected', [
    (None, '格式无效'),
    ({'title': '', 'description': 'abc'}, '标题'),
    ({'title': 'x' * 121, 'description': 'abc'}, '标题'),
    ({'title': '标题'}, '说明或添加截图'),
    ({'title': '标题', 'description': 'x' * 10001}, '10000'),
    ({'title': '标题', 'images': [image()] * 4}, '3张'),
    ({'title': '标题', 'images': 'x'}, '3张'),
    ({'title': '标题', 'images': [{'data_url': 'data:image/svg+xml;base64,PHN2Zz4='}]}, 'PNG/JPEG'),
    ({'title': '标题', 'images': [image(b'not a picture')]}, '有效的'),
    ({'title': '标题', 'images': [{'data_url': 'data:image/png;base64,===='}]}, '编码无效'),
    ({'title': '标题', 'images': [{}]}, '格式无效'),
])
def test_invalid_feedback_is_rejected_before_creating_any_files(tmp_path, payload, expected):
    with pytest.raises(ValueError, match=expected):
        feedback.prepare_feedback(tmp_path, payload, '0.2.3')
    assert list(tmp_path.iterdir()) == []


def test_image_limits_are_checked_before_files_are_written(tmp_path, monkeypatch):
    monkeypatch.setattr(feedback, 'MAX_IMAGE_BYTES', len(PNG) - 1)
    with pytest.raises(ValueError, match='5MB'):
        feedback.prepare_feedback(tmp_path, {'title': '标题', 'images': [image()]}, '0.2.3')
    monkeypatch.setattr(feedback, 'MAX_IMAGE_BYTES', len(PNG))
    monkeypatch.setattr(feedback, 'MAX_TOTAL_BYTES', len(PNG))
    with pytest.raises(ValueError, match='总大小'):
        feedback.prepare_feedback(tmp_path, {'title': '标题', 'images': [image(), image()]}, '0.2.3')
    assert list(tmp_path.iterdir()) == []


def test_long_description_is_kept_complete_locally_and_copyable_instead_of_truncated(tmp_path):
    description = '请核对这一处异常。' * 800
    result = feedback.prepare_feedback(tmp_path, {'title': '长反馈', 'description': description}, '0.2.3')
    assert result['requires_paste'] and len(result['issue_url']) <= 6000
    assert description in result['body']
    assert description in (Path(result['folder']) / '反馈说明.md').read_text(encoding='utf-8')
    assert '完整反馈已在程序中准备' in parse_qs(urlsplit(result['issue_url']).query)['body'][0]


def test_failed_write_removes_only_new_feedback_folder(tmp_path, monkeypatch):
    existing = tmp_path / '反馈' / '已有反馈'
    existing.mkdir(parents=True)
    original = existing / '重要.txt'
    original.write_text('原有资料', encoding='utf-8')

    def fail(*args):
        raise OSError('磁盘写入失败')

    monkeypatch.setattr(feedback, 'atomic_write_text', fail)
    with pytest.raises(OSError, match='磁盘写入失败'):
        feedback.prepare_feedback(tmp_path, {'title': '标题', 'images': [image()]}, '0.2.3')
    assert list((tmp_path / '反馈').iterdir()) == [existing]
    assert original.read_text(encoding='utf-8') == '原有资料'


def test_feedback_directory_cannot_escape_workdir_through_symlink(tmp_path):
    work, elsewhere = tmp_path / 'work', tmp_path / 'elsewhere'
    work.mkdir(); elsewhere.mkdir()
    (work / '反馈').symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(ValueError, match='目录路径无效'):
        feedback.prepare_feedback(work, {'title': '标题', 'description': '反馈'}, '0.2.3')
    assert not list(elsewhere.iterdir())
