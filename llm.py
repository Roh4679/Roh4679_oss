"""사전으로 안 풀리는 컬럼의 한글 이름·설명 초안을 Claude에게 받는다.

보안: API 키는 환경변수 ANTHROPIC_API_KEY에서만 읽는다. 코드·저장소에 키를 넣지 않는다.
비용: --llm을 줄 때만 호출하고, '추측' 컬럼만 한 번에 묶어 보내며, 결과는 캐시에 저장해 같은 컬럼은 다시 묻지 않는다.
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
    '확신이 없으면 설명에 다른 가능성도 함께 적는다.'
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
        if r['column'] in by_col:
            cache[_key(by_col[r['column']])] = [r['name'], r['desc']]


TERMS_SYSTEM = (
    '너는 데이터 컬럼 이름에 쓰인 약어·영어 단어의 뜻을 추측하는 도우미다. '
    '사용자가 알려 준 데이터 주제와, 단어가 들어간 컬럼 이름·샘플 값을 보고 단어마다 짧은 한글 뜻을 정한다. '
    "뜻이 여러 개로 갈리면 가능성 높은 순서로 '|'로 나눠 적는다 (예: 목록|레버리지 지수)."
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


def _ask(system, schema, content):
    """Claude에게 한 번 묻는다 → (응답 JSON 문자열, None) 또는 (None, 실패 이유)."""
    if not os.environ.get('ANTHROPIC_API_KEY'):
        return None, '환경변수 ANTHROPIC_API_KEY가 없음'
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
    if todo:
        text, err = _ask(SYSTEM, SCHEMA, todo)
        if err:
            print(f'[LLM] {err}. LLM 없이 계속합니다.', file=sys.stderr)
        else:
            merge(cache, todo, text)
            _save(cache)
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
        cache[key] = {t['word']: t['meaning'] for t in json.loads(text)['terms'] if t['word'] in sent}
        _save(cache)
    return cache[key], None
