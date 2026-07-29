"""HTTrack/스마트 크롤링으로 받은 폴더를, 개발 참고용으로 보기 좋게 정리한
'사본'을 만든다. 원본 폴더는 절대 건드리지 않는다 - 링크를 다시 쓰는 작업은
실수하면 사이트가 깨질 수 있는 되돌리기 어려운 작업이라, 항상 새 폴더에
결과를 만들고 원본은 그대로 보존한다.

두 가지를 한다:
1. HTTrack이 남기는 내부 관리용 파일(hts-cache/, hts-log.txt, cookies.txt 등)
   제거 - 이건 실제 사이트 파일이 아니라 HTTrack 자신을 위한 캐시/로그다.
2. 이미지/CSS/JS/폰트를 확장자 기준으로 css/js/images/fonts 폴더로 재배치하고,
   HTML/CSS 안의 참조(href/src/url()/@import)를 새 위치에 맞게 다시 쓴다.

주의(안전을 위한 의도적 제약): 자바스크립트 코드가 문자열로 경로를 만들어
쓰는 경우(동적 로딩 등)는 정적 분석만으로는 안전하게 고칠 방법이 없다.
그래서 어떤 자산 파일의 이름이 .js 파일 안에 텍스트로 보이면, 깨질 위험을
피하기 위해 그 파일은 옮기지 않고 원래 자리에 그대로 둔다(자바스크립트
파일 자체의 내용도 다시 쓰지 않는다 - HTML/CSS의 정적 참조만 다룬다).
"""
import os
import re
import shutil

# 실제 사이트 콘텐츠가 아니라 HTTrack 자신을 위한 파일/폴더
_HTTRACK_ARTIFACTS = {
    'hts-cache', 'hts-log.txt', 'hts-in_progress.lock', 'cookies.txt', 'hts-done.txt',
}

_TYPE_FOLDERS = {
    'css': {'.css'},
    'js': {'.js', '.mjs'},
    'images': {'.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico', '.bmp'},
    'fonts': {'.woff', '.woff2', '.ttf', '.eot', '.otf'},
}

_TEXT_EXTS_FOR_REWRITE = {'.html', '.htm', '.css'}

_HTML_REF_RE = re.compile(r'(?:href|src)\s*=\s*"([^"]+)"', re.IGNORECASE)
_CSS_URL_RE = re.compile(r'url\(\s*[\'"]?([^\'")]+)[\'"]?\s*\)')
_CSS_IMPORT_RE = re.compile(r'@import\s+[\'"]([^\'"]+)[\'"]')


def _is_external(ref):
    return ref.startswith(('http://', 'https://', '//', 'data:', 'mailto:', 'javascript:', '#'))


def _ext_category(filename):
    ext = os.path.splitext(filename)[1].lower()
    for category, exts in _TYPE_FOLDERS.items():
        if ext in exts:
            return category
    return None


def _remove_bookkeeping(target_dir, log_fn):
    removed_names = set()
    for root, dirs, files in os.walk(target_dir):
        for name in list(dirs):
            if name in _HTTRACK_ARTIFACTS:
                shutil.rmtree(os.path.join(root, name), ignore_errors=True)
                dirs.remove(name)
                removed_names.add(name)
        for name in list(files):
            if name in _HTTRACK_ARTIFACTS:
                try:
                    os.remove(os.path.join(root, name))
                    removed_names.add(name)
                except OSError:
                    pass
    if removed_names:
        log_fn(f'[폴더 정리] HTTrack 관리용 파일/폴더 제거: {", ".join(sorted(removed_names))}')


