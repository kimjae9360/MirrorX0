"""자바스크립트로 그려지는 사이트를 '오프라인에서 그대로 열리는' 사본으로 받는다.

HTTrack은 HTML 원문만 읽기 때문에 React/Vue 같은 사이트를 받으면 빈 껍데기가 된다.
여기서는 사용자 PC에 설치된 Chrome을 Playwright로 띄워 실제로 화면을 그린 뒤 저장한다.

동작 순서:
    1. 페이지 방문 -> 끝까지 스크롤(지연 로딩 콘텐츠를 끌어냄) -> 렌더링된 HTML 확보
    2. 그 사이 브라우저가 받은 모든 응답(CSS/JS/이미지/폰트)을 response 이벤트로
       가로채 host/path 구조 그대로 저장. 자바스크립트가 나중에 요청하는 것까지
       잡히므로, 정적 파서로는 불가능한 자산까지 전부 모인다.
    3. 링크를 따라 다음 페이지로 (max_pages / 깊이 제한까지)
    4. 전부 받은 뒤 HTML/CSS 안의 주소를 로컬 상대경로로 치환

이렇게 해야 결과 폴더의 index.html을 더블클릭했을 때 원래 모습대로 열린다.
(예전에는 HTML만 저장해서 스타일이 다 깨진 채로 열렸다.)

Chrome이 없으면 예외를 내지 않고 로그만 남기고 종료한다(예약 작업이 깨지지 않게).
"""
import os
import re
import json
import random
import hashlib
import urllib.parse

# 윈도우 파일 이름에 못 쓰는 문자들
_ILLEGAL_CHARS_RE = re.compile(r'[<>:"|?*\\\x00-\x1f]')
# CSS 안의 url(...) 을 찾는다
_CSS_URL_RE = re.compile(r'url\(\s*([^)]+?)\s*\)', re.IGNORECASE)

_STATE_FILENAME = '.mirrorx_smart_state.json'


def _state_file_path(out_dir):
    return os.path.join(out_dir, _STATE_FILENAME)


def _load_crawl_state(out_dir):
    """중단된 적이 있으면 방문 기록/대기열을 불러온다. 없으면 None."""
    path = _state_file_path(out_dir)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        visited = set(data.get('visited_urls', []))
        queue_items = [(u, d) for u, d in data.get('queue', [])]
        return visited, queue_items
    except Exception:
        return None


def _save_crawl_state(out_dir, visited_urls, queue_items):
    path = _state_file_path(out_dir)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'visited_urls': sorted(visited_urls), 'queue': [list(q) for q in queue_items]}, f)
    except OSError:
        pass


def _clear_crawl_state(out_dir):
    try:
        os.remove(_state_file_path(out_dir))
    except OSError:
        pass


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
        # Chrome이 켜져 있으면 쿠키 파일이 잠겨 있어서, 잠긴 채로도 읽으려면
        # Windows 관리자 권한(Volume Shadow Copy)이 필요하다 - 이게 없어서 나는
        # 에러가 가장 흔한 원인이라 따로 짚어준다(막연히 "보안 프로그램" 탓으로
        # 돌리면 사용자가 정작 해결할 방법을 못 찾는다).
        msg = str(e).lower()
        if 'admin' in msg or 'permission denied' in msg or type(e).__name__ == 'RequiresAdminError':
            log_fn('[스마트 크롤링] 브라우저 쿠키를 읽지 못했어요 - Chrome이 켜져 있으면 쿠키 파일이 '
                   '잠겨 있어 관리자 권한 없이는 읽을 수 없어요. Chrome을 완전히 종료한 뒤 다시 '
                   f'시도해주세요. (상세: {e})')
        else:
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


