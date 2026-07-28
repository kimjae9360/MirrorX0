"""AI 추출 결과(행/열로 된 표)를 자연어로 다듬는다.

사용 예: "B열은 빼고 C열을 B열에 넣어줘", "가격 결측치는 최빈값으로 채워줘",
"이름이 빈 행은 지워줘".

핵심 설계 - AI가 데이터를 직접 고치지 않고, '안전한 연산 목록' 중에서 고르게 한다:
    표 전체를 AI에게 주고 "고쳐서 돌려줘"라고 하면, 데이터가 조금만 많아져도
    토큰이 커지고, 평균/최빈값 같은 계산을 AI가 암산하다 틀릴 수 있다.
    그래서 AI에게는 '컬럼 이름 + 샘플 몇 행'만 보여주고, 아래 정해진 연산
    (drop_column/rename_column/move_column/fillna/dedupe/filter_rows/sort_rows)
    중에서 어떤 걸 어떤 순서로 쓸지만 고르게 한다. 실제 계산(최빈값 등)은 이
    파일의 파이썬 코드가 정확하게 수행한다.

    ai_scope.py가 "링크 하나하나 판단" 대신 "필터 규칙을 생성"하게 해서 비용을
    사이트 크기와 무관하게 고정시킨 것과 같은 이유다 - 여기서도 AI가 자유
    코드를 생성해 실행하는 대신 정해진 안전한 연산만 조합하게 하면, 이상한
    코드가 실행될 위험도 없고 결과도 항상 예측 가능하다.
"""
import statistics

_OPERATIONS = ('drop_column', 'rename_column', 'move_column', 'fillna',
              'dedupe', 'filter_rows', 'sort_rows')
_FILL_STRATEGIES = ('mode', 'mean', 'median', 'zero', 'empty')
_FILTER_OPS = ('equals', 'not_equals', 'contains', 'gt', 'lt', 'gte', 'lte', 'not_empty', 'is_empty')


def _operation_schema():
    """세 프로바이더 모두 받아들이는 JSON Schema 서브셋. 연산마다 쓰는 필드가
    달라도 스키마 하나에 전부 선택 필드로 넣어두고(required는 'op'만), 실제
    실행할 때 연산 종류에 맞는 필드만 골라 쓴다."""
    return {
        'type': 'object',
        'properties': {
            'op': {'type': 'string', 'enum': list(_OPERATIONS)},
            'column': {'type': 'string', 'description': '이 연산이 적용될 열 이름'},
            'source_column': {'type': 'string', 'description': "move_column에서 값을 가져올 열"},
            'new_name': {'type': 'string', 'description': 'rename_column의 새 이름'},
            'strategy': {'type': 'string', 'enum': list(_FILL_STRATEGIES)},
            'filter_op': {'type': 'string', 'enum': list(_FILTER_OPS)},
            'value': {'type': 'string', 'description': 'filter_rows에서 비교할 값'},
            'descending': {'type': 'boolean'},
            'columns': {'type': 'array', 'items': {'type': 'string'},
                        'description': 'dedupe에서 비교할 열들(비우면 전체 열)'},
        },
        'required': ['op'],
    }


def _plan_schema():
    return {
        'type': 'object',
        'properties': {
            'operations': {'type': 'array', 'items': _operation_schema()},
            'explanation': {'type': 'string', 'description': '무엇을 왜 했는지 한 문장 요약(한국어)'},
        },
        'required': ['operations', 'explanation'],
    }


_PLAN_DESCRIPTION = (
    '사용자의 자연어 요청을 아래 정해진 연산 목록의 조합으로 바꾼다. '
    '목록에 없는 일(예: 값을 새로 계산해서 채우기, 외부 정보 검색)은 할 수 없으니 '
    '가장 가까운 연산으로 대신하거나, 정말 불가능하면 operations를 빈 배열로 둔다.'
)


def _sample_rows(records, n=5):
    return records[:n]


def _plan_prompt(instruction, columns, sample):
    import json
    return (
        f'다음은 표의 컬럼 이름과 샘플 데이터 몇 행이다.\n'
        f'컬럼: {columns}\n'
        f'샘플: {json.dumps(sample, ensure_ascii=False)}\n\n'
        f'사용자 요청: {instruction}\n\n'
        f'이 요청을 수행할 연산들을 순서대로 제안해줘. '
        f'가능한 연산: {", ".join(_OPERATIONS)} '
        f'(fillna의 strategy는 {", ".join(_FILL_STRATEGIES)} 중 하나, '
        f'filter_rows의 filter_op는 {", ".join(_FILTER_OPS)} 중 하나).'
    )


def propose_refine_plan(instruction, records, api_key, provider='anthropic', model=None):
    """자연어 지시문을 안전한 연산 목록으로 바꿔 제안받는다.
    반환: {'operations': [...], 'explanation': str}"""
    import ai_extract  # 프로바이더별 tool-call 헬퍼를 그대로 재사용
    if provider not in ai_extract.PROVIDERS:
        raise ValueError(f'알 수 없는 AI 프로바이더입니다: {provider!r}')
    if not records:
        return {'operations': [], 'explanation': '표에 데이터가 없어요.'}

    model = model or ai_extract.DEFAULT_MODELS[provider]
    columns = list(records[0].keys())
    prompt = _plan_prompt(instruction, columns, _sample_rows(records))
    schema = _plan_schema()

    if provider == 'anthropic':
        result = ai_extract._anthropic_tool_call(api_key, model, 'refine_plan', _PLAN_DESCRIPTION, schema, prompt)
    elif provider == 'openai':
        result = ai_extract._openai_tool_call(api_key, model, 'refine_plan', _PLAN_DESCRIPTION, schema, prompt)
    else:
        result = ai_extract._gemini_json_call(api_key, model, schema, prompt)

    if result is None:
        raise RuntimeError('AI로부터 제안을 받지 못했습니다.')
    result.setdefault('operations', [])
    result.setdefault('explanation', '')
    return result


