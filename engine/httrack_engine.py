"""HTTrack 엔진을 다루는 부분 - 명령 조립, 실행, 진행률 읽기, 쿠키 준비.

여기에는 화면(위젯) 코드가 전혀 없다. 그래서 GUI로 실행할 때와
예약 작업이 창 없이 실행할 때가 같은 코드를 그대로 쓴다.

흐름:
    build_httrack_cmd(...)  설정값 -> httrack.exe 명령줄 인자 리스트
    run_httrack(cmd, ...)   실행하면서 출력을 한 줄씩 읽어 콜백으로 넘김
    parse_dashboard_line()  HTTrack이 뿌리는 진행 상황 한 줄을 숫자로 해석
"""
import os
import re
import sys
import time
import locale
import subprocess

from i18n import t
from storage import CONFIG_DIR


# 실행 파일이 있는 경로 확인 (PyInstaller 환경 대응)
if getattr(sys, 'frozen', False):
    application_path = sys._MEIPASS
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

# 내장된 HTTrack 엔진 경로
HTTRACK_EXE = os.path.join(application_path, "httrack", "httrack.exe")

# httrack --help 기준 매핑
#  '2' 페이지 안의 모든 사이트 = --mirrorlinks (-Y)
#  '3' 개별 파일 얻기 = --get-files (-g), 자체적으로 depth=0을 강제함
#  '4' 기존 다운로드 업데이트 = --update (-iC2)
#  '5' 중단된 다운로드 이어받기 = --continue (-iC1)
ACTION_FLAGS = {'1': '', '2': '-Y', '3': '-g', '4': '-iC2', '5': '-iC1'}

DEFAULT_FILTERS = '+*.png +*.gif +*.jpg +*.jpeg +*.css +*.js -ad.doubleclick.net/* -mime:application/foobar'

# 항상 붙는 기본 규칙 (광고/알 수 없는 mime 제외) — 체크박스에서 관리하지 않는 부분
BASE_FILTER_RULES = ['-ad.doubleclick.net/*', '-mime:application/foobar']

# 한글 윈도우 등에서 HTTrack이 출력하는 OS 레벨 오류 메시지(winsock 에러 등)는
# UTF-8이 아니라 시스템 ANSI 코드페이지(cp949 등)로 나오므로 이에 맞춰 디코딩해야
# 한글이 깨지지 않는다.
SUBPROCESS_ENCODING = locale.getpreferredencoding(False)

# HTTrack의 실시간 대시보드(-%v)는 ANSI 커서 이동 코드로 화면을 다시 그리는 방식이라
# 이를 파싱해서 진행률 UI에 반영한다.
ANSI_RE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
STAT_PATTERNS = {
    'bytes_saved': re.compile(r'Bytes saved:\s*([^\t\r\n]+)'),
    'links_scanned': re.compile(r'Links scanned:\s*(\d+)/(\d+)\s*\(\+(\d+)\)'),
    'files_written': re.compile(r'Files written:\s*(\d+)'),
    'transfer_rate': re.compile(r'Transfer rate:\s*([^\t\r\n(]+)'),
    'errors': re.compile(r'Errors:\s*(\d+)'),
    'current_job': re.compile(r'Current job:\s*(.+)'),
    'elapsed_time': re.compile(r'Time:\s*([^\t\r\n]+)'),
}
# 텍스트 로그에 찍히는 "HH:MM:SS  Error: ..." 형태의 오류 라인 감지용
# (대시보드의 Errors 카운터가 프로세스 종료 직전에 갱신되지 않는 경우의 보완책)
PLAIN_ERROR_RE = re.compile(r'\bError:\s')


