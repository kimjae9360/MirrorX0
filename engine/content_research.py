"""RSS/Atom 피드, Reddit 공식 JSON API, 사용자가 직접 지정한 사이트 목록에서
트렌드/헤드라인을 합법적으로(스크래핑 우회 없이) 모아 하나의 표로 만든다.

MirrorX0의 핵심 목적(사이트 미러링/데이터 추출)과는 결이 다른 별개의 도구다 -
콘텐츠를 그대로 재가공해서 재배포하는 게 아니라, 발행자가 원래 공개적으로
내보내는 채널(RSS, 공식 API)이나 사용자 본인이 지정한 사이트에서 "무엇이
트렌드인지"를 조사하는 리서치 보조 도구다. 뽑아내는 건 제목/링크/짧은 요약/
출처뿐이고, 실제 콘텐츠 제작은 사람이 원본을 베끼지 않고 직접 한다.

세 가지 소스:
    1. RSS/Atom 피드 - 발행자가 자기 콘텐츠를 요약해서 공개적으로 내보내는
       표준 포맷. 수집 자체가 발행자의 동의 위에 있다.
    2. Reddit 공식 JSON API - 로그인/API 키 없이 읽을 수 있는 공개 리스팅
       엔드포인트(.json)를 정식 User-Agent로 호출한다.
    3. 사용자가 직접 지정하는 사이트 - 기존 pattern_detect(구조 감지)와
       ai_extract(값 추출)를 그대로 재사용해서 반복되는 헤드라인/카드
       항목을 뽑는다 - 이미 검증된 파이프라인이라 새로 만들 게 없다.
"""
import re
import json
import datetime
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET

_USER_AGENT = 'MirrorX0-ContentResearch/1.0 (personal research tool)'
_ATOM_NS = {'atom': 'http://www.w3.org/2005/Atom'}