# ---------------- 연산 실행 (여기는 AI 없이 파이썬이 직접, 정확하게 계산) ----------------

def _numeric_values(values):
    """빈 값을 뺀 나머지가 전부 숫자로 바뀌면 숫자 리스트를, 아니면 None을 돌려준다."""
    out = []
    for v in values:
        if v in (None, ''):
            continue
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            return None
    return out


def _fill_value(records, column, strategy):
    values = [r.get(column) for r in records]
    non_empty = [v for v in values if v not in (None, '')]
    if not non_empty:
        return '' if strategy != 'zero' else 0

    if strategy == 'zero':
        return 0
    if strategy == 'empty':
        return ''
    if strategy == 'mode':
        try:
            return statistics.mode(non_empty)
        except statistics.StatisticsError:
            return non_empty[0]  # 최빈값이 여럿이면(동점) 첫 값으로

    nums = _numeric_values(non_empty)
    if nums is None:
        # 평균/중앙값을 요청했는데 숫자가 아니면 최빈값으로 안전하게 대신한다
        try:
            return statistics.mode(non_empty)
        except statistics.StatisticsError:
            return non_empty[0]
    return statistics.mean(nums) if strategy == 'mean' else statistics.median(nums)


def _matches_filter(value, filter_op, target):
    text = '' if value is None else str(value)
    if filter_op == 'is_empty':
        return text.strip() == ''
    if filter_op == 'not_empty':
        return text.strip() != ''
    if filter_op == 'contains':
        return str(target) in text
    if filter_op in ('equals', 'not_equals'):
        eq = text == str(target)
        return eq if filter_op == 'equals' else not eq
    try:
        num_val, num_target = float(text), float(target)
    except (TypeError, ValueError):
        return False
    return {'gt': num_val > num_target, 'lt': num_val < num_target,
            'gte': num_val >= num_target, 'lte': num_val <= num_target}[filter_op]


def apply_refine_plan(records, operations):
    """연산들을 순서대로 적용한다. 알 수 없는 연산이나 없는 열을 가리키면
    조용히 건너뛰되(전체가 죽지 않게) warnings에 이유를 남긴다.
    반환: (새 records, warnings 목록)"""
    rows = [dict(r) for r in records]
    warnings = []

    for op in operations or []:
        kind = op.get('op')
        column = op.get('column')
        try:
            if kind == 'drop_column':
                for r in rows:
                    r.pop(column, None)

            elif kind == 'rename_column':
                new_name = op.get('new_name')
                if not new_name:
                    warnings.append(f"rename_column: 새 이름이 없어 건너뜀 ({column})")
                    continue
                for r in rows:
                    if column in r:
                        r[new_name] = r.pop(column)

            elif kind == 'move_column':
                source = op.get('source_column')
                for r in rows:
                    r[column] = r.get(source, '')
                    r.pop(source, None)

            elif kind == 'fillna':
                strategy = op.get('strategy', 'empty')
                fill = _fill_value(rows, column, strategy)
                for r in rows:
                    if r.get(column) in (None, ''):
                        r[column] = fill

            elif kind == 'dedupe':
                subset = op.get('columns') or None
                seen, deduped = set(), []
                for r in rows:
                    key = tuple(r.get(c) for c in subset) if subset else tuple(sorted(r.items()))
                    if key not in seen:
                        seen.add(key)
                        deduped.append(r)
                rows = deduped

            elif kind == 'filter_rows':
                filter_op = op.get('filter_op', 'not_empty')
                value = op.get('value', '')
                rows = [r for r in rows if _matches_filter(r.get(column), filter_op, value)]

            elif kind == 'sort_rows':
                descending = bool(op.get('descending', False))

                def _key(r, c=column):
                    v = r.get(c)
                    try:
                        return (0, float(v))
                    except (TypeError, ValueError):
                        return (1, str(v or ''))
                rows.sort(key=_key, reverse=descending)

            else:
                warnings.append(f'알 수 없는 연산이라 건너뜀: {kind}')
        except Exception as e:
            warnings.append(f'{kind} 처리 중 오류로 건너뜀 ({column}): {e}')

    return rows, warnings


def summarize_change(before, after):
    """적용 전/후를 한눈에 보여줄 요약 - 사용자가 코드를 안 봐도 뭐가 바뀌는지 알 수 있게."""
    before_cols = list(before[0].keys()) if before else []
    after_cols = list(after[0].keys()) if after else []
    return {
        'rows_before': len(before), 'rows_after': len(after),
        'columns_before': before_cols, 'columns_after': after_cols,
        'columns_added': [c for c in after_cols if c not in before_cols],
        'columns_removed': [c for c in before_cols if c not in after_cols],
    }
