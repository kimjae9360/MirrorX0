"""페이지네이션이 있는 목록형 사이트를 페이지가 넘어가는 대로 계속 따라가며,
같은 표에 행을 계속 이어붙인다 (Listly의 '페이지네이션 템플릿' 기능 참고).

두 가지 '다음 페이지' 방식을 구분해서 처리한다 - 이게 이 모듈의 핵심이다:

    1. 링크형(예: ?page=2) - 누르면 완전히 새로운 문서로 바뀐다.
       매번 반복 패턴을 처음부터 다시 찾고, 찾은 항목 전부를 추출한다.

    2. 클릭형 '더보기' 버튼 - 누르면 같은 페이지 안에 항목이 추가로 붙는다
       (주소는 그대로). 이 경우 페이지 전체를 다시 추출하면 이미 뽑은 항목을
       중복으로 또 뽑게 된다. 그래서 클릭 전/후의 항목 개수를 비교해서,
       '새로 늘어난 만큼'만 추출한다.

이미 있는 부품을 그대로 재사용한다: pattern_detect(반복 항목 찾기),
ai_extract.extract_list_fields(항목들에서 값 뽑기), smart_crawl의 쿠키 주입.
새로 만드는 건 '페이지가 넘어가는 걸 어떻게 감지하고 따라가는가'뿐이다.
"""
import re
import urllib.parse

# '다음 페이지'로 볼 만한 버튼/링크 텍스트 (한국어/영어 관용구)
_NEXT_TEXT_PATTERNS = [
    re.compile(r'^next$', re.I),
    re.compile(r'^다음\s*(페이지)?$'),
    re.compile(r'^더\s*보기$'),
    re.compile(r'^더\s*보기\s*\+?$'),
    re.compile(r'^load\s*more$', re.I),
    re.compile(r'^show\s*more$', re.I),
    re.compile(r'^>$'),
    re.compile(r'^»$'),
    re.compile(r'^›$'),  # ›
]

# 다음 페이지 후보에서 확실히 제외할 것들 (있으면 이전/처음 버튼일 가능성이 높음)
_EXCLUDE_TEXT_PATTERNS = [
    re.compile(r'^(prev|previous|이전|처음)', re.I),
]


def _looks_like_next(text):
    text = (text or '').strip()
    if not text or any(p.match(text) for p in _EXCLUDE_TEXT_PATTERNS):
        return False
    return any(p.match(text) for p in _NEXT_TEXT_PATTERNS)


def find_next_control(page):
    """현재 렌더링된 화면에서 '다음 페이지' 링크/버튼을 찾는다. 없으면 None.

    rel="next"가 있는 링크를 최우선으로 본다(표준적이고 오탐 위험이 없다).
    없으면 텍스트가 'Next'/'다음'/'더보기'/'>' 등인 링크나 버튼을 찾는다."""
    rel_next = page.locator('a[rel="next"]').first
    if rel_next.count() > 0:
        return rel_next

    for selector in ('a', 'button'):
        for el in page.locator(selector).all():
            try:
                text = el.inner_text()
            except Exception:
                continue
            if _looks_like_next(text):
                return el
    return None


def extract_paginated_list(start_url, fields, api_key, log_fn, provider='anthropic', model=None,
                            max_pages=20, use_local_cookies=False, progress_fn=None, should_stop=None):
    """start_url에서 시작해 반복 항목을 뽑고, 다음 페이지를 계속 따라가며
    누적한다. max_pages는 무한 루프를 막는 안전장치다.
    반환: [{field: value, ..., '_page': int}, ...]"""
    import pattern_detect
    import ai_extract
    from playwright.sync_api import sync_playwright

    all_rows = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel='chrome', headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        if use_local_cookies:
            import smart_crawl
            smart_crawl._inject_local_cookies(page, [start_url], log_fn)

        seen_urls = set()
        prev_item_count = 0   # 직전 페이지(같은 문서)에서 이미 처리한 항목 개수
        current_url = start_url
        page_num = 1

        while current_url and page_num <= max_pages:
            if should_stop and should_stop():
                log_fn('[페이지네이션] 사용자가 중지했습니다.')
                break
            if current_url in seen_urls:
                log_fn('[페이지네이션] 이미 방문한 페이지라 순환으로 보고 멈춥니다.')
                break
            seen_urls.add(current_url)

            if page.url != current_url:
                log_fn(f'[페이지네이션] {page_num}페이지로 이동: {current_url}')
                page.goto(current_url, wait_until='networkidle', timeout=30000)
                prev_item_count = 0  # 새 문서라 이전 개수와 무관 - 처음부터 다시 센다

            html = page.content()
            blocks = pattern_detect.detect_repeating_blocks(html)

            if blocks:
                items = blocks[0]['items_html']
                # '더보기' 클릭으로 같은 문서에 항목이 누적된 경우, 이미 처리한
                # 만큼은 빼고 새로 늘어난 것만 추출한다(중복 방지의 핵심).
                new_items = items[prev_item_count:] if len(items) >= prev_item_count else items
                rows = ai_extract.extract_list_fields(
                    new_items, fields, api_key, provider=provider, model=model) if new_items else []
                prev_item_count = len(items)
            else:
                try:
                    rows = [ai_extract.extract_fields(html, fields, api_key, provider=provider, model=model)]
                except Exception as e:
                    log_fn(f'[페이지네이션] {page_num}페이지 추출 실패: {e}')
                    rows = []

            for r in rows:
                r['_page'] = page_num
            all_rows.extend(rows)
            log_fn(f'[페이지네이션] {page_num}페이지에서 {len(rows)}개 행 추출 (누적 {len(all_rows)}개)')
            if progress_fn:
                progress_fn({'page': page_num, 'total_rows': len(all_rows)})

            next_control = find_next_control(page)
            if not next_control:
                log_fn('[페이지네이션] 다음 페이지를 찾지 못해 종료합니다.')
                break

            try:
                href = next_control.get_attribute('href')
            except Exception:
                href = None

            if href and href.strip() not in ('', '#'):
                current_url = urllib.parse.urljoin(page.url, href)
            else:
                # href가 없는 버튼(자바스크립트로 항목을 이어붙이는 '더보기' 등) -
                # 클릭해서 같은 문서 안에 새 항목이 나타나길 기다린다.
                try:
                    next_control.click()
                    page.wait_for_load_state('networkidle', timeout=15000)
                    current_url = page.url
                except Exception as e:
                    log_fn(f'[페이지네이션] 다음 페이지 이동 실패: {e}')
                    break

            page_num += 1

        browser.close()

    return all_rows
