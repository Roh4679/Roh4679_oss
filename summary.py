"""데이터 요약 — CSV를 샘플링해서 컬럼마다 통계와 쉬운 설명을 만든다."""
import codecs
import csv
import random
from datetime import datetime


def to_num(v):
    try:
        return float(v)
    except ValueError:
        return None


DATE_FORMATS = ('%Y-%m-%d', '%m/%d/%Y', '%Y/%m/%d', '%Y%m%d', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M')


def to_date(v):
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            pass
    return None


def fmt(x):
    return f'{x:g}' if isinstance(x, float) else str(x)


def describe(values):
    """샘플 값 목록 → 통계와 쉬운 설명."""
    filled = [v for v in values if v.strip()]
    info = {'blank_pct': 100 * (1 - len(filled) / len(values)) if values else 0.0,
            'kind': '글자', 'examples': list(dict.fromkeys(filled))[:3]}
    if not filled:
        info['desc'] = '샘플에서 전부 빈칸'
        return info
    uniq = set(filled)
    # 값 종류가 적고, 같은 값이 평균 두 번 이상 나와야 범주로 본다 (작은 데이터에서 전부 범주가 되는 것 방지)
    few = len(uniq) <= 20 and len(uniq) <= len(filled) / 2
    nums = [to_num(v) for v in filled]
    if all(x is not None for x in nums):
        info['kind'] = '정수' if all(x.is_integer() for x in nums) else '소수'
        lo, hi = min(nums), max(nums)
        if uniq <= {'0', '1'}:
            info['desc'] = '0/1 값 (예/아니오로 보임)'
        elif len(uniq) == len(filled) and len(filled) > 50:
            info['desc'] = '줄마다 값이 달라 식별번호로 보임'
        elif few:
            info['desc'] = f'값 {len(uniq)}종류: ' + ', '.join(sorted(uniq, key=float)) + ' (범주로 보임)'
        elif 0 <= lo and hi <= 1 and info['kind'] == '소수':
            info['desc'] = f'0~1 사이 소수 (비율로 보임), 평균 {sum(nums) / len(nums):.3g}'
        else:
            info['desc'] = f'숫자 {fmt(lo)} ~ {fmt(hi)}, 평균 {sum(nums) / len(nums):.4g}'
        return info
    dates = [to_date(v) for v in filled]
    if all(dates):
        info['kind'] = '날짜'
        info['desc'] = f'날짜 {min(dates):%Y-%m-%d} ~ {max(dates):%Y-%m-%d}'
    elif len(uniq) == len(filled) and len(filled) > 50:
        info['desc'] = '줄마다 값이 달라 식별번호로 보임'
    elif few:
        info['desc'] = f'값 {len(uniq)}종류: ' + ', '.join(sorted(uniq)) + ' (범주로 보임)'
    else:
        info['desc'] = f'글자, 샘플에서 고유값 {len(uniq)}개'
    return info


def read_sample(path, k):
    """전체 줄 수를 세면서 k줄을 무작위로 뽑는다 (저수지 샘플링)."""
    with open(path, 'rb') as f:
        head = f.read(1 << 16)
    try:
        codecs.getincrementaldecoder('utf-8')().decode(head)
        enc = 'utf-8-sig'
    except UnicodeDecodeError:
        enc = 'cp949'  # 한국 공공데이터에 흔한 인코딩
    random.seed(0)
    sample, n = [], 0
    # ponytail: 줄 단위로 읽어서 따옴표 안 줄바꿈이 있는 CSV는 깨짐. 그런 데이터가 나오면 csv.reader로 전체 파싱.
    with open(path, encoding=enc, newline='') as f:
        header = next(csv.reader([f.readline()]))
        for n, line in enumerate(f, 1):
            if n <= k:
                sample.append(line)
            elif (j := random.randrange(n)) < k:
                sample[j] = line
    return header, list(csv.reader(sample)), n
