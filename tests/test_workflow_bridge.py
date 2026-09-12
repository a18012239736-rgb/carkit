from pathlib import Path
from api.bridge import Bridge
from engine import rawschema

def test_history_and_comparison_preserve_capture_and_edits(tmp_path):
    bridge = Bridge(str(tmp_path))
    raw = rawschema.detect_and_load(str(Path(__file__).parent/'golden'/'raw-Q05-汽车之家全表-2026-09-11.json'))
    raw.scraped_at='2026-09-12T12:00:00'
    for trim in raw.trims:
        trim.full='2026款 '+trim.short
    raw.save(str(tmp_path/'raw'/'capture.json'))
    history=bridge.vehicle_history()
    assert raw.model in history[0]['label']
    assert '2026款' in history[0]['label']
    assert '2026-09-12' in history[0]['label']
    assert bridge.open_history('capture.json')['ok']
    result=bridge.prepare_competitor('capture.json')
    assert result['ok']
    ladder=result['ladder']
    ladder['items'][0]['values'][0]='人工修正'
    assert bridge.save_ladder_edit(result['path'],ladder)['ok']
    assert bridge.prepare_competitor('capture.json')['ladder']['items'][0]['values'][0]=='人工修正'
    assert bridge.stage_raw.model==raw.model
    assert not bridge.open_history('../capture.json')['ok']