def _safe_segment(seg, max_len=90):
    """URL 조각 하나를 윈도우 파일/폴더 이름으로 쓸 수 있게 다듬는다.

    윈도우에서 못 쓰는 문자(< > : " | ? * \\)를 바꾸고, 끝의 공백/점을 없애고,
    너무 길면 잘라내되 뒤에 해시를 붙여 서로 겹치지 않게 한다.
    '..' 같은 조각도 '_'로 바꾸므로 저장 폴더 밖으로 새어나갈 수 없다."""
    seg = urllib.parse.unquote(seg)
    seg = _ILLEGAL_CHARS_RE.sub('_', seg).strip(' .')
    if seg in ('', '.', '..'):
        return '_'
    if len(seg) > max_len:
        stem, dot, ext = seg.rpartition('.')
        tag = hashlib.md5(seg.encode('utf-8')).hexdigest()[:8]
        if dot and len(ext) <= 8:
            seg = f'{stem[:max_len - len(ext) - 10]}_{tag}.{ext}'
        else:
            seg = f'{seg[:max_len - 9]}_{tag}'
    return seg


def local_path_for(url, out_dir, content_type=''):
    """주소를 '저장 폴더 안의 실제 파일 경로'로 바꾼다.

    HTTrack과 같은 방식으로 host/path 구조를 그대로 만든다.
        https://site.com/a/b.css        -> out_dir/site.com/a/b.css
        https://site.com/blog/          -> out_dir/site.com/blog/index.html
        https://site.com/api?page=2     -> out_dir/site.com/api_1a2b3c4d
    쿼리스트링이 다르면 다른 파일이므로 이름 뒤에 짧은 해시를 붙여 구분한다."""
    parsed = urllib.parse.urlsplit(url)
    host = _safe_segment(parsed.netloc or 'localhost')
    path = parsed.path or '/'
    if path.endswith('/'):
        path += 'index.html'
    segments = [_safe_segment(s) for s in path.split('/') if s] or ['index.html']

    if parsed.query:
        tag = hashlib.md5(parsed.query.encode('utf-8')).hexdigest()[:8]
        stem, dot, ext = segments[-1].rpartition('.')
        segments[-1] = f'{stem}_{tag}.{ext}' if dot else f'{segments[-1]}_{tag}'

    # 확장자가 없는 HTML 주소는 .html을 붙여야 브라우저에서 바로 열린다.
    # (덤으로 /a 와 /a/b 가 파일-폴더로 충돌하는 것도 대부분 막아준다)
    if '.' not in segments[-1] and 'html' in content_type:
        segments[-1] += '.html'

    return os.path.join(out_dir, host, *segments)


class _MirrorWriter:
    """브라우저가 받아온 것들을 디스크에 저장하고, 주소↔로컬경로 대응표를 들고 있는다.

    Playwright의 response 이벤트를 듣기 때문에 자바스크립트가 나중에 불러오는
    이미지·CSS·폰트까지 전부 잡힌다. 정적 HTML만 훑는 방식으로는 불가능한 부분이다."""

    def __init__(self, out_dir, log_fn):
        self.out_dir = out_dir
        self.log_fn = log_fn
        self.url_to_path = {}     # 절대 주소 -> 로컬 절대 경로
        self.bytes_saved = 0
        self.asset_count = 0
        self._failed = set()

    def _write(self, path, data):
        """파일을 쓴다. 경로 일부가 이미 파일이라 폴더를 못 만드는 경우
        (예: /a 를 파일로 저장했는데 /a/b 가 또 오는 경우) 이름을 바꿔 피한다."""
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except (NotADirectoryError, FileExistsError, OSError):
            path = os.path.join(self.out_dir, '_conflict',
                                hashlib.md5(path.encode('utf-8')).hexdigest()[:16])
            os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)
        return path

    def on_response(self, response):
        """응답이 올 때마다 호출된다. HTML은 여기서 저장하지 않는다 -
        자바스크립트 실행이 끝난 '완성된' 화면을 나중에 따로 저장하기 때문."""
        url = response.url.split('#')[0]
        if not url.startswith(('http://', 'https://')) or url in self.url_to_path:
            return
        content_type = (response.headers or {}).get('content-type', '').lower()
        target = local_path_for(url, self.out_dir, content_type)

        if 'html' in content_type:
            self.url_to_path[url] = target      # 링크 치환용으로 자리만 잡아둔다
            return
        try:
            body = response.body()
        except Exception:
            self._failed.add(url)               # 리다이렉트/취소된 요청 등
            return
        try:
            self.url_to_path[url] = self._write(target, body)
            self.bytes_saved += len(body)
            self.asset_count += 1
        except Exception as e:
            self._failed.add(url)
            self.log_fn(f'[스마트 크롤링] 자산 저장 실패 ({url}): {e}')

    def save_page(self, url, html):
        """렌더링이 끝난 페이지 HTML을 저장하고 그 경로를 대응표에 넣는다."""
        url = url.split('#')[0]
        path = local_path_for(url, self.out_dir, 'text/html')
        path = self._write(path, html.encode('utf-8', errors='replace'))
        self.url_to_path[url] = path
        self.bytes_saved += len(html.encode('utf-8', errors='ignore'))
        return path


