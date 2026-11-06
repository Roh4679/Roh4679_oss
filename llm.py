"""사전으로 안 풀리는 컬럼의 한글 이름·설명 초안을 AI에게 받는다.

AI 고르기: 환경변수 ANTHROPIC_API_KEY가 있으면 Claude, 없으면 내 컴퓨터의 Ollama(OLLAMA_MODEL, 기본 gemma3:4b).
보안: API 키는 환경변수 ANTHROPIC_API_KEY에서만 읽는다. 코드·저장소에 키를 넣지 않는다.
비용: 사용자가 켤 때만 호출하고, '추측' 컬럼만 한 번에 묶어 보내며, 결과는 캐시에 저장해 같은 컬럼은 다시 묻지 않는다.
데이터 보호: 컬럼 이름, 타입, 값 요약, 샘플 3개만 보낸다 (--no-samples면 샘플도 안 보냄).
"""
import hashlib
import json
import os
import sys
from pathlib import Path

MODEL = 'claude-opus-5-5'
CACHE = Path(__file__).parent / '.cache' / 'llm_names.json'

SYSTEM = (
    '너는 처음 보는 데이터를 비전공자에게 설명하는 도우미다. '
    '각 컬럼의 이름, 타입, 값 요약, 샘플을 보고 쉬운 한글 이름(짧게)과 한 문장 설명을 만든다. '
    '확신이 없으면 설명에 다른 가능성도 함께 적는다. '
    'column 칸에는 받은 컬럼 이름(영어)을 그대로 적고, name 칸에 한글 이름을 적는다.'
)

SCHEMA = {
    'type': 'object',
    'properties': {'columns': {'type': 'array', 'items': {
        'type': 'object',
        'properties': {'column': {'type': 'string'}, 'name': {'type': 'string'}, 'desc': {'type': 'string'}},
        'required': ['column', 'name', 'desc'],
        'additionalProperties': False,
    }}},
    'required': ['columns'],
    'additionalProperties': False,
}


def _key(col):
    return hashlib.sha1(json.dumps(col, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def merge(cache, todo, text):
    """Claude 응답(JSON 문자열)을 캐시에 넣는다. 보내지 않은 컬럼 이름이 오면 무시한다."""
    by_col = {c['column']: c for c in todo}
    for r in json.loads(text)['columns']:
        if r['column'] not in by_col and r['name'] in by_col:
            r['column'], r['name'] = r['name'], r['column']  # 작은 모델이 칸을 바꿔 적는 경우
        if r['column'] in by_col:
            cache[_key(by_col[r['column']])] = [r['name'], r['desc']]


TERMS_SYSTEM = (
    '너는 데이터 컬럼 이름에 쓰인 약어·영어 단어의 뜻을 추측하는 도우미다. '
    '사용자가 알려 준 데이터 주제와, 단어가 들어간 컬럼 이름·샘플 값을 보고 단어마다 짧은 한글 뜻을 정한다. '
    "뜻이 여러 개로 갈리면 가능성 높은 순서로 '|'로 나눠 적는다 (예: 목록|레버리지 지수). "
    'word 칸에는 받은 단어를 그대로 적고, meaning 칸에 한글 뜻을 적는다.'
)

TERMS_SCHEMA = {
    'type': 'object',
    'properties': {'terms': {'type': 'array', 'items': {
        'type': 'object',
        'properties': {'word': {'type': 'string'}, 'meaning': {'type': 'string'}},
        'required': ['word', 'meaning'],
        'additionalProperties': False,
    }}},
    'required': ['terms'],
    'additionalProperties': False,
}


OLLAMA_URL = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'gemma3:4b')
NO_AI = 'AI를 쓸 수 없음'

SETUP_HELP = f"""**AI 기능을 쓰려면 둘 중 하나를 준비하세요.** (AI 없이도 다른 기능은 모두 동작해요)

**① Ollama (무료, 내 컴퓨터에서 실행, 데이터가 밖으로 안 나감)**
1. https://ollama.com/download 에서 설치
2. 명령창에서 모델 받기 (약 3GB): `ollama pull {OLLAMA_MODEL}`
3. 이 화면을 새로고침

**② Claude API (유료, 답이 더 정확함)**
1. https://console.anthropic.com 에서 API 키 발급
2. 환경변수 `ANTHROPIC_API_KEY`에 키를 넣고 앱을 다시 실행 (Windows: `setx ANTHROPIC_API_KEY "키"`)
"""


def _ollama_models():
    """켜져 있는 Ollama의 모델 목록. 꺼져 있거나 없으면 None."""
    import urllib.request
    try:
        with urllib.request.urlopen(f'{OLLAMA_URL}/api/tags', timeout=2) as r:
            return [m['name'] for m in json.load(r)['models']]
    except OSError:
        return None


def backend():
    """쓸 AI: 'claude' (키가 있으면) → 'ollama' (켜져 있고 모델이 있으면) → None."""
    if os.environ.get('ANTHROPIC_API_KEY'):
        return 'claude'
    models = _ollama_models()
    if models and any(m == OLLAMA_MODEL or m.split(':')[0] == OLLAMA_MODEL for m in models):
        return 'ollama'
    return None


def _ask_ollama(system, schema, content):
    import urllib.error
    import urllib.request
    body = json.dumps({
        # 작은 모델은 temperature 0에서 같은 말을 반복하다 멈춤 → 약간의 무작위성 + 반복 벌점
        'model': OLLAMA_MODEL, 'stream': False, 'format': schema,
        'options': {'temperature': 0.3, 'repeat_penalty': 1.15, 'num_predict': 4096},
        'messages': [{'role': 'system', 'content': system},
                     {'role': 'user', 'content': json.dumps(content, ensure_ascii=False)}],
    }).encode()
    req = urllib.request.Request(f'{OLLAMA_URL}/api/chat', body, {'Content-Type': 'application/json'})
    try:
        # ponytail: 그래픽카드 없는 PC에서 작은 모델도 몇 분 걸릴 수 있어 넉넉히 기다림
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.load(r)['message']['content'], None
    except urllib.error.HTTPError as e:
        return None, f'Ollama 오류 {e.code}: {e.read().decode(errors="replace")[:200]}'
    except OSError as e:
        return None, f'Ollama 연결 실패 ({e})'


def _ask(system, schema, content):
    """AI에게 한 번 묻는다 → (응답 JSON 문자열, None) 또는 (None, 실패 이유)."""
    which = backend()
    if which is None:
        return None, NO_AI
    if which == 'ollama':
        return _ask_ollama(system, schema, content)
    import anthropic
    try:
        resp = anthropic.Anthropic().beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=['server-side-fallback-2026-07-01'],
            fallbacks='default',
            output_config={'effort': 'low', 'format': {'type': 'json_schema', 'schema': schema}},
            system=system,
            messages=[{'role': 'user', 'content': json.dumps(content, ensure_ascii=False)}],
        )
        if resp.stop_reason != 'end_turn':
            return None, f'응답이 끝까지 오지 않음 (stop_reason={resp.stop_reason})'
        return next(b.text for b in resp.content if b.type == 'text'), None
    except anthropic.AuthenticationError:
        return None, 'API 키가 틀림. 환경변수 ANTHROPIC_API_KEY를 확인하세요'
    except anthropic.RateLimitError:
        return None, '요청 한도 초과. 잠시 후 다시 시도하세요'
    except anthropic.APIConnectionError:
        return None, '인터넷 연결 실패'
    except anthropic.AnthropicError as e:
        return None, str(e)


