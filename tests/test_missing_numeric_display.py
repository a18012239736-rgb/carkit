import pytest
from engine.differ import _backup_display, MORE, LESS


@pytest.mark.parametrize('no', [1, 5, 21, 29, 37])
@pytest.mark.parametrize('absent', [None, '', '✕'])
def test_numeric_summary_handles_absence_on_either_side(no, absent):
    _, less = _backup_display(no, LESS, absent, '12', '✕', '12')
    more, _ = _backup_display(no, MORE, '12', absent, '12', '✕')
    assert '12' in less and 'None' not in less
    assert '12' in more and 'None' not in more