def _to_relative(from_file, to_file):
    """저장된 파일끼리 서로를 가리키는 상대 경로를 만든다 (폴더를 통째로 옮겨도 살아 있게)."""
    rel = os.path.relpath(to_file, os.path.dirname(from_file))
    return urllib.parse.quote(rel.replace(os.sep, '/'))


def _rewrite_css(text, base_url, page_file, url_to_path):
    """CSS 안의 url(...) 을 로컬 경로로 바꾼다."""
    def repl(m):
        raw = m.group(1).strip('\'"')
        if raw.startswith(('data:', '#')):
            return m.group(0)
        absolute = urllib.parse.urljoin(base_url, raw).split('#')[0]
        target = url_to_path.get(absolute)
        return f'url({_to_relative(page_file, target)})' if target else m.group(0)
    return _CSS_URL_RE.sub(repl, text)


def rewrite_saved_files(writer, page_files, log_fn):
    """크롤링이 끝난 뒤, 저장한 HTML/CSS 안의 주소를 로컬 경로로 바꾼다.

    크롤링 도중이 아니라 '전부 받은 뒤에' 하는 이유:
    아직 안 받은 페이지로 가는 링크도 나중에 받고 나면 이어져야 하기 때문이다.
    대응표에 없는 주소(우리가 안 받은 것)는 원래 주소 그대로 둬서 인터넷으로 나간다."""
    from bs4 import BeautifulSoup

    url_to_path = writer.url_to_path
    rewritten = 0

    # 1) HTML - 태그의 주소 속성들
    for page_url, page_file in page_files:
        try:
            with open(page_file, encoding='utf-8', errors='replace') as f:
                soup = BeautifulSoup(f.read(), 'lxml')

            for tag, attr in (('a', 'href'), ('link', 'href'), ('img', 'src'), ('script', 'src'),
                              ('source', 'src'), ('video', 'poster'), ('iframe', 'src'),
                              ('embed', 'src'), ('audio', 'src')):
                for el in soup.find_all(tag):
                    raw = el.get(attr)
                    if not raw or raw.startswith(('data:', 'javascript:', 'mailto:', '#')):
                        continue
                    absolute = urllib.parse.urljoin(page_url, raw).split('#')[0]
                    target = url_to_path.get(absolute)
                    if target:
                        el[attr] = _to_relative(page_file, target)

            # 반응형 이미지(srcset)는 "주소 1x, 주소 2x" 형태라 조각별로 바꾼다
            for el in soup.find_all(srcset=True):
                parts = []
                for chunk in el['srcset'].split(','):
                    bits = chunk.strip().split(' ', 1)
                    absolute = urllib.parse.urljoin(page_url, bits[0]).split('#')[0]
                    target = url_to_path.get(absolute)
                    head = _to_relative(page_file, target) if target else bits[0]
                    parts.append(' '.join([head] + bits[1:]))
                el['srcset'] = ', '.join(parts)

            for el in soup.find_all('style'):
                if el.string:
                    el.string = _rewrite_css(el.string, page_url, page_file, url_to_path)

            with open(page_file, 'w', encoding='utf-8') as f:
                f.write(str(soup))
            rewritten += 1
        except Exception as e:
            log_fn(f'[스마트 크롤링] 링크 치환 실패 ({page_file}): {e}')

    # 2) 따로 받은 .css 파일 안의 url(...)
    for url, path in list(url_to_path.items()):
        if not path.lower().endswith('.css') or not os.path.exists(path):
            continue
        try:
            with open(path, encoding='utf-8', errors='replace') as f:
                text = f.read()
            with open(path, 'w', encoding='utf-8') as f:
                f.write(_rewrite_css(text, url, path, url_to_path))
        except Exception:
            pass

    return rewritten


