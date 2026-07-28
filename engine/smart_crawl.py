"""HTTrack의 정적 크롤링으로는 받아지지 않는 JS 렌더링/SPA 페이지를 위한 보조 크롤러.

사용자 PC에 이미 설치된 Chrome을 Playwright(channel='chrome')로 그대로 띄워서
페이지를 방문하고, 지연 로딩 콘텐츠가 나오도록 끝까지 스크롤한 뒤, 렌더링된 HTML을
저장한다. Chromium을 따로 내려받지 않으므로 사용자 PC에 Chrome이 없으면 동작하지
않는다 - 이 경우 예외 없이 로그만 남기고 조용히 종료한다 (예약 작업이 깨지지 않게).

주의: 이 버전은 지정된 URL들을 각각 방문해 렌더링 결과를 저장하는 수준이며,
HTTrack처럼 링크를 재귀적으로 따라가며 사이트 전체를 받는 기능은 없다.
"""
import os
import re
import urllib.parse

_FILENAME_SAFE_RE = re.compile(r'[^A-Za-z0-9_.-]+')


def _url_to_filename(url):
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.strip('/') or 'index'
    name = _FILENAME_SAFE_RE.sub('_', f'{parsed.netloc}_{path}')
    if not name.lower().endswith('.html'):
        name += '.html'
    return name


def _cookie_domains_for(urls):
    """대상 URL들의 호스트와 그 상위 도메인만 모은다 (blog.site.com -> {blog.site.com, site.com})."""
    domains = set()
    for raw in urls:
        raw = (raw or '').strip()
        if not raw:
            continue
        host = urllib.parse.urlparse(raw if '://' in raw else 'http://' + raw).hostname or ''
        parts = [p for p in host.split('.') if p]
        for i in range(max(1, len(parts) - 1)):
            domains.add('.'.join(parts[i:]))
    return domains


def _inject_local_cookies(page, urls, log_fn):
    """로컬 브라우저에 저장된 로그인 쿠키 중 '지금 받는 사이트 것만' 브라우저 컨텍스트에 넣는다.

    browser_cookie3.load()는 모든 사이트의 쿠키를 다 돌려주므로 그대로 주입하면
    관계없는 사이트(메일·은행 등)의 세션까지 이 브라우저 세션에 실리게 된다.
    반드시 대상 도메인으로 걸러서 넣는다. 실패해도 크롤링 자체는 계속 진행한다."""
    try:
        import browser_cookie3
    except ImportError:
        log_fn("[스마트 크롤링] 브라우저 로그인 사용에는 'browser_cookie3'가 필요해요. "
               '설치 명령: pip install browser_cookie3')
        return
    try:
        jar = browser_cookie3.load()
    except Exception as e:
        log_fn(f'[스마트 크롤링] 브라우저 쿠키를 읽지 못했어요 (보안 프로그램 차단일 수 있음): {e}')
        return

    wanted = _cookie_domains_for(urls)
    cookies = []
    for c in jar:
        bare = (c.domain or '').lstrip('.')
        if bare not in wanted:
            continue
        cookies.append({
            'name': c.name, 'value': c.value,
            'domain': c.domain, 'path': c.path or '/',
            'secure': bool(c.secure),
        })
    if not cookies:
        log_fn('[스마트 크롤링] 이 사이트에 대해 브라우저에 저장된 로그인이 없어요 — 로그인 없이 진행합니다.')
        return
    try:
        page.context.add_cookies(cookies)
        log_fn(f'[스마트 크롤링] 브라우저 로그인을 사용합니다 (이 사이트 쿠키 {len(cookies)}개).')
    except Exception as e:
        log_fn(f'[스마트 크롤링] 쿠키 주입 실패: {e}')


def _auto_scroll(page, max_steps=30, pause_ms=300):
    """지연 로딩 콘텐츠를 끌어내기 위해 페이지 끝까지 반복 스크롤한다."""
    last_height = 0
    for _ in range(max_steps):
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        page.wait_for_timeout(pause_ms)
        height = page.evaluate('document.body.scrollHeight')
        if height == last_height:
            break
        last_height = height


