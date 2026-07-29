"""HTTrack의 원본 "사이트 링크 주고 전체 페이지 다운로드" 기능을, 링크 하나하나를
AI에게 묻지 않고도 스마트하게 만들기 위한 모듈.

핵심 설계: 시작 페이지 몇 장만 얕게 훑어 링크 구조의 '샘플'을 모으고, 그 샘플 +
사용자의 자연어 목표를 **딱 한 번의 API 호출**로 보내서 "어떤 URL 패턴이면
그 목표를 달성하는지"(HTTrack이 원래 이해하는 +/- 필터 규칙)를 만들어달라고
한다. 링크 개별 판단이 아니라 "규칙 생성" 작업으로 프레이밍했기 때문에, 사이트가
얼마나 크든 API 호출 횟수는 늘 1회(많아야 몇 회)로 고정된다 - 이게 토큰 비용을
사이트 크기와 무관하게 만드는 이유다.

생성된 규칙은 기존 "추가 규칙"(custom_filters_var) 칸에 그대로 들어가므로,
실제 대량 크롤링 자체는 이미 검증된 build_httrack_cmd()/run_httrack() 경로를
그대로 탄다 - 여기서 새로 만드는 건 그 규칙을 자동으로 제안해주는 보조 도구뿐이다.
"""
import urllib.request
import urllib.parse

import ai_extract


def _fetch_html(url, timeout=10):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except Exception:
        return None


def _path_pattern(url):
    """중복 제거용 - 숫자로 된 경로 세그먼트를 뭉뚱그려서 '같은 모양' 링크를 하나로
    취급한다. 예: /book/1234/1 과 /book/5678/2 는 같은 패턴으로 본다."""
    parsed = urllib.parse.urlparse(url)
    segments = ['*' if seg.isdigit() else seg for seg in parsed.path.split('/')]
    return parsed.netloc + '/'.join(segments)


def _collect_links(html, base_url, seen_patterns, sample, max_links):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')
    for a in soup.find_all('a', href=True):
        if len(sample) >= max_links:
            break
        href = urllib.parse.urljoin(base_url, a['href'])
        if not href.startswith(('http://', 'https://')):
            continue
        pattern = _path_pattern(href)
        if pattern in seen_patterns:
            continue
        seen_patterns.add(pattern)
        sample.append({'url': href, 'text': a.get_text(strip=True)[:80]})


def _fetch_link_sample_static(start_urls, max_pages, max_links):
    seen_patterns = set()
    sample = []
    for start_url in start_urls[:max_pages]:
        if len(sample) >= max_links:
            break
        html = _fetch_html(start_url)
        if html:
            _collect_links(html, start_url, seen_patterns, sample, max_links)
    return sample


def _fetch_link_sample_dynamic(start_urls, max_pages, max_links):
    """정적 fetch로 링크가 거의 안 나오는 JS 렌더링 사이트를 위한 폴백.
    smart_crawl.py와 동일한 Playwright channel='chrome' 방식을 그대로 쓴다."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []
        
    seen_patterns = set()
    sample = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel='chrome', headless=True)
        except Exception:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception:
                return []
                
        page = browser.new_page()
        for start_url in start_urls[:max_pages]:
            if len(sample) >= max_links:
                break
            try:
                page.goto(start_url, wait_until='networkidle', timeout=15000)
            except Exception:
                continue
            links = page.eval_on_selector_all(
                'a[href]', 'els => els.map(e => ({href: e.href, text: e.textContent}))')
            for link in links:
                if len(sample) >= max_links:
                    break
                href = link.get('href') or ''
                if not href.startswith(('http://', 'https://')):
                    continue
                pattern = _path_pattern(href)
                if pattern in seen_patterns:
                    continue
                seen_patterns.add(pattern)
                sample.append({'url': href, 'text': (link.get('text') or '').strip()[:80]})
        browser.close()
    return sample


def fetch_link_sample(start_urls, max_pages=3, max_links=200, min_links_before_fallback=5):
    """시작 URL들을 얕게(depth 1) 방문해 링크 샘플(URL + 앵커 텍스트)을 모은다.
    사이트 전체를 미리 받지 않으므로 사이트 크기와 무관하게 빠르다."""
    sample = _fetch_link_sample_static(start_urls, max_pages, max_links)
    if len(sample) < min_links_before_fallback:
        try:
            dynamic_sample = _fetch_link_sample_dynamic(start_urls, max_pages, max_links)
            if len(dynamic_sample) > len(sample):
                sample = dynamic_sample
        except Exception:
            pass
    return sample


def _scope_rules_schema():
    return {
        'type': 'object',
        'properties': {
            'rules': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': 'HTTrack 필터 규칙 목록, 한 줄에 하나. 예: "+*/recipe/*", "-*/cart/*"',
            },
            'explanation': {'type': 'string', 'description': '왜 이 규칙들을 골랐는지 한국어로 간단히 설명'},
        },
        'required': ['rules', 'explanation'],
    }


def propose_scope_rules(goal, link_sample, start_url, api_key, provider='anthropic', model=None):
    """링크 샘플 + 사용자의 자연어 목표를 API 호출 1회로 보내 HTTrack 필터 규칙을 제안받는다.
    돌려주는 값: {'rules': ['+*/recipe/*', ...], 'explanation': '...'}"""
    if provider not in ai_extract.PROVIDERS:
        raise ValueError(f'알 수 없는 AI 프로바이더입니다: {provider!r}')
    if not link_sample:
        raise ValueError('링크 샘플이 없습니다. 먼저 대상 사이트에서 링크를 가져와야 합니다.')

    model = model or ai_extract.DEFAULT_MODELS[provider]
    schema = _scope_rules_schema()
    sample_lines = '\n'.join(f'- {item["url"]}  (텍스트: {item["text"]})' for item in link_sample)
    prompt = (
        f'다음은 {start_url}에서 찾은 링크 샘플입니다 (전체 사이트가 아니라 얕게 찾은 일부입니다):\n\n'
        f'{sample_lines}\n\n'
        f'사용자가 원하는 것: {goal}\n\n'
        '이 목표를 달성하도록 HTTrack 크롤러가 이해하는 URL 필터 규칙을 만들어주세요. '
        '"+패턴"은 포함, "-패턴"은 제외이고 와일드카드 *를 쓸 수 있습니다 '
        '(예: "+*/recipe/*", "-*/cart/*", "-*/login/*"). '
        '경로에 포함된 고유 숫자나 ID 값은 반드시 * 로 대체해서 포괄적인 규칙을 만들어주세요 (예: /board/1234 -> +*/board/*). '
        '샘플에 없는 경로라도 목표에 맞게 합리적으로 패턴을 추론해도 됩니다.'
    )
    description = '사용자 목표에 맞는 HTTrack URL 필터 규칙을 제안한다.'

    if provider == 'ollama':
        result = ai_extract._ollama_json_call(model, schema, prompt)
    elif provider == 'anthropic':
        result = ai_extract._anthropic_tool_call(
            api_key, model, 'propose_scope_rules', description, schema, prompt)
    elif provider == 'openai':
        result = ai_extract._openai_tool_call(
            api_key, model, 'propose_scope_rules', description, schema, prompt)
    else:  # gemini
        result = ai_extract._gemini_json_call(api_key, model, schema, prompt)

    if result is None:
        raise RuntimeError('AI로부터 규칙 제안을 받지 못했습니다.')
    return result