# 링크로 발견됐을 때 '페이지로 열어보지 않는' 확장자들. 이런 주소를 그대로
# page.goto()로 열면 브라우저가 페이지 대신 파일 다운로드를 시도하거나, 받아온
# 바이너리를 텍스트로 잘못 저장하게 된다. (이미지/CSS/JS 등은 이것과 무관하게
# 방문한 페이지 안에서 <img>/<link>로 쓰이면 response 이벤트로 여전히 저장된다 -
# 여기서 거르는 건 어디까지나 '이 주소 자체를 새 페이지로 열지 말지'뿐이다.)
_NON_PAGE_EXT = {
    'pdf', 'zip', 'rar', '7z', 'tar', 'gz', 'exe', 'msi', 'dmg', 'apk',
    'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'ico', 'bmp', 'tiff',
    'mp4', 'mp3', 'avi', 'mov', 'webm', 'wav', 'flac', 'ogg', 'm4a',
    'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'hwp', 'csv',
    'css', 'js', 'json', 'xml', 'woff', 'woff2', 'ttf', 'eot',
}


def _is_page_link(url):
    """이 주소가 '방문할 페이지'인지, 아니면 파일 다운로드 링크인지 확장자로 가른다."""
    path = urllib.parse.urlparse(url).path
    last = path.rsplit('/', 1)[-1]
    ext = last.rsplit('.', 1)[-1].lower() if '.' in last else ''
    return ext not in _NON_PAGE_EXT


def _start_boundaries(start_urls):
    """'같은 폴더 안에서만' 범위를 위해, 시작 주소들의 '디렉터리 경계'를 계산한다.
    site.com/book/1234/1 로 시작하면 경계는 site.com + '/book/1234/' 가 되어
    site.com/book/1234/* 는 통과하고 site.com/book/5678/* 는 막힌다."""
    boundaries = []
    for su in start_urls:
        p = urllib.parse.urlparse(su)
        directory = p.path.rsplit('/', 1)[0] + '/'
        boundaries.append((p.netloc.lower(), directory))
    return boundaries


def _within_boundaries(target_url, boundaries):
    p = urllib.parse.urlparse(target_url)
    return any(p.netloc.lower() == netloc and p.path.startswith(directory)
              for netloc, directory in boundaries)


# 대형 쇼핑몰/포털은 자동화된 접속 자체를 막는 경우가 흔하다(예: Akamai 등의
# 봇 차단 서비스). 이럴 땐 페이지는 "저장됐지만" 내용이 차단 안내문뿐이라 -
# 실패한 게 아니라 성공한 것처럼 보여서 사용자가 왜 안 되는지 알기 어렵다.
# 완벽한 감지는 불가능하지만, 흔한 문구 + 유난히 짧은 본문 조합으로 대략
# 짚어주는 정도는 가능하다(오탐 가능성이 있으니 '~같아요'로 단정하지 않는다).
_BLOCK_SIGNS = (
    'access denied', 'you don\'t have permission to access',
    'unusual traffic', 'blocked', 'captcha', 'are you a robot',
    '접근이 거부', '접근 권한이 없습니다', '차단되었습니다', '자동화된 요청',
    '비정상적인 접근', '보안문자',
)


