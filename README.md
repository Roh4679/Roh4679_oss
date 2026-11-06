# 데이터 이해 도우미

처음 받은 CSV 파일을 올리면 **"이 컬럼이 뭐지?"** 를 한글로 풀어 주는 도구입니다.
데이터나 코딩을 전공하지 않은 사람도 쓸 수 있게 만들었습니다. 특정 분야가 아니라 어떤 CSV에도 쓸 수 있습니다.

## 할 수 있는 것 (v0.1)

- **데이터 요약**: 줄 수, 열 수, 빈칸이 많은 열
- **한글 컬럼 사전**: 컬럼마다 아래 내용을 표로 보여 줍니다
  - 원래 이름, 한글 이름 (예: `customer_prev3_order_qty` → 고객 최근 3 주문 수량)
  - 설명 (값을 보고 판단: 0/1 값, 날짜 범위, 숫자 범위, 범주 등)
  - 역할: 식별 / 시간 / 분류 / 수치
  - 빈칸 비율, 샘플 값, 확실/추측 (확실하지 않은 이름·역할은 추측으로 표시)
- **모르는 단어 채우기**: 사전에 없는 단어의 뜻을 직접 넣거나, 데이터 주제를 적고 AI가 먼저 채우게 할 수 있습니다
- **SQLite 저장**: 분석 결과를 기록으로 쌓고(같은 파일도 새 기록으로), 저장 기록 화면에서 다시 볼 수 있습니다
- 큰 파일도 무작위로 5만 줄만 뽑아 빠르게 분석합니다

## 설치

Python 3.10 이상이 필요합니다.

```
pip install -r requirements.txt
```

## 실행

### 웹 화면

```
python -m streamlit run app.py --server.address localhost
```

브라우저에서 http://localhost:8501 이 열립니다. 왼쪽에서 CSV를 올리고 메뉴를 고르세요.
(`--server.address localhost`는 내 컴퓨터에서만 접속되게 하는 설정입니다.)

### 명령창

```
python main.py 데이터.csv                     # 요약 + 한글 컬럼 사전 출력
python main.py 데이터.csv --save              # 결과를 data.db(SQLite)에 저장
python main.py 데이터.csv --terms 용어.csv    # 분야 용어 파일 추가 (예: terms/baseball.csv)
python main.py --check                        # 자체 점검 (화면 없이 기능 확인, 'ok'가 나오면 정상)
```

분야 용어 파일은 한 줄에 `약어,한글 뜻` 형식입니다. 뜻이 여러 개면 `|`로 나눕니다 (예: `li,레버리지 지수|목록`).

### AI 기능 (선택)

사전으로 풀리지 않는 컬럼을 Claude AI에게 물어볼 수 있습니다. 쓰지 않아도 나머지 기능은 모두 동작합니다.

- 환경변수 `ANTHROPIC_API_KEY`에 API 키를 넣어야 합니다. 키는 코드나 저장소에 넣지 마세요.
- 보내는 내용: 컬럼 이름, 값 요약, 샘플 값 3개 (명령창에서 `--no-samples`를 주면 샘플 값은 보내지 않음)
- 같은 질문은 `.cache/`에 저장해 다시 보내지 않습니다 (비용 절약)

```
python main.py 데이터.csv --llm
```

웹에서는 왼쪽의 "모르는 컬럼은 Claude AI에게 물어보기"를 켜거나, "AI로 1차 채우기"를 누릅니다.

## 파일 구성

| 파일 | 하는 일 |
|---|---|
| `app.py` | 웹 화면 (Streamlit) |
| `main.py` | 명령창 실행, 자체 점검 |
| `analyze.py` | 분석 묶음: 컬럼 통계 + 역할 + 한글 사전 표 |
| `summary.py` | 파일 읽기(샘플링), 값 통계와 설명 |
| `dictionary.py` | 컬럼 이름 → 한글 이름 |
| `db.py` | SQLite 저장 (datasets, columns, terms 표) |
| `llm.py` | Claude AI 연결 (선택) |
| `terms/` | 분야 용어 파일 예시 |

## 데이터 보호

`data/`(테스트 데이터), `data.db`(분석 기록), `.cache/`(AI 응답)에는 올린 데이터의 값이 들어 있어 저장소에 올리지 않습니다 (`.gitignore`).

## References

다른 프로젝트의 코드를 복사해 넣지는 않았고, 아래 라이브러리와 자료를 사용·참고했습니다.

- [Streamlit](https://github.com/streamlit/streamlit) — 웹 화면 (Apache License 2.0)
- [pandas](https://github.com/pandas-dev/pandas) — 웹 화면의 표·그래프용 데이터 (BSD 3-Clause, Streamlit과 함께 설치됨)
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) — Claude AI 연결 (MIT License), [Claude API 문서](https://docs.claude.com)
- [SQLite](https://www.sqlite.org) — 저장소 (Public Domain), Python 기본 모듈 [`sqlite3`](https://docs.python.org/3/library/sqlite3.html)로 사용
- Python 표준 라이브러리 [`csv`](https://docs.python.org/3/library/csv.html), [`random`](https://docs.python.org/3/library/random.html), [`datetime`](https://docs.python.org/3/library/datetime.html)
- 저수지 샘플링(큰 파일에서 무작위 줄 뽑기): Jeffrey S. Vitter, "Random Sampling with a Reservoir", *ACM Transactions on Mathematical Software*, 11(1), 1985. ([위키백과 설명](https://en.wikipedia.org/wiki/Reservoir_sampling))

## 라이선스

[MIT License](LICENSE)
