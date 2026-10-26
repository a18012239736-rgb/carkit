"""Seat comparison wording and explicit source evidence remain independent."""
import pytest

from engine import seat_adjust, stage_one
from engine.models import Cell


@pytest.mark.parametrize('current,previous,expected', [
    ('主驾6向电调+副驾4向手调', '主驾6向手调+副驾4向手调',
     '主驾电调（主驾手调）'),
    ('主驾8向电调+副驾4向手调', '主驾6向电调+副驾4向手调',
     '主驾8向（主驾6向）'),
    ('主驾8向电调+副驾4向手调', '主驾6向手调+副驾4向手调',
     '主驾8向电调（主驾6向手调）'),
    ('主驾8向电调+副驾6向电调', '主驾6向手调+副驾4向手调',
     '主驾8向电调+副驾6向电调（主驾6向手调+副驾4向手调）'),
    ('主驾8向电调+副驾6向电调', '主驾8向手调+副驾4向电调',
     '主驾电调+副驾6向（主驾手调+副驾4向）'),
    ('主驾8向电调+副驾6向电调', '主驾8向电调+副驾4向电调',
     '副驾6向（副驾4向）'),
    ('主驾8向电调+副驾6向电调', '主驾8向电调+副驾6向电调', ''),
    ('主驾电调+副驾4向手调', '主驾6向电调+副驾4向手调',
     '主驾方向未说明（主驾6向）'),
    ('主驾6向+副驾4向手调', '主驾6向电调+副驾4向手调',
     '主驾方式未说明（主驾电调）'),
    ('主驾6向调节+副驾4向手调', '主驾6向电调+副驾4向手调',
     '主驾方式未说明（主驾电调）'),
    ('主驾6向电调', '主驾6向电调+副驾4向手调',
     '副驾调节未说明（副驾4向手调）'),
    ('主驾12向电调（主含腰撑4向）+副驾8向电调（副含腿托2向）',
     '主驾10向电调+副驾8向电调', '主驾12向（主驾10向）'),
    ('主驾12向电调（主含腰撑4向）+副驾8向电调（副含腿托2向）',
     '主驾12向电调+副驾8向电调', ''),
])
def test_difference_shows_only_changed_fields_with_one_baseline(current, previous, expected):
    assert seat_adjust.difference_label(current, previous) == expected


@pytest.mark.parametrize('current,previous', [
    ('○主驾8向电调+副驾4向手调', '主驾6向手调+副驾4向手调'),
    ('主驾8向电调+副驾4向手调', '○主驾6向电调+副驾4向手调'),
    ('[待定]主驾8向电调', '主驾6向电调'),
    ('主驾8向电调', '[待pjy核]主驾6向电调'),
    ('主驾8向电调+副驾未知', '主驾6向电调+副驾4向手调'),
    ('✕', '主驾6向电调+副驾4向手调'),
])
def test_optional_pending_and_unparseable_values_keep_existing_fallback(current, previous):
    assert seat_adjust.difference_label(current, previous) is None


@pytest.mark.parametrize('items,expected', [
    ([('主驾座椅调节', '主驾8向电调（主驾6向电调）'),
      ('副驾座椅调节', '副驾6向电调（副驾4向电调）')],
     ['主驾8向+副驾6向（主驾6向+副驾4向）']),
    ([('主驾座椅调节', '主驾8向电调（主驾6向电调）'),
      ('副驾座椅调节', '副驾4向手调')],
     ['主驾8向（主驾6向）+副驾4向手调']),
    ([('主驾座椅调节', '主驾8向电调（主驾6向电调）'),
      ('副驾座椅调节', '无（副驾4向手调）')],
     ['主驾8向（主驾6向）+无（副驾4向手调）']),
    ([('主驾座椅调节', '主驾8向电调'),
      ('副驾座椅调节', '副驾6向电调（副驾4向电调）')],
     ['主驾8向电调+副驾6向（副驾4向）']),
])
def test_compact_items_also_compresses_comparison_next_to_added_or_removed_seat(items, expected):
    assert stage_one._compact_items(items, 0) == expected


@pytest.mark.parametrize('support', ['腰部支撑(4向)', '腿托调节', '腿部支撑调节(2向)'])
def test_explicit_total_is_not_lost_when_support_is_a_separate_subitem(support):
    cell = Cell(dot='●', text='8向电动', subs=[Cell(dot='●', text=support)])
    assert seat_adjust.raw_directions(cell) == 8
    assert seat_adjust.raw_modes(None, cell) == ['电调', '手调']


@pytest.mark.parametrize('text,expected', [
    ('主●／副●', ['电调', '电调']),
    ('主●＋副-', ['电调', '手调']),
    ('主驾电调／副驾手调', ['电调', '手调']),
])
def test_raw_modes_accepts_fullwidth_separators(text, expected):
    assert seat_adjust.raw_modes(Cell(dot='●', text=text)) == expected
