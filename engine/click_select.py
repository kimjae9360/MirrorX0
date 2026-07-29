"""사용자가 실제 브라우저 화면에서 마우스로 항목 하나를 가리키고 클릭하면,
그 항목과 구조적으로 같은 종류(형제 요소들)를 찾아 반복 패턴으로 인식한다
(Listly의 '클릭해서 고르기(Point & Click)' 기능 참고).

pattern_detect.py의 자동 감지(태그+클래스 조합으로 그룹화한 뒤 '풍부함'으로
채점해서 가장 그럴듯한 후보를 스스로 고름)와 원리는 같지만, 이건 사용자가
직접 고른 예시 하나를 기준으로 그 구조와 일치하는 형제 요소를 전부 모으는
수동 경로다 - 자동 감지가 메뉴/광고 등을 잘못 짚었을 때, 또는 애초에 자동
감지가 후보를 못 찾을 만큼 애매한 구조일 때 사용자가 직접 정정할 수 있다.

브라우저는 headless=False(화면에 실제로 보이는 채)로 띄운다 - 사용자가
마우스로 가리키고 클릭해야 하므로 당연히 화면이 보여야 한다.
"""
import threading

# 클릭한 요소를 가리켜서 셀렉터를 만들고, 마우스를 올렸을 때 주황 테두리로
# 표시해준다. 클릭하면 기본 동작(링크 이동 등)을 막고 파이썬으로 결과를 보낸다.
_PICKER_SCRIPT = r"""
(function() {
    if (window.__mirrorx_picker_installed) { return; }
    window.__mirrorx_picker_installed = true;

    function mxGetSelector(el) {
        if (el.id) { return '#' + CSS.escape(el.id); }
        if (el.classList && el.classList.length > 0) {
            var classes = Array.from(el.classList).map(function(c) { return CSS.escape(c); });
            return el.tagName.toLowerCase() + '.' + classes.join('.');
        }
        var path = [];
        var node = el;
        for (var i = 0; i < 4 && node && node.nodeType === 1; i++) {
            var tag = node.tagName.toLowerCase();
            var parent = node.parentElement;
            if (parent) {
                var siblings = Array.from(parent.children).filter(function(c) {
                    return c.tagName === node.tagName;
                });
                if (siblings.length > 1) {
                    tag += ':nth-of-type(' + (siblings.indexOf(node) + 1) + ')';
                }
            }
            path.unshift(tag);
            node = parent;
        }
        return path.join(' > ');
    }

    var prevEl = null;
    var prevOutline = '';

    function onOver(e) {
        if (prevEl) { prevEl.style.outline = prevOutline; }
        prevEl = e.target;
        prevOutline = e.target.style.outline;
        e.target.style.outline = '3px solid #ff6a00';
    }

    function onClick(e) {
        e.preventDefault();
        e.stopPropagation();
        var selector = mxGetSelector(e.target);
        var preview = (e.target.innerText || '').slice(0, 80);
        window.mirrorx_pick(selector, e.target.tagName.toLowerCase(), preview);
    }

    document.addEventListener('mouseover', onOver, true);
    document.addEventListener('click', onClick, true);
})();
"""


def find_similar_elements(html, selector):
    """페이지 HTML 전체에서 주어진 CSS 셀렉터와 일치하는 요소를 전부 찾는다.
    (사용자가 클릭한 요소 자기 자신이 아니라, 그와 '같은 종류'인 형제 요소들.)"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')
    try:
        items = soup.select(selector)
    except Exception:
        return []
    return [str(it) for it in items]


def pick_element_and_collect(url, use_local_cookies=False, timeout_seconds=300):
    """실제 브라우저 창을 열어 사용자가 항목 하나를 클릭할 때까지 기다린 뒤,
    그 항목과 구조적으로 같은 종류의 요소를 전부 모아 돌려준다.

    반환: {'selector': str, 'tag': str, 'preview': str, 'items_html': [str, ...]}
    사용자가 창을 닫아버리거나 시간이 너무 오래 걸리면 RuntimeError를 던진다."""
    from playwright.sync_api import sync_playwright

    picked = {}
    event = threading.Event()

    def on_pick(selector, tag, preview):
        picked['selector'] = selector
        picked['tag'] = tag
        picked['preview'] = preview
        event.set()

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel='chrome', headless=False)
        except Exception:
            browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.expose_function('mirrorx_pick', on_pick)

        if use_local_cookies:
            import smart_crawl
            smart_crawl._inject_local_cookies(page, [url], lambda m: None)

        page.goto(url, wait_until='domcontentloaded', timeout=30000)
        page.evaluate(_PICKER_SCRIPT)
        # 사용자가 페이지를 이동하더라도(다른 링크 등) 스크립트가 다시 필요하므로
        # 새 문서가 로드될 때마다 다시 주입한다.
        page.on('load', lambda: page.evaluate(_PICKER_SCRIPT))

        waited = 0.0
        while not event.is_set():
            if page.is_closed():
                browser.close()
                raise RuntimeError('사용자가 브라우저 창을 닫아서 취소되었습니다.')
            try:
                page.wait_for_timeout(200)
            except Exception:
                browser.close()
                raise RuntimeError('사용자가 브라우저 창을 닫아서 취소되었습니다.')
            waited += 0.2
            if waited > timeout_seconds:
                browser.close()
                raise RuntimeError('시간이 너무 오래 걸려 취소되었습니다.')

        html = page.content()
        browser.close()

    items_html = find_similar_elements(html, picked['selector'])
    if not items_html:
        # 셀렉터가 너무 구체적이라 클릭한 요소 자신 말고는 안 잡혔을 수 있다.
        # 그래도 사용자가 고른 항목 자체는 결과에 넣어 최소 1행은 나오게 한다.
        items_html = [f"<div>{picked['preview']}</div>"]

    return {
        'selector': picked['selector'],
        'tag': picked['tag'],
        'preview': picked['preview'],
        'items_html': items_html,
    }
