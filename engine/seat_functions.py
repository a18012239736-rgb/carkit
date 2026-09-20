"""座椅功能按座位和功能存储；旧合并字段在读取时展开。"""
import re

FEATURES = ('通风', '加热', '按摩', '头枕音响')
SEATS = ('主驾', '副驾', '二排')
SUBS = tuple(seat + feature for feature in FEATURES for seat in SEATS)
PRICES = {'通风': 400, '加热': 250, '按摩': 600, '头枕音响': 100}


def empty():
    return {sub: '✕' for sub in SUBS}


def _front_scopes(phrase):
    if re.search(r'仅(?:驾驶位|主驾)|主驾|主驾驶', phrase) and not re.search(r'副驾|副驾驶|主副|前排', phrase):
        return ('主驾',)
    if re.search(r'仅副驾|副驾|副驾驶', phrase) and not re.search(r'主驾|主驾驶|主副|前排', phrase):
        return ('副驾',)
    return ('主驾', '副驾')


def from_text(front='', rear='', headrest=''):
    out = empty()
    for text, seats in ((front, ('主驾', '副驾')), (rear, ('二排',))):
        for phrase in re.split(r'[+＋；;、\n]|(?<=\))(?=[^\s])', str(text)):
            scopes = _front_scopes(phrase) if seats[0] != '二排' else seats
            for feature in FEATURES:
                if feature in phrase:
                    for seat in scopes:
                        out[seat + feature] = ('[待定]请确认头枕音响座位' if feature == '头枕音响'
                            and seat != '二排' and not any(scope in phrase for scope in ('主驾','副驾','前排','主副','驾驶位')) else '●')
    if headrest:
        scopes = ('二排',) if '二排' in headrest or '后排' in headrest else _front_scopes(headrest)
        if not any(seat in headrest for seat in SEATS) and '前排' not in headrest:
            scopes = ('主驾', '副驾')
            for seat in scopes:
                out[seat + '头枕音响'] = '[待定]请确认头枕音响座位'
        else:
            for seat in scopes:
                out[seat + '头枕音响'] = '●'
    return out


def normalize(value):
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
