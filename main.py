"""v0.1: CSV를 넣으면 한글 컬럼 사전 + 데이터 요약을 보여 준다.

사용법: python main.py 데이터.csv [--terms 분야용어.csv] [--sample 50000] [--llm [--no-samples]]
자체 점검: python main.py --check

분야 용어 파일: 한 줄에 '약어,한글'. 뜻이 여러 개면 '|'로 나눈다 (예: li,레버리지 지수|목록).
--llm: 사전으로 안 풀린 '추측' 컬럼만 Claude에게 물어본다. 환경변수 ANTHROPIC_API_KEY 필요.
"""
import argparse
import sys

from analyze import apply_ai, dictionary_rows, profile
from dictionary import korean_name, load_terms
from summary import describe


def main(path, k=50000, use_llm=False, send_samples=True, save=False):
    header, rows, total, infos = profile(path, k)
    table = dictionary_rows(header, infos)
    if use_llm:
        apply_ai(table, send_samples)

    print(f'# {path}')
    print(f'줄 {total:,}개, 열 {len(header)}개'
          + (f' (통계는 무작위 {len(rows):,}줄 샘플 기준)' if len(rows) < total else ''))
    kinds = {}
    for r in table:
        kinds[r['종류']] = kinds.get(r['종류'], 0) + 1
    print('열 종류: ' + ', '.join(f'{k} {v}개' for k, v in kinds.items()))
    blanky = [r for r in table if r['빈칸 비율(%)'] >= 30]
    if blanky:
        print('빈칸 많은 열: ' + ', '.join(f"{r['원래 이름']}({r['빈칸 비율(%)']:.0f}%)" for r in blanky))
    print()

    for r in table:
        print(f"{r['원래 이름']}  →  {r['한글 이름']}  [{r['확실/추측']}]  {r['역할']}")
        print(f"    {r['종류']}, 빈칸 {r['빈칸 비율(%)']:.1f}%, {r['설명']}")
        if r['샘플 값']:
            print(f"    예: {r['샘플 값']}")
        if r['참고']:
            print(f"    참고: {r['참고']}")

    if save:
        import db
        print(f"\nDB에 저장함 (dataset id {db.save_dataset(db.connect(), path, total, len(rows), table)})")


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
    cache = {}
    llm.merge(cache, todo, '{"columns": [{"column": "주문 상태", "name": "st", "desc": "d"}]}')  # 칸이 바뀐 답
    assert list(cache.values()) == [['주문 상태', 'd']]
    real_backend, llm.backend = llm.backend, lambda: None  # AI가 없는 컴퓨터인 척
    assert llm.suggest_terms('테스트', [{'word': 'x', 'columns': ['x'], 'examples': []}]) == ({}, llm.NO_AI)
    llm.backend = real_backend

    # 1단계: 컬럼 역할 — 정답을 아는 작은 판매 데이터
    from analyze import role
    with tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False, encoding='utf-8') as f:
        f.write('order_id,sold_at,grade,item,st,qty,price,score_rate\n'
                '1,2026-03-02 08:40,1,빵,완료,2,1000,0.5\n2,2026-03-02 08:45,1,우유,완료,1,1500,0.25\n'
                '3,2026-03-02 12:10,2,과자,완료,1,500,0.75\n4,2026-03-02 12:15,2,우유,완료,1,300,0.1\n')
    header, rows, total, infos = profile(f.name)
    os.remove(f.name)
    assert total == 4 and len(rows) == 4
    assert [i['role'] for i in infos] == ['id', 'time', 'dimension', 'dimension', 'dimension', 'measure', 'measure', 'measure']
    assert role('zip', describe([str(10000 + i) for i in range(30)] * 2)) == ('measure', False)  # 정수는 코드일 수 있어 추측
    assert role('is_vip', describe(['0', '1', '1', '0']))[0] == 'dimension'

    # 2단계: SQLite — 메모리 DB로 저장·조회·쌓기·삭제
    import db
    con = db.connect(':memory:')
    table = dictionary_rows(header, infos)
    a = db.save_dataset(con, 'sales.csv', total, len(rows), table)
    b = db.save_dataset(con, 'sales.csv', total, len(rows), table)  # 같은 파일 다시 → 덮어쓰지 않고 쌓임
    assert a != b and len(db.list_datasets(con)) == 2
    cols = db.get_columns(con, a)
    assert [c['name'] for c in cols] == header and cols[0]['role'] == '식별'
    db.delete_dataset(con, a)
    assert db.get_columns(con, a) == [] and len(db.list_datasets(con)) == 1  # 컬럼도 같이 지워짐
    # v0.2: 사용자가 고친 역할이 자동 판단보다 우선, 지우면 자동으로 돌아감
    db.save_role(con, '매점', 'grade', 'measure')
    assert dictionary_rows(header, infos, db.load_roles(con, '매점'))[2]['역할'] == '수치'
    assert dictionary_rows(header, infos, db.load_roles(con, '학교'))[2]['역할'] == '분류 ?'  # 다른 주제엔 안 섞임
    db.save_role(con, '매점', 'grade', None)
    assert dictionary_rows(header, infos, db.load_roles(con, '매점'))[2]['역할'] == '분류 ?'
    # v0.2: 지표 초안 + SQLite 계산 (정답: 매출 2*1000 + 1*1500 + 1*500 + 1*300 = 4300)
    import metrics
    import pandas as pd
    drafts = {m['name']: m for m in metrics.draft(table)}
    assert drafts['매출(수량×단가)']['formula'] == 'SUM("qty" * "price")' and not drafts['매출(수량×단가)']['sure']
    assert '단가 합계' not in drafts and '단가 평균' in drafts  # 단가는 더하면 의미 없음
    mem = metrics.load(pd.DataFrame(rows, columns=header), table)
    assert metrics.evaluate(mem, drafts['매출(수량×단가)']['formula']) == (4300, None)
    assert metrics.evaluate(mem, drafts['주문 수']['formula']) == (4, None)
    assert metrics.evaluate(mem, 'SUM(없는열)')[1].startswith('없는 컬럼')
    assert metrics.evaluate(mem, '1; DROP TABLE data')[1]
    db.save_terms(con, '야구', {'pitcher': '투수', 'li': ('목록', '레버리지 지수')})
    db.save_terms(con, '부동산', {'home': '집'})
    assert db.load_terms(con, '야구') == {'pitcher': '투수', 'li': ('목록', '레버리지 지수')}
    assert db.load_terms(con, '부동산') == {'home': '집'} and db.list_topics(con) == ['부동산', '야구']
    # 뜻 정리: 쉼표 = 뜻 여러 개, 괄호·' - ' 뒤 설명은 잘라냄
    from dictionary import clean_meaning
    assert clean_meaning('상위 (주문) - 공격할 팀') == '상위'
    assert clean_meaning('경기, 게임') == ('경기', '게임') and clean_meaning(' | ') is None
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
    ap.add_argument('--save', action='store_true', help='결과를 SQLite(data.db)에 저장')
    args = ap.parse_args()
    for t in args.terms:
        load_terms(t)
    main(args.csv, args.sample, args.llm, not args.no_samples, args.save)
