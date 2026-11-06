"""데이터 지도의 지표 — 역할을 보고 계산식 초안을 만들고, SQLite로 샘플에서 값을 계산한다."""
import re
import sqlite3

from analyze import ROLES

LABEL_TO_ROLE = {v: k for k, v in ROLES.items()}
# 더하면 의미 없는 수치 (단가·비율 합계는 이상함) → 평균만
AVG_ONLY = {'price', 'rate', 'ratio', 'pct', 'avg', 'mean', 'score', 'speed', 'height', 'width', 'weight',
            'age', 'temp', 'lat', 'lon', 'lng'}
QTY_WORDS = {'qty', 'quantity', 'cnt', 'count', 'num'}
PRICE_WORDS = {'price', 'cost'}


def _words(col):
    return set(re.sub(r'([a-z])([A-Z])', r'\1_\2', col).lower().replace('-', '_').replace(' ', '_').split('_'))


def q(col):
    """SQL에서 컬럼 이름을 안전하게 감싼다 (공백·한글·예약어가 있어도 되게)."""
    return '"' + col.replace('"', '""') + '"'


def role_of(row):
    return LABEL_TO_ROLE[row['역할'].removesuffix(' ?')]


def draft(table):
    """컬럼 사전 표 → 지표 초안 [{name, formula, ingredients, sure}]. 규칙 기반."""
    out = [{'name': '줄 수', 'formula': 'COUNT(*)', 'ingredients': [], 'sure': True}]
    measures = []
    for r in table:
        col, ko, role, sure = r['원래 이름'], r['한글 이름'], role_of(r), not r['역할'].endswith('?')
        if role == 'id':
            name = re.sub(r'\s*(식별번호|번호|코드|키)$', '', ko) or ko
            out.append({'name': f'{name} 수', 'formula': f'COUNT(DISTINCT {q(col)})', 'ingredients': [col], 'sure': sure})
        elif role == 'measure':
            measures.append(r)
            if not _words(col) & AVG_ONLY:
                out.append({'name': f'{ko} 합계', 'formula': f'SUM({q(col)})', 'ingredients': [col], 'sure': sure})
            out.append({'name': f'{ko} 평균', 'formula': f'AVG({q(col)})', 'ingredients': [col], 'sure': sure})
    qty = [r['원래 이름'] for r in measures if _words(r['원래 이름']) & QTY_WORDS]
    price = [r['원래 이름'] for r in measures if _words(r['원래 이름']) & PRICE_WORDS]
    if qty and price:  # 수량 × 단가 = 금액으로 추측 (가장 먼저 나온 한 쌍만)
        out.append({'name': '매출(수량×단가)', 'formula': f'SUM({q(qty[0])} * {q(price[0])})',
                    'ingredients': [qty[0], price[0]], 'sure': False})
    return out


def load(sample, table):
    """샘플 표(pandas) → 메모리 SQLite. 수치·식별 숫자는 숫자로, 빈칸은 NULL로 넣는다."""
    con = sqlite3.connect(':memory:')
    types = {'정수': 'INTEGER', '소수': 'REAL'}
    cols = ', '.join(f"{q(r['원래 이름'])} {types.get(r['종류'], 'TEXT')}" for r in table)
    con.execute(f'CREATE TABLE data ({cols})')
    con.executemany(f'INSERT INTO data VALUES ({", ".join("?" * len(table))})',
                    ([v if v != '' else None for v in row] for row in sample.itertuples(index=False)))
    return con


def evaluate(con, formula):
    """계산식 하나를 샘플에서 계산 → (값, None) 또는 (None, 쉬운 오류 설명)."""
    # ponytail: 계산식을 SQL에 그대로 넣음 — 메모리 복사본이라 원본은 안전. 남이 쓴 식을 받게 되면 sqlglot으로 검사.
    if ';' in formula:
        return None, "계산식에는 ';'를 쓸 수 없어요"
    try:
        return con.execute(f'SELECT {formula} FROM data').fetchone()[0], None
    except sqlite3.Error as e:
        msg = str(e)
        if 'no such column' in msg:
            return None, f"없는 컬럼이에요: {msg.split(':')[-1].strip()}"
        return None, f'계산식이 이상해요 ({msg})'
