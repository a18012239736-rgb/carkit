"""Per-trim applicability; unknown energy types are never guessed from model names."""

def energy_types(raw):
    row = raw.row('能源类型')
    return [c.text.strip() for c in row.cells] if row else [''] * len(raw.trims)


def not_applicable(energy, no):
    # Only electric range has powertrain-specific valuation applicability.
    # All other checklist items retain the original comparison rules.
    combustion = energy in {'汽油', '柴油', '天然气', '汽油+天然气', '汽油+CNG', '汽油+48V轻混系统', '柴油+48V轻混系统'}
    hev = energy in {'油电混合', '汽油电驱'}
    return no == 1 and (combustion or hev)