def existing_mirror_kind(out_dir):
    """이미 받아둔 미러가 있는지 HTTrack이 남긴 흔적으로 판별한다.
    'interrupted' - 받다가 끊긴 미러 (진행 중 lock 파일이 남아 있음) → 이어받기가 맞다
    'complete'    - 한 번 다 받은 미러 (hts-cache에 이전 상태가 있음) → 변경분만 받으면 된다
    None          - 처음 받는 곳
    """
    if not os.path.isdir(out_dir):
        return None
    if os.path.exists(os.path.join(out_dir, 'hts-in_progress.lock')):
        return 'interrupted'
    if os.path.isdir(os.path.join(out_dir, 'hts-cache')):
        return 'complete'
    return None


def cookie_domains_for(urls):
    """대상 URL들의 호스트와 그 상위 도메인만 모은다.
    (예: blog.site.com -> {'blog.site.com', 'site.com'})"""
    from urllib.parse import urlparse
    domains = set()
    for raw in urls:
        raw = (raw or '').strip()
        if not raw:
            continue
        host = urlparse(raw if '://' in raw else 'http://' + raw).hostname or ''
        parts = [p for p in host.split('.') if p]
        # 마지막 두 조각(example.com)까지만 올라간다 - 더 올라가면 'com' 같은
        # TLD가 되어 관계없는 사이트까지 다 걸리게 된다.
        for i in range(max(1, len(parts) - 1)):
            domains.add('.'.join(parts[i:]))
    return domains


def export_local_cookies(urls, out_path):
    """로컬 브라우저 쿠키 중 '지금 받으려는 사이트 것만' 골라 Netscape cookies.txt로 쓴다.

    browser_cookie3.load()는 모든 사이트의 쿠키를 다 돌려주므로 그대로 쓰면 안 된다.
    관계없는 사이트(메일·은행 등)의 세션 쿠키까지 대상 서버로 보내게 되고 파일에도
    남기 때문이다. 반드시 대상 도메인으로 걸러서 내보낸다.
    반환: (성공 여부, 사용자에게 보여줄 메시지)"""
    try:
        import browser_cookie3
    except ImportError:
        return False, t('warn_cookie_lib_missing')
    try:
        jar = browser_cookie3.load()
    except Exception as e:
        return False, t('warn_cookie_read_failed', e=e)

    wanted = cookie_domains_for(urls)
    rows = []
    for c in jar:
        bare = (c.domain or '').lstrip('.')
        if bare not in wanted:
            continue
        # Netscape 형식: domain / include_subdomains / path / secure / expiry / name / value
        rows.append('\t'.join([
            c.domain or bare,
            'TRUE' if (c.domain or '').startswith('.') else 'FALSE',
            c.path or '/',
            'TRUE' if c.secure else 'FALSE',
            str(int(c.expires)) if c.expires else '0',
            c.name or '', c.value or '',
        ]))

    if not rows:
        return False, t('warn_cookie_none_matched')

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('# Netscape HTTP Cookie File\n')
        f.write('# MirrorX0가 생성했습니다. 대상 사이트 쿠키만 들어 있습니다.\n\n')
        f.write('\n'.join(rows) + '\n')
    return True, t('log_cookie_exported', n=len(rows))


