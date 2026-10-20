from pathlib import Path

from lxml import html


INDEX = Path(__file__).resolve().parents[1] / 'ui' / 'index.html'


def document():
    return html.fromstring(INDEX.read_text(encoding='utf-8'))


def by_id(root, identifier):
    matches = root.xpath(f'.//*[@id="{identifier}"]')
    assert len(matches) == 1, identifier
    return matches[0]


def test_workspace_styles_load_after_existing_component_styles():
    styles = document().xpath('//head/link[@rel="stylesheet"]/@href')
    assert styles[-1].split('?', 1)[0] == 'workspace.css'


def test_history_is_available_in_the_search_card_but_initially_collapsed():
    root = document()
    history = by_id(root, 'raw-history')
    assert history.tag == 'details'
    assert 'open' not in history.attrib
    assert history.xpath('ancestor::*[contains(concat(" ", normalize-space(@class), " "), " search-card ")]')
    assert by_id(root, 'raw-list') in history.iterdescendants()


def test_stage_settings_and_persistent_result_actions_follow_trim_selection():
    root = document()
    settings = by_id(root, 'stage-display-settings')
    result_tools = by_id(root, 'stage-result-tools')
    assert settings.getparent().get('id') == 'page-scrape'
    assert settings.getprevious().get('id') == 'stage-trims'
    assert 'hidden' in settings.attrib
    assert result_tools.getprevious() is settings
    assert by_id(root, 'stage-result-actions') in result_tools.iterdescendants()
    assert by_id(root, 'stage-export-status') in result_tools.iterdescendants()


def test_saving_belongs_to_results_and_opening_plans_stays_in_the_plan_picker():
    root = document()
    result = by_id(root, 'diff-result')
    controls = by_id(root, 'comparison-save-controls')
    assert controls in result.iterdescendants()
    for identifier in ['comparison-plan-name', 'btn-save-plan']:
        assert by_id(root, identifier) in controls.iterdescendants()
    picker = by_id(root, 'comparison-plan-list')
    assert picker.xpath('ancestor::details[contains(concat(" ", normalize-space(@class), " "), " comparison-plans ")]')
    assert picker not in result.iterdescendants()


def test_result_details_are_initially_collapsed_below_the_primary_table():
    root = document()
    result = by_id(root, 'diff-result')
    details = by_id(root, 'comparison-detail-section')
    review = by_id(root, 'comparison-review')
    assert details in result.iterdescendants()
    assert by_id(root, 'detail-table') in details.iterdescendants()
    for section in [details, review]:
        assert section.tag == 'details'
        assert 'open' not in section.attrib
    assert list(result.iterdescendants()).index(by_id(root, 'backup-table')) < list(result.iterdescendants()).index(details)
