"""주소(URL) 관련 공용 헬퍼.

main.py와 dialogs.py 양쪽에서 쓰기 때문에 따로 뒀다.
"""
import urllib.request


def normalize_url(raw):
    """'news.naver.com'처럼 http(s):// 없이 적은 주소를 정상 주소로 만든다.
    브라우저 주소창에 익숙한 사용자는 스킴을 잘 안 붙이는데, Playwright의
    page.goto()는 스킴이 없으면 'Cannot navigate to invalid URL'로 실패한다.
    (실제로 사용자가 news.naver.com을 넣었다가 이 오류를 만났다.)"""
    url = (raw or '').strip()
    if not url:
        return url
    if '://' in url:
        return url
    if url.startswith('//'):
        return 'https:' + url
    return 'https://' + url


def _fetch_sample_html_from_url(url, timeout=10):
    """필드 제안용 샘플 페이지를 간단한 HTTP GET으로 가져온다 (아직 크롤링 전이므로
    렌더링 없이 원본 HTML만 있으면 충분함). 실패하면 None."""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except Exception:
        return None
