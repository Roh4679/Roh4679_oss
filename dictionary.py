"""기능 1: 한글 컬럼 사전 — 컬럼명을 한글 이름으로 바꾼다."""
import csv
import re

# 분야와 상관없이 데이터에 흔한 영어 약어 → 한글. 튜플이면 뜻이 여러 개라 '추측'으로 표시한다.
# 분야 용어(야구, 의료 등)는 여기 넣지 않고 --terms 파일로 받는다.
TERMS = {
    'id': '식별번호', 'no': '번호', 'num': '개수', 'n': '개수', 'cnt': '개수', 'count': '개수',
    'seq': '순번', 'idx': '순번', 'index': '순번', 'row': '행', 'key': '키', 'code': '코드', 'cd': '코드',
    'name': '이름', 'nm': '이름', 'type': '종류', 'kind': '종류', 'group': '그룹', 'cat': '분류',
    'category': '분류', 'level': '수준', 'grade': ('등급', '학년'), 'desc': ('설명', '내림차순'),
    'value': '값', 'val': '값', 'is': '여부', 'has': '여부', 'flag': '여부', 'yn': '여부',
    'state': '상태', 'status': '상태', 'st': ('상태', '시작(start)'),
    'date': '날짜', 'dt': '날짜', 'time': '시각', 'ts': '시각', 'at': '시각', 'year': '연도',
    'month': '월', 'week': '주', 'day': '일', 'dayofweek': '요일', 'weekday': '요일', 'hour': '시',
    'season': ('시즌', '계절'), 'start': '시작', 'end': '종료', 'created': '생성', 'updated': '수정',
    'before': '이전', 'after': '이후', 'prev': '이전', 'next': '다음', 'last': '마지막', 'first': '처음',
    'asof': '그 시점까지',
    'amt': '금액', 'amount': '금액', 'price': '단가', 'cost': '비용', 'qty': '수량', 'quantity': '수량',
    'sales': '매출', 'revenue': '매출', 'total': '합계', 'sum': '합계', 'avg': '평균', 'mean': '평균',
    'max': '최대', 'min': '최소', 'std': '표준편차', 'rate': '비율', 'ratio': '비율', 'pct': '퍼센트',
    'diff': '차이', 'score': '점수', 'success': '성공', 'fail': '실패', 'run': ('득점', '실행'),
    'user': '사용자', 'customer': '고객', 'cust': '고객', 'member': '회원', 'team': '팀',
    'order': '주문', 'item': '상품', 'product': '상품', 'prod': ('상품', '운영 환경'), 'sold': '판매',
    'purchase': '구매', 'age': '나이', 'gender': '성별', 'sex': '성별', 'region': '지역', 'city': '도시',
    'addr': '주소', 'address': '주소', 'phone': '전화번호', 'tel': '전화번호', 'email': '이메일',
    'lat': '위도', 'lon': '경도', 'lng': '경도', 'temp': ('온도', '임시'), 'speed': '속도',
    'height': '높이', 'width': '너비', 'weight': '무게', 'auto': '자동', 'on': '위', 'of': '의',
}


def load_terms(path):
    """분야 용어 파일(약어,한글)을 읽어 기본 사전 위에 덮어쓴다."""
    with open(path, encoding='utf-8-sig', newline='') as f:
        for row in csv.reader(f):
            if len(row) >= 2 and not row[0].startswith('#'):
                means = tuple(m.strip() for m in row[1].split('|'))
                TERMS[row[0].strip().lower()] = means if len(means) > 1 else means[0]


def korean_name(col):
    """컬럼명 → (한글 이름, 확실 여부, 메모)."""
    # snake_case, camelCase, 공백, 하이픈을 모두 단어로 나눈다
    tokens = re.sub(r'([a-z])([A-Z])', r'\1_\2', col).lower().replace('-', '_').replace(' ', '_').split('_')
    words, sure, notes = [], True, []
    for t in filter(None, tokens):
        if m := re.fullmatch(r'prev(\d+)', t):
            words.append(f'최근 {m[1]}')
        elif t.isdigit():
            words.append(t)
        elif isinstance(TERMS.get(t), tuple):
            words.append(TERMS[t][0])
            sure = False
            notes.append(f"'{t}'는 {' 또는 '.join(TERMS[t])}일 수 있음")
        elif t in TERMS:
            words.append(TERMS[t])
        else:
            words.append(t)
            sure = False
            notes.append(f"'{t}' 모름")
    return ' '.join(words), sure, notes