def build_httrack_cmd(urls, out_dir, action_code, depth, filters, settings, safety=None, scope=None,
                      log_fn=None):
    """위젯 상태 없이 HTTrack cmd 리스트만 조립한다. safety는 매 작업마다 바뀌는
    안전장치 값들: {'pause': (min,max)|None, 'maxtime_hours': float|None,
    'maxsize_mb': int|None, 'hostcontrol': 'none'|'timeout'|'slow'|'both'}.
    scope는 AI 없이 결정론적으로 다운로드 경계를 규정하는 값들:
    {'same_folder': bool, 'domain_scope': 'host'|'subdomain'}."""
    safety = safety or {}
    scope = scope or {}
    cmd = [HTTRACK_EXE]
    if urls:
        os.makedirs(out_dir, exist_ok=True)
        # --- 로컬 브라우저 로그인(쿠키) 사용 ---
        # 받은 사이트 폴더가 아니라 설정 폴더에 쓴다 - 결과 폴더는 사용자가 그대로
        # 공유하거나 올릴 수 있는 곳이라 세션 쿠키를 거기에 남기면 안 된다.
        if settings.get('use_local_cookies'):
            cookie_path = os.path.join(CONFIG_DIR, 'session_cookies.txt')
            ok, message = export_local_cookies(urls, cookie_path)
            if log_fn:
                log_fn(message)
            if ok:
                # -%K(--cookies-file)가 파일 경로를 받는 옵션이다. -b는 '쿠키를 받을지
                # 말지(0/1)'라서 경로를 주면 HTTrack이 그 경로를 URL로 해석해버린다.
                cmd.extend(['-%K', cookie_path])
        urls_file = os.path.join(out_dir, 'mirrorx0_urls.txt')
        with open(urls_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(urls))
        cmd.extend(['-%L', urls_file])
    cmd.extend(['-O', out_dir])

    if ACTION_FLAGS.get(action_code):
        cmd.append(ACTION_FLAGS[action_code])

    # '-g' 개별 파일 모드는 depth=0을 강제하므로 덮어쓰지 않음.
    # depth가 None이면 -r 플래그 자체를 안 붙여서 HTTrack의 기본값(무제한)을 그대로 쓴다.
    if action_code != '3' and depth is not None:
        cmd.append(f'-r{depth}')

    # 시작 주소와 같은 폴더 밖으로 못 나가게 (--stay-on-same-dir) - 거대한 사이트의
    # 한 섹션만 원할 때 depth 숫자보다 훨씬 확실한 경계.
    if scope.get('same_folder'):
        cmd.append('-S')
    # 서브도메인까지 포함할지 (--stay-on-same-domain). 기본(host)은 HTTrack 자체
    # 기본값(-a, 같은 호스트만)을 그대로 쓰므로 플래그를 안 붙인다.
    if scope.get('domain_scope') == 'subdomain':
        cmd.append('-d')

    cmd.extend(filters)

    cmd.append(f'-c{int(settings["connections"])}')
    cmd.append(f'-R{int(settings["retries"])}')
    cmd.append(f'-T{int(settings["timeout"])}')
    if int(settings['max_rate']):
        cmd.append(f'-A{int(settings["max_rate"])}')
    cmd.append(f'-s{settings["robots"]}')
    if settings.get('external_links'):
        cmd.append('-%e1')  # 링크로 이어지는 외부 사이트도 1단계 받기 (--ext-depth)
    if settings['user_agent']:
        cmd.extend(['-F', settings['user_agent']])
    if settings['proxy']:
        cmd.extend(['-P', settings['proxy']])

    # --- 안전장치 (매 작업마다 조절하는 값) ---
    if safety.get('pause'):
        p_min, p_max = safety['pause']
        cmd.append(f'-%G{p_min}:{p_max}')  # --pause: 요청 사이 무작위 텀
    if safety.get('maxtime_hours'):
        cmd.append(f'-E{int(float(safety["maxtime_hours"]) * 3600)}')  # --max-time
    if safety.get('maxsize_mb'):
        cmd.append(f'-M{int(safety["maxsize_mb"]) * 1024 * 1024}')  # --max-size
    hostcontrol_flag = {'none': None, 'timeout': '1', 'slow': '2', 'both': '3'}.get(
        safety.get('hostcontrol', 'none'))
    if hostcontrol_flag:
        cmd.append(f'-H{hostcontrol_flag}')  # --host-control

    # --- 고급 (환경설정에서 온 값들) ---
    if settings.get('referer'):
        cmd.extend(['-%R', settings['referer']])
    if settings.get('lang_header'):
        cmd.extend(['-%l', settings['lang_header']])
    for header_line in settings.get('custom_headers', '').splitlines():
        header_line = header_line.strip()
        if header_line:
            cmd.extend(['-%X', header_line])
    if settings.get('cookies_file'):
        cmd.extend(['-%K', settings['cookies_file']])
    link_format = settings.get('link_format', 'relative')
    if link_format == 'absolute':
        cmd.append('-K')
    elif link_format == 'original':
        cmd.append('-K4')
    if settings.get('near_files'):
        cmd.append('-n')
    if int(settings.get('conn_per_sec', 0) or 0):
        cmd.append(f'-%c{int(settings["conn_per_sec"])}')
    if settings.get('warc'):
        cmd.append('-%r')
    if settings.get('search_index'):
        cmd.append('-%I')

    cmd.append('-v')    # 로그를 화면(stdout)에 실시간 출력 (--verbose)
    cmd.append('-q')    # 확인 질문 없이 진행 (--quiet), non-interactive 실행에 필수
    cmd.append('-%v')   # 실시간 진행률 대시보드 출력 (--display) -> 진행률 UI에 사용
    return cmd