def _collect_js_referenced_names(target_dir, candidate_names):
    """candidate_names(옮기려는 파일들의 파일명) 중 어떤 것이 .js 파일 안에
    문자열로 등장하는지 확인한다 - 등장하면 동적 로딩 등으로 깨질 위험이
    있다고 보고 옮기지 않는다(정확한 파싱이 아니라 보수적인 안전장치)."""
    referenced = set()
    for root, _dirs, files in os.walk(target_dir):
        for name in files:
            if os.path.splitext(name)[1].lower() not in ('.js', '.mjs'):
                continue
            try:
                with open(os.path.join(root, name), 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except OSError:
                continue
            for candidate in candidate_names:
                if candidate not in referenced and candidate in content:
                    referenced.add(candidate)
    return referenced


def _unique_target_path(target_dir, rel_path):
    """같은 파일명이 여러 폴더에서 옮겨져 부딪히면 뒤에 _2, _3 ... 을 붙인다."""
    base, ext = os.path.splitext(rel_path)
    candidate = rel_path
    n = 2
    while os.path.exists(os.path.join(target_dir, candidate)):
        candidate = f'{base}_{n}{ext}'
        n += 1
    return candidate


def _rewrite_references(target_dir, moved, log_fn):
    """moved: {정리 폴더 기준 기존 상대경로: 새 상대경로}. 모든 html/css
    파일을 훑으며 각 참조를 새 위치 기준 상대경로로 다시 계산해 바꾼다.

    주의할 점: 파일 자신이 옮겨진 경우, 그 안에 적힌 상대경로는 '옮기기 전
    위치'를 기준으로 쓰여 있다(아직 다시 쓰지 않았으므로). 그래서 참조를
    해석할 때는 '옮기기 전 위치'(authoring_dir) 기준으로 대상을 찾고, 실제로
    새로 써넣을 경로는 '지금 있는 위치'(current_dir) 기준으로 계산해야 한다."""
    old_to_new_abs = {
        os.path.normpath(os.path.join(target_dir, old)): os.path.normpath(os.path.join(target_dir, new))
        for old, new in moved.items()
    }
    new_to_old_rel = {new: old for old, new in moved.items()}

    def resolve(ref, authoring_dir):
        ref_path_only = ref.split('?', 1)[0].split('#', 1)[0]
        if not ref_path_only:
            return None
        if ref_path_only.startswith('/'):
            abs_target = os.path.normpath(os.path.join(target_dir, ref_path_only.lstrip('/')))
        else:
            abs_target = os.path.normpath(os.path.join(authoring_dir, ref_path_only))
        return old_to_new_abs.get(abs_target)

    rewritten_files = 0
    for root, _dirs, files in os.walk(target_dir):
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in _TEXT_EXTS_FOR_REWRITE:
                continue
            path = os.path.join(root, name)
            rel_to_target = os.path.relpath(path, target_dir)
            old_rel = new_to_old_rel.get(rel_to_target)
            authoring_dir = os.path.dirname(os.path.join(target_dir, old_rel)) if old_rel else root
            current_dir = root

            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except OSError:
                continue

            changed = False

            def make_sub():
                def _sub(m):
                    nonlocal changed
                    ref = m.group(1)
                    if _is_external(ref):
                        return m.group(0)
                    new_abs = resolve(ref, authoring_dir)
                    if not new_abs:
                        return m.group(0)
                    new_rel = os.path.relpath(new_abs, current_dir).replace(os.sep, '/')
                    changed = True
                    return m.group(0).replace(ref, new_rel, 1)
                return _sub

            if ext in ('.html', '.htm'):
                new_content = _HTML_REF_RE.sub(make_sub(), content)
            else:  # .css
                new_content = _CSS_URL_RE.sub(make_sub(), content)
                new_content = _CSS_IMPORT_RE.sub(make_sub(), new_content)

            if changed and new_content != content:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                rewritten_files += 1

    if rewritten_files:
        log_fn(f'[폴더 정리] 파일 {rewritten_files}개에서 링크 경로를 새 위치에 맞게 갱신했습니다.')


def _remove_empty_dirs(target_dir):
    for root, dirs, _files in os.walk(target_dir, topdown=False):
        for d in dirs:
            full = os.path.join(root, d)
            try:
                if not os.listdir(full):
                    os.rmdir(full)
            except OSError:
                pass


def organize_folder(source_dir, log_fn=lambda m: None):
    """source_dir(이미 완료된 미러링 폴더)를 정리한 사본을 만든다. 원본은
    전혀 건드리지 않고, 같은 부모 폴더 아래 '<이름>_clean' 폴더에 결과를 둔다.
    반환: 새로 만들어진 정리본 폴더의 절대 경로."""
    source_dir = os.path.abspath(source_dir)
    parent = os.path.dirname(source_dir)
    base_name = os.path.basename(source_dir.rstrip(os.sep)) or 'site'
    target_dir = os.path.join(parent, f'{base_name}_clean')
    suffix = 2
    while os.path.exists(target_dir):
        target_dir = os.path.join(parent, f'{base_name}_clean{suffix}')
        suffix += 1

    log_fn(f'[폴더 정리] 정리된 사본을 만드는 중: {target_dir}')
    shutil.copytree(source_dir, target_dir)

    _remove_bookkeeping(target_dir, log_fn)

    candidates = {}  # 정리 폴더 기준 상대경로 -> 카테고리
    for root, _dirs, files in os.walk(target_dir):
        for name in files:
            category = _ext_category(name)
            if not category:
                continue
            rel = os.path.relpath(os.path.join(root, name), target_dir)
            if rel.split(os.sep)[0] in _TYPE_FOLDERS:
                continue  # 이미 분류 폴더 안에 있음(재실행 등 대비)
            candidates[rel] = category

    if not candidates:
        log_fn('[폴더 정리] 재배치할 자산 파일을 찾지 못했습니다 (이미 단순한 구조입니다).')
        return target_dir

    candidate_names = {os.path.basename(rel) for rel in candidates}
    js_referenced = _collect_js_referenced_names(target_dir, candidate_names)

    moved = {}
    skipped = 0
    for rel, category in candidates.items():
        name = os.path.basename(rel)
        if name in js_referenced:
            skipped += 1
            continue
        new_rel = _unique_target_path(target_dir, os.path.join(category, name))
        new_abs = os.path.join(target_dir, new_rel)
        os.makedirs(os.path.dirname(new_abs), exist_ok=True)
        shutil.move(os.path.join(target_dir, rel), new_abs)
        moved[rel] = new_rel

    if skipped:
        log_fn(f'[폴더 정리] {skipped}개 파일은 자바스크립트에서도 참조되고 있어 '
               '안전을 위해 옮기지 않았습니다.')

    if moved:
        _rewrite_references(target_dir, moved, log_fn)
        log_fn(f'[폴더 정리] {len(moved)}개 파일을 css/js/images/fonts 폴더로 재배치했습니다.')

    _remove_empty_dirs(target_dir)
    return target_dir