def _looks_blocked(html):
    """본문 글자 수가 아주 적으면서(진짜 페이지라면 이보다는 김) 흔한 차단
    문구가 보이면 True. 둘 다 만족해야 하므로 우연히 문구 하나가 들어간
    정상 페이지를 오탐할 가능성을 줄인다."""
    text = re.sub(r'<[^>]+>', ' ', html or '').lower()
    if len(text) > 2000:
        return False
    return any(sign in text for sign in _BLOCK_SIGNS)


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
    same_folder = bool(scope.get('same_folder'))
    boundaries = _start_boundaries(urls) if same_folder else None

    # 요청 사이 텀 - HTTrack 쪽 '안전장치'에는 있었는데 스마트 크롤링에는 없던 것.
    # 사이트 하나에 짧은 시간 안에 페이지 요청을 몰아치면 차단당하기 쉽다.
    pause = smart_opts.get('pause')  # (최소초, 최대초) 또는 None(꺼짐)

    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception as e:
        log_fn(f'[스마트 크롤링] 저장 폴더를 만들 수 없습니다: {e}')
        return False

    import storage
    free_mb, disk_status = storage.check_disk_space(out_dir)
    if disk_status == 'critical':
        log_fn(f'[스마트 크롤링] 디스크 여유 공간이 너무 부족해({free_mb:.0f}MB) 시작하지 않습니다. '
               '공간을 확보한 뒤 다시 시도해주세요.')
        return False
    elif disk_status == 'warn':
        log_fn(f'[스마트 크롤링] 디스크 여유 공간이 얼마 남지 않았습니다({free_mb:.0f}MB). 계속 진행합니다.')

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

    def is_allowed(target_url, start_urls):
        """도메인 범위 + (켰다면) 같은 폴더 범위 + 페이지로 열어볼 만한 주소인지를 모두 본다."""
        if not _is_page_link(target_url):
            return False
        if not is_allowed_domain(target_url, start_urls):
            return False
        if same_folder and not _within_boundaries(target_url, boundaries):
            return False
        return True

    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel='chrome', headless=True)
            except Exception:
                log_fn('[스마트 크롤링] 시스템 Chrome을 찾을 수 없어 번들된 Chromium을 시도합니다.')
                browser = p.chromium.launch(headless=True)

            # 뷰포트를 지정하지 않으면 1280x720으로 고정된다 - 요즘 사이트는 그
            # 폭에서 태블릿용 레이아웃을 내주는 경우가 있어, 데스크톱 화면 그대로
            # 받으려면 넉넉한 폭으로 잡아주는 편이 낫다.
            page = browser.new_page(viewport={'width': 1920, 'height': 1080})

            # 브라우저가 받아오는 모든 것(CSS/JS/이미지/폰트)을 저장한다.
            # 자바스크립트가 나중에 요청하는 것까지 잡히기 때문에, 이걸 해야
            # 오프라인에서 화면이 원래 모습대로 열린다.
            writer = _MirrorWriter(out_dir, log_fn)
            page.on('response', writer.on_response)
            page_files = []           # [(페이지 주소, 저장된 파일 경로)]

            if job.get('use_local_cookies', False):
                _inject_local_cookies(page, urls, log_fn)

            from collections import deque

            resumed_state = None if job.get('force_restart') else _load_crawl_state(out_dir)
            if resumed_state:
                visited_urls, queue_items = resumed_state
                queue = deque(queue_items)
                log_fn(f'[스마트 크롤링] 이전에 중단된 지점에서 이어받습니다 '
                       f'(이미 방문 {len(visited_urls)}개, 남은 대기열 {len(queue)}개).')
            else:
                queue = deque([(u, 1) for u in urls])
                visited_urls = set()
                _clear_crawl_state(out_dir)  # force_restart 등으로 새로 시작하면 이전 상태는 버린다

            visited_count = len(visited_urls)
            error_count = 0
            blocked_notice_shown = False

            def report(current_url=''):
                if progress_fn:
                    progress_fn({
                        'visited': visited_count, 'max_pages': max_pages,
                        'queued': len(queue), 'errors': error_count,
                        'bytes_saved': writer.bytes_saved, 'current_url': current_url,
                    })

            while queue and visited_count < max_pages:
                if should_stop and should_stop():
                    log_fn('[스마트 크롤링] 사용자가 중지했습니다.')
                    break

                # 페이지마다 디스크 여유 공간을 확인한다 - disk_usage 자체는 가벼운
                # 시스템 호출이라 매번 봐도 느려지지 않고, 디스크가 꽉 찬 채로 계속
                # 쓰다가 파일이 손상되는 것을 막는 게 더 중요하다.
                free_mb, disk_status = storage.check_disk_space(out_dir)
                if disk_status == 'critical':
                    log_fn(f'[스마트 크롤링] 디스크 여유 공간이 부족해({free_mb:.0f}MB) 여기서 멈춥니다. '
                           '공간을 확보한 뒤 다시 실행하면 이어받습니다.')
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

                    if not blocked_notice_shown and _looks_blocked(html):
                        blocked_notice_shown = True
                        log_fn('[스마트 크롤링] 이 사이트가 자동 접속을 막고 있는 것 같아요 '
                               '(차단/보안 확인 페이지가 저장된 것으로 보임). 대형 쇼핑몰·포털처럼 '
                               '봇 차단이 강한 사이트는 이 도구로 받아지지 않을 수 있어요.')

                    # 렌더링이 끝난 화면을 host/path 구조 그대로 저장한다
                    # (링크 치환은 전부 받은 뒤 한 번에 한다)
                    page_files.append((current_url.split('#')[0],
                                       writer.save_page(current_url, html)))
                    visited_count += 1

                    if current_depth < max_depth:
                        try:
                            from bs4 import BeautifulSoup
                            soup = BeautifulSoup(html, 'lxml')
                            for a in soup.find_all('a', href=True):
                                next_url = urllib.parse.urljoin(current_url, a['href']).split('#')[0]
                                if next_url.startswith(('http://', 'https://')):
                                    if next_url not in visited_urls and is_allowed(next_url, urls):
                                        queue.append((next_url, current_depth + 1))
                        except Exception as parse_e:
                            log_fn(f'[스마트 크롤링] 링크 파싱 오류: {parse_e}')
                            
                except Exception as e:
                    error_count += 1
                    log_fn(f'[스마트 크롤링] 실패 ({current_url}): {e}')

                report(current_url)
                _save_crawl_state(out_dir, visited_urls, queue)

                # 다음 페이지로 넘어가기 전에 잠깐 쉰다(설정했다면). 마지막 페이지 뒤에는
                # 어차피 쓸모없는 대기라 큐가 남아있을 때만 쉰다.
                if pause and queue:
                    lo, hi = pause
                    if hi > 0:
                        page.wait_for_timeout(random.uniform(min(lo, hi), hi) * 1000)

            # 대기열이 자연스럽게 다 빈 경우(더 갈 곳이 없어 끝난 것)에만 이어받기
            # 상태를 지운다. 사용자가 멈췄거나(should_stop), max_pages에 걸렸거나,
            # 디스크 공간 부족으로 멈췄다면 상태를 남겨서 다음에 이어받을 수 있게 한다.
            if not queue:
                _clear_crawl_state(out_dir)

            browser.close()

        # 다 받은 뒤에 링크를 로컬 경로로 바꾼다.
        if page_files:
            log_fn('[스마트 크롤링] 링크를 오프라인용으로 바꾸는 중…')
            rewrite_saved_files(writer, page_files, log_fn)

        log_fn(f'[스마트 크롤링] 완료: 페이지 {visited_count}개, '
               f'함께 받은 파일 {writer.asset_count}개 (목표 최대치 {max_pages})')
        if page_files:
            log_fn(f'[스마트 크롤링] 이 파일을 브라우저로 열면 됩니다: {page_files[0][1]}')
        return visited_count > 0
    except Exception as e:
        log_fn(f'[스마트 크롤링] 오류: {e}')
        return False
