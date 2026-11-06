"""분석 묶음 — 파일 하나를 읽어 컬럼마다 통계·역할·한글 이름을 만든다. 명령창(main.py)과 웹(app.py)이 같이 쓴다."""
import re

from dictionary import korean_name
from summary import describe, read_sample

ROLES = {'id': '식별', 'time': '시간', 'dimension': '분류', 'measure': '수치'}
ID_WORDS = {'id', 'no', 'code', 'cd', 'key', 'seq', 'idx', 'uuid'}
TIME_WORDS = {'date', 'dt', 'time', 'ts', 'at', 'year', 'month', 'week', 'day', 'hour', 'yyyymm', 'ym'}
MEASURE_WORDS = {'qty', 'quantity', 'amt', 'amount', 'price', 'cost', 'sales', 'revenue', 'total', 'sum', 'avg',
                 'mean', 'cnt', 'count', 'num', 'rate', 'ratio', 'pct', 'score', 'speed', 'weight', 'height', 'width'}


def role(col, info):
    """컬럼 이름 + 값 통계 → (역할, 확실 여부). 규칙 기반이라 애매하면 '추측'."""
    words = set(re.sub(r'([a-z])([A-Z])', r'\1_\2', col).lower().replace('-', '_').replace(' ', '_').split('_'))
    unique_rows = info['n_filled'] > 50 and info['n_unique'] == info['n_filled']
    few = info['n_unique'] <= 20 and info['n_unique'] <= info['n_filled'] / 2
    if words & ID_WORDS:
        return 'id', True
    if info['kind'] == '날짜':
        return 'time', True
    if words & TIME_WORDS:
        return 'time', False  # 예: year=2024처럼 숫자로 된 시간
    numeric = info['kind'] in ('정수', '소수')
    if numeric and words & MEASURE_WORDS:
        return 'measure', True
    if unique_rows:
        return 'id', False  # 줄마다 값이 다름 (번호일 가능성)
    if info['kind'] == '글자' or info['desc'].startswith('0/1'):
        return 'dimension', bool(info['n_filled'])
    if few:
        return 'dimension', False  # 숫자인데 종류가 적음 (등급 1/2/3 같은 것일 수도, 진짜 수치일 수도)
    return 'measure', info['kind'] == '소수'  # 정수는 우편번호 같은 코드일 수도 있어 추측


def profile(path, k=50000):
    """파일 → (컬럼 이름들, 샘플 줄들, 전체 줄 수, 컬럼별 통계+역할). 무거운 부분이라 웹에서는 캐시한다."""
    header, rows, total = read_sample(path, k)
    cols = list(zip(*rows)) if rows else [()] * len(header)
    infos = []
    for h, c in zip(header, cols):
        info = describe(list(c))
        info['role'], info['role_sure'] = role(h, info)
        infos.append(info)
    return header, rows, total, infos


def dictionary_rows(header, infos, roles=None):
    """한글 컬럼 사전 표의 줄들. 사용자가 넣은 단어 뜻·역할이 바로 반영되도록 캐시 밖에서 부른다.
    roles: 사용자가 직접 고친 {컬럼 이름: 역할} — 자동 판단보다 우선하고 '?'가 붙지 않는다."""
    roles = roles or {}
    table = []
    for h, info in zip(header, infos):
        name, sure, notes = korean_name(h)
        table.append({'원래 이름': h, '한글 이름': name, '확실/추측': '확실' if sure else '추측',
                      '역할': ROLES[roles[h]] if h in roles else ROLES[info['role']] + ('' if info['role_sure'] else ' ?'),
                      '설명': info['desc'], '종류': info['kind'], '빈칸 비율(%)': round(info['blank_pct'], 1),
                      '샘플 값': ', '.join(info['examples']), '참고': '; '.join(notes)})
    return table


def apply_ai(table, send_samples=True):
    """'추측' 컬럼만 Claude에게 물어 한글 이름·설명을 바꾼다. 키가 없거나 실패하면 그대로 둔다."""
    import llm
    ai = llm.suggest([{'column': r['원래 이름'], 'kind': r['종류'], 'desc': r['설명'],
                       'examples': r['샘플 값'].split(', ') if send_samples and r['샘플 값'] else []}
                      for r in table if r['확실/추측'] == '추측'])
    for r in table:
        if r['원래 이름'] in ai:
            r['한글 이름'], ai_desc = ai[r['원래 이름']]
            r['확실/추측'] = '추측·AI'
            r['설명'] = f"{ai_desc} ({r['설명']})"  # 웹 표에는 참고 칸이 없어 AI 설명을 설명 칸에 넣음
            r['참고'] = ''
