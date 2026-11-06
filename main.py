"""v0.1: CSV를 넣으면 한글 컬럼 사전 + 데이터 요약을 보여 준다.

사용법: python main.py 데이터.csv [--terms 분야용어.csv] [--sample 50000] [--llm [--no-samples]]
자체 점검: python main.py --check

분야 용어 파일: 한 줄에 '약어,한글'. 뜻이 여러 개면 '|'로 나눈다 (예: li,레버리지 지수|목록).
--llm: 사전으로 안 풀린 '추측' 컬럼만 Claude에게 물어본다. 환경변수 ANTHROPIC_API_KEY 필요.
"""
import argparse
import sys

from dictionary import korean_name, load_terms
from summary import describe, read_sample


def main(path, k=50000, use_llm=False, send_samples=True):
    header, rows, total = read_sample(path, k)
    cols = list(zip(*rows)) if rows else [()] * len(header)
    infos = [describe(list(c)) for c in cols]
    names = [korean_name(h) for h in header]

    ai = {}
    if use_llm:
        import llm
        ai = llm.suggest([
            {'column': h, 'kind': i['kind'], 'desc': i['desc'], 'examples': i['examples'] if send_samples else []}
            for h, i, (_, sure, _) in zip(header, infos, names) if not sure
        ])

    print(f'# {path}')
    print(f'줄 {total:,}개, 열 {len(header)}개'
          + (f' (통계는 무작위 {len(rows):,}줄 샘플 기준)' if len(rows) < total else ''))
    kinds = {}
    for i in infos:
        kinds[i['kind']] = kinds.get(i['kind'], 0) + 1
    print('열 종류: ' + ', '.join(f'{k} {v}개' for k, v in kinds.items()))
    blanky = [(h, i['blank_pct']) for h, i in zip(header, infos) if i['blank_pct'] >= 30]
    if blanky:
        print('빈칸 많은 열: ' + ', '.join(f'{h}({p:.0f}%)' for h, p in blanky))
    print()

    for h, i, (name, sure, notes) in zip(header, infos, names):
        if h in ai:
            name, ai_desc = ai[h]
            print(f"{h}  →  {name}  [추측·AI]")
            print(f"    AI 설명: {ai_desc}")
        else:
            print(f"{h}  →  {name}  [{'확실' if sure else '추측'}]")
        print(f"    {i['kind']}, 빈칸 {i['blank_pct']:.1f}%, {i['desc']}")
        if i['examples']:
            print(f"    예: {', '.join(i['examples'])}")
        if notes:
            print(f"    참고: {'; '.join(notes)}")


def check():
    import os, tempfile
    assert korean_name('asof_customer_prev3_order_qty') == ('그 시점까지 고객 최근 3 주문 수량', True, [])
    assert korean_name('soldAt')[:2] == ('판매 시각', True)
    name, sure, notes = korean_name('st')
    assert not sure and '시작(start)' in notes[0]
    assert korean_name('pitcher_id') == ('pitcher 식별번호', False, ["'pitcher' 모름"])
    with tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False, encoding='utf-8') as f:
        f.write('# 주석\npitcher,투수\nli,레버리지 지수|목록\n')
    load_terms(f.name)
    os.remove(f.name)
    assert korean_name('pitcher_id') == ('투수 식별번호', True, [])
    assert korean_name('li')[1] is False
    assert describe(['0', '1', '', '1'])['desc'].startswith('0/1')
    assert describe([str(i / 100) for i in range(1, 60)] * 2)['desc'].startswith('0~1')
    assert describe(['03/29/2019', '04/01/2019'])['desc'] == '날짜 2019-03-29 ~ 2019-04-01'
    assert describe([''])['desc'] == '샘플에서 전부 빈칸'
    assert describe(['300', '500', '1000', '1500'])['desc'].startswith('숫자 300 ~ 1500')
    assert describe(['2026-03-02 08:40', '2026-03-02 12:20'])['kind'] == '날짜'
    import llm
    cache, todo = {}, [{'column': 'st', 'kind': '글자', 'desc': '', 'examples': ['완료']}]
    llm.merge(cache, todo, '{"columns": [{"column": "st", "name": "주문 상태", "desc": "완료/환불"},'
                           ' {"column": "안보낸열", "name": "x", "desc": "x"}]}')
    assert list(cache.values()) == [['주문 상태', '완료/환불']]
    old = os.environ.pop('ANTHROPIC_API_KEY', None)
    assert llm.suggest_terms('테스트', [{'word': 'x', 'columns': ['x'], 'examples': []}])[1]  # 키 없으면 이유를 돌려줌
    if old:
        os.environ['ANTHROPIC_API_KEY'] = old
    print('ok')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    if sys.argv[1:] == ['--check']:
        check()
        sys.exit()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('csv')
    ap.add_argument('--terms', action='append', default=[], help='분야 용어 파일 (여러 번 줄 수 있음)')
    ap.add_argument('--sample', type=int, default=50000)
    ap.add_argument('--llm', action='store_true', help="'추측' 컬럼을 Claude에게 물어봄 (ANTHROPIC_API_KEY 필요)")
    ap.add_argument('--no-samples', action='store_true', help='LLM에 샘플 값을 보내지 않음')
    args = ap.parse_args()
    for t in args.terms:
        load_terms(t)
    main(args.csv, args.sample, args.llm, not args.no_samples)