def _load():
    return json.loads(CACHE.read_text('utf-8')) if CACHE.exists() else {}


def _save(cache):
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), 'utf-8')


def suggest(cols):
    """cols: [{column, kind, desc, examples}] → {column: (한글 이름, 설명)}. 실패하면 있는 캐시만 돌려준다."""
    cache = _load()
    todo = [c for c in cols if _key(c) not in cache]
    # 작은 로컬 모델은 한 번에 많이 물으면 답이 길어지다 깨짐 → 6개씩 나눠 묻기 (하나가 실패해도 나머지는 살림)
    size = 6 if backend() == 'ollama' else len(todo) or 1
    for i in range(0, len(todo), size):
        part = todo[i:i + size]
        text, err = _ask(SYSTEM, SCHEMA, part)
        try:
            if not err:
                merge(cache, part, text)
                _save(cache)
        except (ValueError, KeyError, TypeError):
            err = 'AI 답의 형식이 이상함'
        if err == NO_AI:
            print(f'[LLM] {err}. LLM 없이 계속합니다.', file=sys.stderr)
            break
        if err:
            print(f'[LLM] 컬럼 {i + 1}~{i + len(part)}: {err}. 이 부분은 AI 없이 계속합니다.', file=sys.stderr)
    return {c['column']: cache[_key(c)] for c in cols if _key(c) in cache}


def suggest_terms(topic, words):
    """주제 + 모르는 단어들 [{word, columns, examples}] → ({단어: 뜻}, 실패 이유 또는 None)."""
    cache = _load()
    key = 'terms:' + _key({'topic': topic, 'words': words})
    if key not in cache:
        text, err = _ask(TERMS_SYSTEM, TERMS_SCHEMA, {'topic': topic, 'words': words})
        if err:
            return {}, err
        sent = {w['word'] for w in words}
        try:
            got = {}
            for t in json.loads(text)['terms']:
                w, m = (t['meaning'], t['word']) if t['word'] not in sent and t['meaning'] in sent else (t['word'], t['meaning'])
                if w in sent:
                    got[w] = m
            cache[key] = got
        except (ValueError, KeyError, TypeError):
            return {}, 'AI 답의 형식이 이상함. 다시 눌러 보세요'
        _save(cache)
    return cache[key], None
