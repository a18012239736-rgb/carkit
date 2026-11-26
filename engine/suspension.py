"""Suspension capabilities used by both comparison and valuation."""
import re


def components(value):
    text = str(value or '').strip()
    if (not text or text.startswith('○') or text in ('选装', '选配')
            or re.search(r'[（(]\s*(?:选装|选配)\s*[)）]\s*$', text)
            or '[待定]' in text):
        return set()
    text = re.sub(r'[（(][^()（）]*(?:○|选装|选配)[^()（）]*[)）]', '', text)
    text = '+'.join(part for part in re.split(r'[+＋/／,，、]', text) if not part.strip().startswith('○'))
    # pjy: air/magic-carpet suspension is the soft/hard + height combination.
    if '空气' in text or '魔毯' in text:
        return {'soft_hard', 'height_or_air'}
    return {key for key, word in (('soft_hard', '软硬'), ('height_or_air', '高低')) if word in text}


def amount(value, params):
    return sum(params[key] for key in components(value))
