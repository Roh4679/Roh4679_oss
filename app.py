"""웹 화면. 실행: python -m streamlit run app.py --server.address localhost
화면 코드만 여기 두고, 분석은 analyze.py, 저장은 db.py 를 가져다 쓴다."""
import os
import re
import tempfile

import pandas as pd
import streamlit as st

import db
import llm
import metrics
from analyze import ROLES, apply_ai, dictionary_rows, profile
from dictionary import TERMS, clean_meaning


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
    menu = st.radio('메뉴', ['컬럼 이해하기', '데이터 지도', '저장 기록', '관계 파악하기 (준비 중)'])
    NO_TOPIC = '(주제 없음)'
    topic = st.selectbox('데이터 주제', [NO_TOPIC] + db.list_topics(con), accept_new_options=True,
                         help='새 주제는 직접 입력하세요 (예: 야구, 쇼핑몰). 직접 넣은 단어 뜻과 고친 역할은 '
                              '주제별로 따로 저장돼서 다른 분야 데이터에 섞이지 않아요.')
    topic = '' if topic in (None, NO_TOPIC) else topic.strip()
    use_llm = st.checkbox('모르는 컬럼은 AI에게 물어보기', value=False,
                          help='Ollama(내 컴퓨터) 또는 Claude API를 써요. 컬럼 이름과 샘플 값 3개를 AI에게 보내요.')

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

if menu.startswith('관계'):
    st.info('표와 표 사이, 컬럼과 컬럼 사이 관계를 보여 주는 화면은 다음 단계에서 만들어요.')
    st.stop()

file = files[0] if len(files) == 1 else st.selectbox('볼 파일', files, format_func=lambda f: f.name)
with st.spinner('분석 중...'):
    total, sample, infos = analyze(file.getvalue())

# 이 주제에서 사용자가 넣은 단어 뜻·고친 역할 (DB에 주제별로 저장, 주제가 없으면 기본 사전만)
my_terms = db.load_terms(con, topic) if topic else {}
my_roles = db.load_roles(con, topic)
# ponytail: 공용 사전(TERMS)을 직접 바꿈 — 혼자 쓰는 로컬 도구라 괜찮음. 여러 명이 동시에 쓰면 사용자별 사전으로 분리.
TERMS.clear()
TERMS.update(BASE_TERMS, **my_terms)
table = dictionary_rows(sample.columns, infos, my_roles)
few_rows = '줄이 30개보다 적어서 역할·설명 판단이 부정확할 수 있어요.' if total < 30 else ''

if use_llm:
    if llm.backend() is None:
        st.info(llm.SETUP_HELP)
    else:
        with st.spinner('AI가 모르는 컬럼을 살펴보는 중... (내 컴퓨터 AI는 몇 분 걸릴 수 있어요)'):
            apply_ai(table)

if menu == '데이터 지도':
    st.header(f'데이터 지도 · {file.name}')
    st.caption('컬럼들로 무엇을 나눠 보고 무엇을 계산할 수 있는지 한눈에 보여 줘요. '
               "역할이 틀렸으면 '컬럼 이해하기' 표에서 고치세요.")
    if few_rows:
        st.warning(few_rows)
    icons = {'id': '🔑', 'time': '🕒', 'dimension': '📂', 'measure': '🔢'}
    for role, label in ROLES.items():
        cols = [r for r in table if metrics.role_of(r) == role]
        names = ' · '.join(f"{r['한글 이름']}(`{r['원래 이름']}`){' ?' if r['역할'].endswith('?') else ''}" for r in cols)
        st.markdown(f"{icons[role]} **{label}** &nbsp; {names or '없음'}")

    st.subheader('📊 지표 초안')
    note = f' (무작위 {len(sample):,}줄 샘플 기준이라 합계는 실제보다 작아요)' if len(sample) < total else ''
    st.caption('역할을 보고 규칙으로 만든 계산식이에요. 값은 SQLite로 계산했어요' + note + '.')
    data_db = metrics.load(sample, table)
    rows = []
    for m in metrics.draft(table):
        value, err = metrics.evaluate(data_db, m['formula'])
        rows.append({'지표': m['name'], '계산식': m['formula'],
                     '값': err or (f'{value:,.4g}' if isinstance(value, float) else f'{value:,}' if value is not None else '빈칸'),
                     '재료 컬럼': ', '.join(m['ingredients']), '확실/추측': '확실' if m['sure'] else '추측'})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
    st.stop()

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
if few_rows:
    st.warning(few_rows)

