from engine.differ import _backup_display

def test_power_tailgate_has_specific_label():
    assert _backup_display(13, '多', '●', '✕', '●', '✕') == ('电动后备箱', '')
