"""座椅功能按座位和功能存储；旧合并字段在读取时展开。"""
import re

FEATURES = ('通风', '加热', '按摩', '头枕音响')
SEATS = ('主驾', '副驾', '二排')
SUBS = tuple(seat + feature for feature in FEATURES for seat in SEATS)
PRICES = {'通风': 400, '加热': 250, '按摩': 600, '头枕音响': 100}


def empty():
    return {sub: '✕' for sub in SUBS}


def _front_scopes(phrase, *, legacy=False, previous_mapping=False):
    if not legacy and not previous_mapping:
        if re.search(r'\((?:仅)?(?:驾驶位|主驾(?:驶(?:位|座)?)?)\)', phrase):
            return ('主驾',)
        if re.search(r'\((?:仅)?副驾(?:驶(?:位|座)?)?\)', phrase):
            return ('副驾',)
    driver = r'仅(?:驾驶位|主驾)|主驾|主驾驶' + ('' if legacy else r'|(?<!副)驾驶位')
    if re.search(driver, phrase) and not re.search(r'副驾|副驾驶|主副|前排', phrase):
        return ('主驾',)
    if re.search(r'仅副驾|副驾|副驾驶', phrase) and not re.search(r'主驾|主驾驶|主副|前排', phrase):
        return ('副驾',)
    return ('主驾', '副驾')


_SCOPE_RE = r'主驾|副驾|驾驶位|前排|主副|二排|后排'


def _split_phrases(text, *, normalize_parens=True):
    text = str(text or '')
    if normalize_parens:
        text = text.replace('（', '(').replace('）', ')')
    phrases = []
    buf = []
    depth = 0
    for i, ch in enumerate(text):
        if ch == '(':
            depth += 1
            buf.append(ch)
        elif ch == ')':
            depth = max(0, depth - 1)
            buf.append(ch)
            if depth == 0:
                nxt = text[i + 1:i + 2]
                if nxt and nxt not in '+＋；;、,，\n/':
                    phrases.append(''.join(buf).strip())
                    buf = []
        elif depth == 0 and ch in '+＋；;、,，\n':
            part = ''.join(buf).strip()
            if part:
                phrases.append(part)
            buf = []
        elif depth == 0 and ch == '/':
            left = ''.join(buf)
            right = text[i + 1:].lstrip()
            if re.search(_SCOPE_RE + r'|\)', left) or re.match(r'(?:○|' + _SCOPE_RE + r')', right):
                part = left.strip()
                if part:
                    phrases.append(part)
                buf = []
            else:
                buf.append(ch)
        else:
            buf.append(ch)
    tail = ''.join(buf).strip()
    if tail:
        phrases.append(tail)
    return phrases


def _standard_phrases(value, *, legacy=False, previous_mapping=False):
    raw = str(value or '').strip()
    if not raw:
        return []
    if legacy or previous_mapping:
        return _split_phrases(raw, normalize_parens=not legacy)
    if raw.startswith('○') and '●' not in raw:
        return []
    from .differ import _standard_configuration
    out = []
    for phrase in _split_phrases(raw, normalize_parens=True):
        std = _standard_configuration(phrase)
        if std and std != '✕':
            out.append(std)
    return out


def from_text(front='', rear='', headrest='', *, legacy=False, front_scope_known=False, headrest_scope_known=False,
              previous_mapping=False):
    out = empty()
    for text, seats in ((front, ('主驾', '副驾')), (rear, ('二排',))):
        for phrase in _standard_phrases(text, legacy=legacy, previous_mapping=previous_mapping):
            if not legacy:
                phrase = phrase.replace('头枕扬声器', '头枕音响').replace('头枕喇叭', '头枕音响')
            scopes = _front_scopes(phrase, legacy=legacy, previous_mapping=previous_mapping) if seats[0] != '二排' else seats
            recognized = phrase if legacy or previous_mapping else phrase.replace('头枕加热', '')
            for feature in FEATURES:
                if feature in recognized:
                    for seat in scopes:
                        out[seat + feature] = ('[待定]请确认头枕音响座位' if feature == '头枕音响'
                            and seat != '二排' and not front_scope_known
                            and not any(scope in phrase for scope in ('主驾','副驾','前排','主副','驾驶位')) else '●')
    if headrest and headrest not in ('✕', '×', '-', '无', '无配置'):
        known_scopes = (*SEATS, '前排') if legacy else (*SEATS, '前排', '主副', '驾驶位', '后排')
        for phrase in _standard_phrases(headrest, legacy=legacy, previous_mapping=previous_mapping):
            rear_hit = '二排' in phrase or '后排' in phrase
            front_explicit = any(scope in phrase for scope in ('主驾', '副驾', '前排', '主副', '驾驶位'))
            if rear_hit:
                out['二排头枕音响'] = '●'
            if front_explicit or not rear_hit:
                if not headrest_scope_known and not any(scope in phrase for scope in known_scopes):
                    for seat in ('主驾', '副驾'):
                        out[seat + '头枕音响'] = '[待定]请确认头枕音响座位'
                else:
                    for seat in _front_scopes(phrase, legacy=legacy, previous_mapping=previous_mapping):
                        out[seat + '头枕音响'] = '●'
    return out


def normalize(value):
    from .differ import _standard_configuration
    value = _standard_configuration(value)
    if isinstance(value, dict) and all(key in value for key in SUBS):
        return value
    if isinstance(value, dict):
        out = empty()
        for key, state in value.items():
            if key in out:
                out[key] = state
            elif key == '前加热通风' and state == '●':
                for seat in ('主驾', '副驾'):
                    out[seat+'加热'] = out[seat+'通风'] = '●'
            elif key == '前按摩' and state == '●':
                for seat in ('主驾', '副驾'):
                    out[seat+'按摩'] = '●'
            elif key == '二排' and state == '●':
                for feature in ('加热', '通风', '按摩'):
                    out['二排'+feature] = '[待定]请确认二排具体功能'
            elif key == '二排' and state not in ('✕', '', None):
                out.update({k:v for k,v in from_text(rear=state).items() if v != '✕'})
            elif key in ('头枕音响', '头枕') and state == '●':
                out['主驾头枕音响'] = out['副驾头枕音响'] = '[待定]请确认头枕音响座位'
        return out
    if isinstance(value, str) and '[待定]' in value:
        return {sub:'[待定]请核对座椅功能' for sub in SUBS}
    return from_text(str(value)) if value not in ('', '✕', None) else empty()
