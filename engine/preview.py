"""완료된 프로젝트의 대표 페이지를 작은 뷰포트로 스크린샷 찍어 썸네일로 쓴다.

HTTrack이 기본으로 만드는 index.html을 우선 찾고, 없으면(스마트 크롤링이
저장한 파일처럼 이름 규칙이 다른 경우) 폴더 안 첫 번째 .html 파일로 대신한다.
smart_crawl.py와 동일한 Playwright channel='chrome' 패턴을 그대로 쓴다 -
사용자 PC의 기존 Chrome을 그대로 이용하므로 별도 브라우저를 내려받지 않는다.
"""
import os

import ai_extract

THUMB_WIDTH = 320
THUMB_HEIGHT = 200


def find_preview_target(project_dir):
    """미리보기로 찍을 HTML 파일 경로를 찾는다. 없으면 None."""
    index_path = os.path.join(project_dir, 'index.html')
    if os.path.exists(index_path):
        return index_path
    html_files = ai_extract.find_html_files(project_dir, max_files=1)
    return html_files[0] if html_files else None


def capture_preview(project_dir, out_path):
    """project_dir 안의 대표 페이지를 작은 뷰포트로 스크린샷 찍어 out_path(png)에 저장한다.
    성공하면 True. 대상이 없거나 실패해도 예외를 던지지 않는다 - 완료 흐름을 막으면 안 되므로."""
    target = find_preview_target(project_dir)
    if not target:
        return False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            page = browser.new_page(viewport={'width': THUMB_WIDTH, 'height': THUMB_HEIGHT})
            file_url = 'file:///' + os.path.abspath(target).replace('\\', '/')
            page.goto(file_url, timeout=15000)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            page.screenshot(path=out_path)
            browser.close()
        return os.path.exists(out_path)
    except Exception:
        return False
