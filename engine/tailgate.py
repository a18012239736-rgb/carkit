"""Standard power-tailgate equipment; position memory is not hands-free sensing."""
import re


def _standard(value):
    text = str(value or '').strip()
    if text.startswith('○') or '[待' in text or '?' in text or '？' in text:
        return ''
    text = re.sub(r'[（(][^()（）]*(?:○|选装|选配)[^()（）]*[)）]', '', text)
    return re.split(r'[,，+＋]\s*○', text, maxsplit=1)[0].strip()


def has_sensing(value):
    text = _standard(value)
    text = re.sub(r'感应(?:式)?雨[刮刷]', '', text)
    if re.search(r'(?:无|没有|不带|不支持|非)\s*感应', text):
        return False
    return '感应' in text


def components(value):
    text = _standard(value)
    if (not text or re.fullmatch(r'(?:✕|×|—|-|无)(?:[（(].*[)）])?', text)
            or ('手动' in text and '电动' not in text)):
        return False, False
    return True, has_sensing(text)


def label(value):
    powered, sensing = components(value)
    return '感应电动后备箱' if sensing else '电动后备箱' if powered else '✕'
