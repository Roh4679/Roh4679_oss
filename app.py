"""웹 화면. 실행: python -m streamlit run app.py --server.address localhost
화면 코드만 여기 두고, 분석은 analyze.py, 저장은 db.py 를 가져다 쓴다."""
import os
import re
import tempfile

import pandas as pd
import streamlit as st

import db
from analyze import apply_ai, dictionary_rows, profile
from dictionary import TERMS


@st.cache_data
def analyze(data, k=50000):
    """업로드한 파일(바이트) → (전체 줄 수, 샘플 표, 컬럼별 통계+역할). 같은 파일은 다시 계산하지 않는다."""
    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
        f.write(data)
    try:
        header, rows, total, infos = profile(f.name, k)
    finally:
        os.remove(f.name)
    return total, pd.DataFrame(rows, columns=header), infos


st.set_page_config(page_title='데이터 이해 도우미', layout='wide')
con = st.cache_resource(db.connect)()
BASE_TERMS = st.cache_resource(lambda: dict(TERMS))()  # 기본 사전 원본 (사용자 단어를 지웠을 때 되돌리려고)

with st.sidebar:
    st.title('데이터 이해 도우미')
    files = st.file_uploader('CSV 파일 올리기 (여러 개 가능)', type='csv', accept_multiple_files=True)
    menu = st.radio('메뉴', ['컬럼 이해하기', '저장 기록', '관계 파악하기 (준비 중)'])
    use_llm = st.checkbox('모르는 컬럼은 Claude AI에게 물어보기', value=False,
                          help='환경변수 ANTHROPIC_API_KEY가 필요해요. 컬럼 이름과 샘플 값 3개가 전송돼요.')

if menu == '저장 기록':
    st.header('저장 기록 (SQLite)')
    saved = db.list_datasets(con)
    if not saved:
        st.info("아직 저장한 기록이 없어요. '컬럼 이해하기'에서 DB에 저장을 눌러 보세요.")
        st.stop()
    st.dataframe(pd.DataFrame(saved).rename(columns={
        'id': '번호', 'file_name': '파일 이름', 'uploaded_at': '저장 시각',
        'row_count': '줄 수', 'col_count': '열 수', 'sample_count': '샘플 줄 수'}), hide_index=True)
    pick = st.selectbox('자세히 볼 기록', saved, format_func=lambda d: f"{d['id']}번 · {d['file_name']} · {d['uploaded_at']}")
    st.dataframe(pd.DataFrame(db.get_columns(con, pick['id'])).drop(columns=['id', 'dataset_id']),
                 hide_index=True, width='stretch')
    if st.button(f"{pick['id']}번 기록 지우기"):
        db.delete_dataset(con, pick['id'])
        st.rerun()
    st.stop()

if not files:
    st.info('왼쪽에서 CSV 파일을 올려 주세요.')
    st.stop()

if menu != '컬럼 이해하기':
    st.info('표와 표 사이, 컬럼과 컬럼 사이 관계를 보여 주는 화면은 다음 단계에서 만들어요.')
    st.stop()

file = files[0] if len(files) == 1 else st.selectbox('볼 파일', files, format_func=lambda f: f.name)
with st.spinner('분석 중...'):
    total, sample, infos = analyze(file.getvalue())

# 사용자가 넣은 단어 뜻 — DB(terms 표)에 저장돼서 새로고침해도 남는다
if 'my_terms' not in st.session_state:
    st.session_state.my_terms = db.load_terms(con)
my_terms = st.session_state.my_terms
# ponytail: 공용 사전(TERMS)을 직접 바꿈 — 혼자 쓰는 로컬 도구라 괜찮음. 여러 명이 쓰면 사용자별 사전으로 분리.
TERMS.clear()
TERMS.update(BASE_TERMS, **my_terms)
table = dictionary_rows(sample.columns, infos)

if use_llm:
    if not os.environ.get('ANTHROPIC_API_KEY'):
        st.warning('ANTHROPIC_API_KEY가 없어 AI 없이 보여 줘요.')
    else:
        apply_ai(table)

