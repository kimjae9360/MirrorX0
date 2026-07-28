"""한 페이지 안에 반복되는 항목(상품 카드, 게시글 목록 등)을 AI 없이 구조로 찾아낸다.

왜 필요한가:
    지금까지 AI 추출은 '페이지 1개 = 행 1개'로만 동작했다. 그런데 목록형
    페이지(카테고리 페이지에 상품 24개가 나열된 경우 등)는 페이지 하나 안에
    여러 '행'이 들어있어서, 그 구조를 못 찾으면 페이지 전체를 뭉뚱그려
    행 하나로 잘못 뽑거나 아예 못 뽑는다.

어떻게 찾는가 (AI를 안 쓰는 이유 - 비용/속도):
    같은 부모 아래 '태그+클래스가 같은 형제 요소'가 여러 개 있으면 그게
    반복 패턴이다 (상품 카드 24개는 보통 <div class="product-card"> 24개가
    <div class="product-list"> 안에 나란히 있는 식). 이건 순수 DOM 구조
    분석만으로 충분히 찾아낼 수 있어서 AI 호출이 필요 없다.

    다만 메뉴 목록(<nav><li>메뉴1</li><li>메뉴2</li>...)도 구조적으로는
    '반복'이라서, 데이터가 아닌 것까지 오탐하지 않도록 두 가지를 본다:
      - 각 항목 안에 자식 태그가 얼마나 다양한가 (상품 카드는 이미지+제목+가격
        처럼 안이 복잡하고, 메뉴 항목은 텍스트 하나뿐인 경우가 많다)
      - 항목당 글자 수가 너무 적지 않은가 (짧은 링크 나열은 대개 메뉴/태그 목록)
      - nav/header/footer/aside 태그 안에 있는 건 애초에 후보에서 뺀다
"""

# 반복 패턴 후보에서 제외할 영역 (메뉴/헤더/푸터 등 - 데이터 목록이 아닌 경우가 대부분)
_NOISE_ANCESTORS = {'nav', 'header', 'footer', 'aside', 'script', 'style'}

# 신뢰도를 낮추는 태그(순수 텍스트 링크 나열은 메뉴일 가능성이 높다)
_MIN_TEXT_LEN = 8


def _signature(tag):
    """형제 요소가 '같은 종류'인지 판단하는 서명. 태그명 + class 속성으로 묶는다."""
    classes = tag.get('class') or []
    return (tag.name, tuple(sorted(classes)))


def _richness(tag):
    """이 요소 하나가 얼마나 '데이터스러운지' 대략적인 점수.
    자식 태그 종류가 다양할수록, 글자 수가 많을수록 데이터 카드에 가깝다."""
    descendant_tags = {d.name for d in tag.find_all(True)}
    text_len = len(tag.get_text(strip=True))
    return len(descendant_tags), text_len


def _has_noise_ancestor(tag):
    for parent in tag.parents:
        if getattr(parent, 'name', None) in _NOISE_ANCESTORS:
            return True
    return False


def detect_repeating_blocks(html, min_repeats=4, max_candidates=3, max_scan_chars=400_000):
    """html 안에서 반복되는 요소 그룹을 찾아 점수 높은 순으로 돌려준다.

    반환: [{'count': int, 'tag': str, 'items_html': [str, ...]}, ...]
    items_html은 실제로 발견된 '모든' 항목의 HTML이다(샘플 몇 개가 아니라 전부) -
    나중에 각 항목의 실제 값을 뽑아내려면 항목마다 다른 실제 내용이 필요하기
    때문이다. 아무 패턴도 못 찾으면 빈 리스트를 돌려준다(호출부는 기존처럼
    '페이지 전체 = 행 1개' 방식으로 그대로 넘어가면 된다)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html[:max_scan_chars], 'lxml')
    for tag in soup(['script', 'style']):
        tag.decompose()

    candidates = []
    for parent in soup.find_all(True):
        if _has_noise_ancestor(parent):
            continue
        groups = {}
        for child in parent.find_all(True, recursive=False):
            groups.setdefault(_signature(child), []).append(child)

        for (tag_name, _classes), items in groups.items():
            if len(items) < min_repeats or tag_name in ('script', 'style', 'br', 'hr'):
                continue
            richness_scores = [_richness(it) for it in items[:10]]  # 앞부분만 재도 충분
            avg_tag_diversity = sum(r[0] for r in richness_scores) / len(richness_scores)
            avg_text_len = sum(r[1] for r in richness_scores) / len(richness_scores)
            if avg_text_len < _MIN_TEXT_LEN:
                continue  # 짧은 텍스트 나열 - 메뉴/태그 목록일 가능성이 높아 제외

            score = len(items) * min(avg_tag_diversity, 6) * min(avg_text_len / 20, 3)
            candidates.append({
                'count': len(items),
                'tag': tag_name,
                'score': score,
                'items_html': [str(it) for it in items],
            })

    candidates.sort(key=lambda c: c['score'], reverse=True)

    # 같은 항목 집합을 부모가 다른 조상 태그에서도 중복으로 잡을 수 있어(예:
    # <ul>의 후보와 그 부모 <div>의 후보가 사실상 같은 그룹), 항목 개수와 태그가
    # 겹치는 것 중 점수가 더 낮은 쪽은 뺀다.
    seen = set()
    result = []
    for c in candidates:
        key = (c['tag'], c['count'])
        if key in seen:
            continue
        seen.add(key)
        result.append(c)
        if len(result) >= max_candidates:
            break
    return result