st.subheader('한글 컬럼 사전')
st.caption('역할 칸(✎)을 눌러 바꾸면 바로 저장돼요. 직접 고친 역할은 같은 주제에서 같은 이름의 컬럼이면 다른 파일에도 적용돼요.')
with st.expander('역할이 뭐예요?'):
    st.markdown('- **식별**: 줄을 구분하는 번호 (더하거나 평균 내면 의미 없음) — 예: 주문번호\n'
                '- **시간**: 언제 일어났는지 — 예: 판매 시각\n'
                '- **분류**: 무엇으로 나눠 볼지 — 예: 상품, 상태\n'
                '- **수치**: 더하거나 평균 낼 수 있는 숫자 — 예: 수량, 단가')
view = pd.DataFrame(table).drop(columns='참고')  # 참고는 모르는 단어 찾기에만 씀
view.insert(view.columns.get_loc('역할') + 1, '역할 판단',
            ['직접 고침' if h in my_roles else '자동 · 추측' if r.endswith('?') else '자동'
             for h, r in zip(view['원래 이름'], view['역할'])])
view['역할'] = view['역할'].str.removesuffix(' ?')
edited = st.data_editor(
    view, hide_index=True, width='stretch', key=f'roles_{topic}_{file.name}',
    disabled=[c for c in view.columns if c != '역할'],
    column_config={'역할': st.column_config.SelectboxColumn('역할 ✎', options=list(ROLES.values()), required=True)})
changed = edited[edited['역할'] != view['역할']]
for name, label in zip(changed['원래 이름'], changed['역할']):
    db.save_role(con, topic, name, metrics.LABEL_TO_ROLE[label])
if len(changed):
    st.rerun()
mine = [h for h in view['원래 이름'] if h in my_roles]
if mine and st.button(f'직접 고친 역할 {len(mine)}개를 자동 판단으로 되돌리기'):
    for name in mine:
        db.save_role(con, topic, name, None)
    st.session_state.pop(f'roles_{topic}_{file.name}', None)  # 편집 기록도 비워야 표가 자동 값으로 다시 그려짐
    st.rerun()

unknown = list(dict.fromkeys(w for r in table for w in re.findall(r"'([^']+)' 모름", r['참고'])))
drafts = st.session_state.setdefault('drafts', {})  # AI가 채운 초안 (확인 전)


def shown(m):
    return ' | '.join(m) if isinstance(m, tuple) else m or ''


@st.dialog('단어 뜻 채우기', width='large')
def fill_words():
    st.caption(f"주제 '{topic}'에만 저장돼요. 짧은 한글 이름으로 적고, 뜻이 여러 개면 쉼표나 '|'로 나눠요 (예: 경기, 게임). "
               '괄호 속 설명이나 " - " 뒤 설명은 저장할 때 잘라내요.')
    with st.form('words'):
        # 아직 모르는 단어 + 이미 넣은 단어 (고칠 수 있게)
        answers = {w: st.text_input(w, value=shown(drafts.get(w) or my_terms.get(w)))
                   for w in unknown + [w for w in my_terms if w not in unknown]}
        if st.form_submit_button('확인', type='primary'):
            for w, a in answers.items():
                if meaning := clean_meaning(a):
                    my_terms[w] = meaning
                else:
                    my_terms.pop(w, None)  # 칸을 비우면 넣은 뜻을 지움
            db.save_terms(con, topic, my_terms)
            drafts.clear()
            st.rerun()


if not topic and unknown:
    st.info(f'모르는 단어가 {len(unknown)}개 있어요. 왼쪽에서 **데이터 주제**를 고르거나 새로 적으면 뜻을 채울 수 있어요.')
elif unknown or my_terms:
    if st.button('AI로 1차 채우기', disabled=not unknown,
                 help=f"주제 '{topic}', 단어가 들어간 컬럼 이름, 샘플 값 3개를 AI에게 보내요 (Ollama면 내 컴퓨터 밖으로 안 나가요)."):
        words = [{'word': w,
                  'columns': [r['원래 이름'] for r in table if f"'{w}' 모름" in r['참고']],
                  'examples': next(r['샘플 값'] for r in table if f"'{w}' 모름" in r['참고']).split(', ')}
                 for w in unknown]
        with st.spinner('AI가 단어 뜻을 추측하는 중...'):
            guesses, err = llm.suggest_terms(topic, words)
        if err == llm.NO_AI:
            st.info(llm.SETUP_HELP)
        elif err:
            st.warning(f'AI 추천 실패: {err}')
        if guesses:
            drafts.update({w: clean_meaning(m) for w, m in guesses.items()})  # 초안만 넣고, 반영은 사용자가 창에서 확인을 눌러야 함
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