def parse_dashboard_line(raw_line, state, on_progress):
    """ANSI 이스케이프로 그려지는 HTTrack 실시간 대시보드(-%v) 한 줄을 파싱해 state를 갱신하고,
    'Current job' 프레임이 나올 때마다(초당 수십 번이 아니라 ~0.3초에 한 번) on_progress로 알린다."""
    clean = ANSI_RE.sub('', raw_line)

    m = STAT_PATTERNS['links_scanned'].search(clean)
    if m:
        state['links_done'] = int(m.group(1))
        state['links_total'] = int(m.group(2))

    m = STAT_PATTERNS['files_written'].search(clean)
    if m:
        state['files_written'] = int(m.group(1))

    m = STAT_PATTERNS['bytes_saved'].search(clean)
    if m:
        state['bytes_saved'] = m.group(1).strip()

    m = STAT_PATTERNS['transfer_rate'].search(clean)
    if m:
        state['transfer_rate'] = m.group(1).strip()

    m = STAT_PATTERNS['elapsed_time'].search(clean)
    if m:
        state['elapsed_time'] = m.group(1).strip()

    m = STAT_PATTERNS['errors'].search(clean)
    if m:
        state['errors'] = int(m.group(1))

    m = STAT_PATTERNS['current_job'].search(clean)
    if m:
        state['current_job'] = m.group(1).strip()
        now = time.monotonic()
        if now - state['last_update'] > 0.3:
            state['last_update'] = now
            on_progress(dict(state))


def run_httrack(cmd, on_log, on_progress, on_done, on_process=None):
    """cmd를 실행하고 stdout을 실시간으로 읽어 콜백으로 전달한다. GUI 스레드와 헤드리스
    예약 작업 양쪽에서 공용으로 쓴다 (GUI는 콜백 안에서 큐에 담고, 헤드리스는 로그 파일에 쓴다)."""
    try:
        CREATE_NO_WINDOW = 0x08000000
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding=SUBPROCESS_ENCODING,
            errors='replace',
            creationflags=CREATE_NO_WINDOW
        )
        if on_process:
            on_process(proc)

        local_state = {'last_update': 0.0}
        plain_errors = 0

        for line in iter(proc.stdout.readline, ''):
            if not line:
                continue
            if '\x1b' in line:
                # ANSI 이스케이프가 섞인 줄 = 실시간 대시보드 갱신 프레임
                # (그대로 로그에 찍으면 제어문자가 그대로 노출되므로 파싱만 함)
                parse_dashboard_line(line, local_state, on_progress)
            else:
                line_str = line.strip()
                if line_str:
                    on_log(line_str)
                    if PLAIN_ERROR_RE.search(line_str):
                        # 대시보드의 Errors 카운터가 프로세스 종료 전에 마지막으로
                        # 갱신되지 않는 경우가 있어, 텍스트 로그의 "Error:" 라인도
                        # 별도로 세어 완료 판정에 사용한다.
                        plain_errors += 1
                        local_state['plain_errors'] = plain_errors

        proc.stdout.close()
        return_code = proc.wait()
        engine_errors = max(local_state.get('errors', 0), plain_errors)
        on_done(return_code, engine_errors)
    except Exception as e:
        on_done(str(e), 0)