h1, h2 = st.columns([4, 1], vertical_alignment='bottom')
h1.header(file.name)
if h2.button('DB에 저장', width='stretch', help='지금 보이는 분석 결과를 기록으로 남겨요. 같은 파일도 저장할 때마다 새 기록으로 쌓여요.'):
    st.toast(f'{db.save_dataset(con, file.name, total, len(sample), table)}번 기록으로 저장했어요.')
a, b, c = st.columns(3)
a.metric('줄 수', f'{total:,}')
b.metric('열 수', len(table))
c.metric('빈칸 30% 이상인 열', sum(r['빈칸 비율(%)'] >= 30 for r in table))
if len(sample) < total:
    st.caption(f'통계는 무작위로 뽑은 {len(sample):,}줄 기준이에요.')

st.subheader('한글 컬럼 사전')
st.dataframe(pd.DataFrame(table), hide_index=True, width='stretch')

unknown = list(dict.fromkeys(w for r in table for w in re.findall(r"'([^']+)' 모름", r['참고'])))
drafts = st.session_state.setdefault('drafts', {})  # AI가 채운 초안 (확인 전)


@st.dialog('단어 뜻 채우기', width='large')
def fill_words():
    st.caption("뜻을 아는 단어만 적고 확인을 누르세요. 뜻이 여러 개면 '|'로 나눠요 (예: 목록|레버리지 지수).")
    with st.form('words'):
        # 아직 모르는 단어 + 이미 넣은 단어 (고칠 수 있게)
        answers = {w: st.text_input(w, value=drafts.get(w) or (' | '.join(m) if isinstance(m := my_terms.get(w, ''), tuple) else m))
                   for w in unknown + [w for w in my_terms if w not in unknown]}
        if st.form_submit_button('확인', type='primary'):
            for w, a in answers.items():
                means = tuple(m.strip() for m in a.split('|') if m.strip())
                if means:
                    my_terms[w] = means if len(means) > 1 else means[0]
                else:
                    my_terms.pop(w, None)  # 칸을 비우면 넣은 뜻을 지움
            db.save_terms(con, my_terms)
            drafts.clear()
            st.rerun()


if unknown or my_terms:
    t1, t2 = st.columns([4, 1], vertical_alignment='bottom')
    topic = t1.text_input('데이터 주제를 적으면 AI가 모르는 단어 뜻을 먼저 채워 줘요',
                          placeholder='예: 야구 투구 기록, 쇼핑몰 주문')
    if t2.button('AI로 1차 채우기', disabled=not (topic and unknown), width='stretch',
                 help='주제, 단어가 들어간 컬럼 이름, 샘플 값 3개가 Claude로 전송돼요. ANTHROPIC_API_KEY 필요.'):
        import llm
        words = [{'word': w,
                  'columns': [r['원래 이름'] for r in table if f"'{w}' 모름" in r['참고']],
                  'examples': next(r['샘플 값'] for r in table if f"'{w}' 모름" in r['참고']).split(', ')}
                 for w in unknown]
        with st.spinner('AI가 단어 뜻을 추측하는 중...'):
            guesses, err = llm.suggest_terms(topic, words)
        if err:
            st.warning(f'AI 추천 실패: {err}')
        if guesses:
            drafts.update(guesses)  # 초안만 넣고, 반영은 사용자가 창에서 확인을 눌러야 함
            fill_words()
    if st.button(f'직접 채우기 — 모르는 단어 {len(unknown)}개, 넣은 단어 {len(my_terms)}개'):
        fill_words()

st.subheader('데이터 미리보기 (앞 100줄)')
st.dataframe(sample.head(100), width='stretch')

st.subheader('값 분포')
col = st.selectbox('볼 컬럼', sample.columns,
                   format_func=lambda h: f"{h} ({next(r['한글 이름'] for r in table if r['원래 이름'] == h)})")
st.bar_chart(sample[col].value_counts().head(30))
st.caption('많이 나온 값 30개까지만 보여 줘요.')