def _http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={'User-Agent': _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _strip_html(text):
    return re.sub(r'<[^>]+>', ' ', text or '').strip()


# ---------------- RSS / Atom ----------------

def fetch_rss_items(feed_url, limit=20):
    """RSS 2.0 / Atom 피드를 읽어 [{'title','link','summary','published','source'}]로
    돌려준다. 실패해도 예외를 던지지 않고 빈 리스트를 돌려준다 - 여러 피드를
    한 번에 돌 때 하나 실패했다고 전체가 멈추면 안 되기 때문."""
    try:
        raw = _http_get(feed_url)
        root = ET.fromstring(raw)
    except Exception:
        return []

    items = []
    channel = root.find('channel')
    if channel is not None:
        for item in channel.findall('item')[:limit]:
            items.append({
                'title': _strip_html(item.findtext('title') or ''),
                'link': (item.findtext('link') or '').strip(),
                'summary': _strip_html(item.findtext('description') or '')[:300],
                'published': (item.findtext('pubDate') or '').strip(),
                'source': feed_url,
            })
        return items

    entries = root.findall('atom:entry', _ATOM_NS) or root.findall('entry')
    for entry in entries[:limit]:
        link_el = entry.find('atom:link', _ATOM_NS)
        if link_el is None:
            link_el = entry.find('link')
        link = link_el.get('href') if link_el is not None else ''
        title = entry.findtext('atom:title', default='', namespaces=_ATOM_NS) \
            or entry.findtext('title', default='')
        summary = entry.findtext('atom:summary', default='', namespaces=_ATOM_NS) \
            or entry.findtext('summary', default='')
        published = entry.findtext('atom:published', default='', namespaces=_ATOM_NS) \
            or entry.findtext('published', default='') \
            or entry.findtext('atom:updated', default='', namespaces=_ATOM_NS)
        items.append({
            'title': _strip_html(title),
            'link': (link or '').strip(),
            'summary': _strip_html(summary)[:300],
            'published': (published or '').strip(),
            'source': feed_url,
        })
    return items


# ---------------- Reddit (공식 공개 JSON, 로그인/키 불필요) ----------------

def fetch_reddit_top(subreddit, limit=20, time_filter='day'):
    """공식 공개 리스팅 엔드포인트(.json)를 정식 User-Agent로 호출한다.
    로그인이나 API 키가 필요 없는, Reddit이 누구에게나 허용하는 읽기 전용
    접근이다(비공식 우회가 아니다)."""
    subreddit = subreddit.strip().lstrip('r/').strip('/')
    if not subreddit:
        return []
    url = (f'https://www.reddit.com/r/{urllib.parse.quote(subreddit)}/top.json'
           f'?limit={limit}&t={time_filter}')
    try:
        raw = _http_get(url)
        data = json.loads(raw)
    except Exception:
        return []

    items = []
    for child in data.get('data', {}).get('children', []):
        d = child.get('data', {})
        items.append({
            'title': d.get('title', ''),
            'link': f"https://www.reddit.com{d.get('permalink', '')}",
            'summary': f"score {d.get('score', 0)} · comments {d.get('num_comments', 0)}",
            'published': '',
            'source': f'r/{subreddit}',
        })
    return items


# ---------------- 사용자 지정 사이트 (기존 파이프라인 재사용) ----------------

def fetch_site_items(url, api_key, provider='ollama', model=None, max_items=20):
    """사용자가 지정한 사이트 하나에서 반복되는 헤드라인/카드 항목을 뽑는다.
    pattern_detect(구조 감지, AI 미사용)로 먼저 찾아보고, 반복 패턴이 없으면
    페이지 전체를 항목 하나로 보고 뽑는다(둘 다 ai_extract의 기존 함수 그대로)."""
    import pattern_detect
    import ai_extract

    try:
        html = _http_get(url).decode('utf-8', errors='replace')
    except Exception:
        return []

    fields = [
        {'name': 'title', 'label': '제목', 'type': 'string'},
        {'name': 'link', 'label': '링크', 'type': 'string'},
    ]
    blocks = pattern_detect.detect_repeating_blocks(html)
    if blocks:
        items_html = blocks[0]['items_html'][:max_items]
        rows = ai_extract.extract_list_fields(items_html, fields, api_key, provider=provider, model=model)
    else:
        try:
            rows = [ai_extract.extract_fields(html, fields, api_key, provider=provider, model=model)]
        except Exception:
            rows = []

    for r in rows:
        r.setdefault('summary', '')
        r.setdefault('published', '')
        r['source'] = url
    return rows


# ---------------- 통합 실행 ----------------

def run_research(rss_feeds=(), subreddits=(), site_urls=(), api_key='', provider='ollama', model=None,
                  out_dir='.', formats=('csv',), log_fn=lambda m: None):
    """세 가지 소스를 전부 모아 하나의 표로 합치고 내보낸다.
    반환: (rows, saved_paths)"""
    import ai_extract
    all_rows = []

    for feed in rss_feeds:
        rows = fetch_rss_items(feed)
        log_fn(f'[리서치] RSS {feed}: {len(rows)}건')
        all_rows.extend(rows)

    for sub in subreddits:
        rows = fetch_reddit_top(sub)
        log_fn(f'[리서치] r/{sub}: {len(rows)}건')
        all_rows.extend(rows)

    for url in site_urls:
        rows = fetch_site_items(url, api_key, provider=provider, model=model)
        log_fn(f'[리서치] {url}: {len(rows)}건')
        all_rows.extend(rows)

    if not all_rows:
        log_fn('[리서치] 수집된 항목이 없습니다.')
        return [], []

    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    saved_paths = ai_extract.export_records(all_rows, out_dir, f'research_{timestamp}', list(formats))
    log_fn(f'[리서치] 총 {len(all_rows)}건 수집, 저장: {", ".join(saved_paths) if saved_paths else "없음"}')
    return all_rows, saved_paths
