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


def suggest(cols):
    """cols: [{column, kind, desc, examples}] → {column: (한글 이름, 설명)}. 실패하면 있는 캐시만 돌려준다."""
    cache = json.loads(CACHE.read_text('utf-8')) if CACHE.exists() else {}
    todo = [c for c in cols if _key(c) not in cache]
    if todo and not os.environ.get('ANTHROPIC_API_KEY'):
        print('[LLM] 환경변수 ANTHROPIC_API_KEY가 없어 LLM 없이 계속합니다.', file=sys.stderr)
    elif todo:
        import anthropic
        try:
            resp = anthropic.Anthropic().beta.messages.create(
                model=MODEL,
                max_tokens=16000,
                betas=['server-side-fallback-2026-07-01'],
                fallbacks='default',
                output_config={'effort': 'low', 'format': {'type': 'json_schema', 'schema': SCHEMA}},
                system=SYSTEM,
                messages=[{'role': 'user', 'content': json.dumps(todo, ensure_ascii=False)}],
            )
            if resp.stop_reason != 'end_turn':
                raise RuntimeError(f'응답이 끝까지 오지 않음 (stop_reason={resp.stop_reason})')
            merge(cache, todo, next(b.text for b in resp.content if b.type == 'text'))
            CACHE.parent.mkdir(exist_ok=True)
            CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), 'utf-8')
        except anthropic.AuthenticationError:
            print('[LLM] API 키가 없거나 틀림. 환경변수 ANTHROPIC_API_KEY를 설정하세요. LLM 없이 계속합니다.', file=sys.stderr)
        except anthropic.RateLimitError:
            print('[LLM] 요청 한도 초과. 잠시 후 다시 시도하세요. LLM 없이 계속합니다.', file=sys.stderr)
        except anthropic.APIConnectionError:
            print('[LLM] 인터넷 연결 실패. LLM 없이 계속합니다.', file=sys.stderr)
        except (anthropic.AnthropicError, RuntimeError) as e:
            print(f'[LLM] 실패: {e}. LLM 없이 계속합니다.', file=sys.stderr)
    return {c['column']: cache[_key(c)] for c in cols if _key(c) in cache}