def run_smart_crawl(job, log_fn, progress_fn=None, should_stop=None):
    """job: jobs.py 스키마의 dict (urls/save_path/smart 필드 사용). 성공하면 True.

    progress_fn: 페이지를 하나 처리할 때마다 진행 상황 dict를 받는 콜백(선택).
        {'visited', 'max_pages', 'queued', 'errors', 'bytes_saved', 'current_url'}
        GUI에서 즉시 실행할 때 진행률 링과 지표를 채우는 데 쓴다.
    should_stop: True를 돌려주면 크롤링을 중단하는 콜백(선택). 사용자가 중지를 누른 경우.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        # 사용자 모르게 네트워크에서 패키지를 받아 설치하지 않는다. 예약 실행 중에
        # 조용히 설치가 일어나면 곤란하고, exe로 묶인 뒤에는 sys.executable이
        # 앱 자신이라 아예 엉뚱하게 동작한다. 설치 방법만 안내하고 끝낸다.
        log_fn('[스마트 크롤링] Playwright가 설치되어 있지 않습니다. '
               '설치 명령: pip install playwright')
        return False

    urls = job.get('urls', [])
    out_dir = job.get('save_path', '.')
    smart_opts = job.get('smart', {}) or {}
    wait_until = smart_opts.get('wait_until', 'networkidle')
    max_pages = smart_opts.get('max_pages', 50)
    
    httrack_opts = job.get('httrack', {}) or {}
    depth_str = httrack_opts.get('depth')
    try:
        max_depth = int(depth_str) if depth_str is not None else 1
    except ValueError:
        max_depth = 1

    scope = job.get('scope', {})
    domain_scope = scope.get('domain_scope', 'host')

    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception as e:
        log_fn(f'[스마트 크롤링] 저장 폴더를 만들 수 없습니다: {e}')
        return False

    def is_allowed_domain(target_url, start_urls):
        target_netloc = urllib.parse.urlparse(target_url).netloc.lower()
        for su in start_urls:
            su_netloc = urllib.parse.urlparse(su).netloc.lower()
            if domain_scope == 'subdomain':
                if target_netloc == su_netloc or target_netloc.endswith('.' + su_netloc) or su_netloc.endswith('.' + target_netloc):
                    return True
            else:
                if target_netloc == su_netloc:
                    return True
        return False

    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel='chrome', headless=True)
            except Exception:
                log_fn('[스마트 크롤링] 시스템 Chrome을 찾을 수 없어 번들된 Chromium을 시도합니다.')
                browser = p.chromium.launch(headless=True)

            page = browser.new_page()
            
            if job.get('use_local_cookies', False):
                _inject_local_cookies(page, urls, log_fn)

            from collections import deque
            queue = deque([(u, 1) for u in urls])
            visited_urls = set()
            visited_count = 0
            error_count = 0
            bytes_saved = 0

            def report(current_url=''):
                if progress_fn:
                    progress_fn({
                        'visited': visited_count, 'max_pages': max_pages,
                        'queued': len(queue), 'errors': error_count,
                        'bytes_saved': bytes_saved, 'current_url': current_url,
                    })

            while queue and visited_count < max_pages:
                if should_stop and should_stop():
                    log_fn('[스마트 크롤링] 사용자가 중지했습니다.')
                    break
                current_url, current_depth = queue.popleft()
                if current_url in visited_urls:
                    continue

                visited_urls.add(current_url)

                try:
                    log_fn(f'[스마트 크롤링] 방문 (Depth {current_depth}/{max_depth}): {current_url}')
                    page.goto(current_url, wait_until=wait_until, timeout=30000)
                    _auto_scroll(page)
                    html = page.content()

                    out_path = os.path.join(out_dir, _url_to_filename(current_url))
                    with open(out_path, 'w', encoding='utf-8') as f:
                        f.write(html)
                    visited_count += 1
                    bytes_saved += len(html.encode('utf-8', errors='ignore'))

                    if current_depth < max_depth:
                        try:
                            from bs4 import BeautifulSoup
                            soup = BeautifulSoup(html, 'lxml')
                            for a in soup.find_all('a', href=True):
                                next_url = urllib.parse.urljoin(current_url, a['href']).split('#')[0]
                                if next_url.startswith(('http://', 'https://')):
                                    if next_url not in visited_urls and is_allowed_domain(next_url, urls):
                                        queue.append((next_url, current_depth + 1))
                        except Exception as parse_e:
                            log_fn(f'[스마트 크롤링] 링크 파싱 오류: {parse_e}')
                            
                except Exception as e:
                    error_count += 1
                    log_fn(f'[스마트 크롤링] 실패 ({current_url}): {e}')

                report(current_url)

            browser.close()
        log_fn(f'[스마트 크롤링] 완료: {visited_count} 페이지 저장 (목표 최대치 {max_pages})')
        return visited_count > 0
    except Exception as e:
        log_fn(f'[스마트 크롤링] 오류: {e}')
        return False
