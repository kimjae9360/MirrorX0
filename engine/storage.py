r"""설정과 프로젝트 기록을 파일로 저장하고 불러오는 부분.

저장 위치는 코드가 있는 폴더가 아니라 %APPDATA%\MirrorX 다.
(프로그램 폴더는 쓰기 권한이 없을 수 있고, exe로 묶으면 임시 폴더가 되기 때문)

    settings.json   환경설정 (연결 수, API 키, 언어 등)
    projects.json   받았던 사이트 기록
    previews/       완료된 사이트의 썸네일
"""
import os
import json
import shutil
import hashlib

# 디스크 여유 공간 기준(MB). WARN 밑으로 떨어지면 경고만, CRITICAL 밑으로
# 떨어지면 (아직 시작 전이면) 시작을 막고 (진행 중이면) 크롤링을 멈춘다 -
# 디스크가 완전히 꽉 차면 파일 쓰기 중 손상/충돌로 이어질 수 있어서다.
DISK_WARN_MB = 1024
DISK_CRITICAL_MB = 200


def check_disk_space(path):
    """path가 위치할 드라이브의 남은 용량(MB)을 확인한다. path 자체가 아직
    없어도(받기 전 폴더 등) 존재하는 상위 폴더를 찾아 그 드라이브를 본다.
    반환: (free_mb: float, status: 'ok'|'warn'|'critical')"""
    probe = os.path.abspath(path)
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    if not probe or not os.path.exists(probe):
        probe = os.path.abspath(os.sep)

    usage = shutil.disk_usage(probe)
    free_mb = usage.free / (1024 * 1024)
    if free_mb < DISK_CRITICAL_MB:
        status = 'critical'
    elif free_mb < DISK_WARN_MB:
        status = 'warn'
    else:
        status = 'ok'
    return free_mb, status

CONFIG_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'MirrorX')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'settings.json')

DEFAULT_SETTINGS = {
    'base_path': os.path.join(os.path.expanduser('~'), 'Downloads', 'MirrorX'),
    'user_agent': '',
    'connections': 8,
    'retries': 1,
    'timeout': 30,
    'max_rate': 0,   # 0 = 무제한
    'robots': '2',   # 0=무시, 1=가능하면 준수, 2=항상 준수
    'proxy': '',
    'external_links': False,  # 링크로 연결된 외부 사이트의 파일도 1단계 받아올지
    'language': 'en',  # UI 언어. 기본값은 영어, 환경설정에서 한국어로 변경 가능
    # --- 고급 (환경설정 > 고급) ---
    'referer': '',
    'lang_header': '',
    'custom_headers': '',
    'cookies_file': '',
    'link_format': 'relative',  # relative(기본, 플래그 없음) / absolute(-K) / original(-K4)
    'near_files': False,
    'conn_per_sec': 0,  # 0 = HTTrack 기본값(초당 5개) 그대로 사용
    'warc': False,
    'search_index': False,
    # --- AI 크롤링 ---
    'ai_provider': 'ollama',  # 'ollama'(기본, 무료·로컬) | 'anthropic' | 'openai' | 'gemini'
    'nav_collapsed': False,   # 좌측 내비게이션 접힘 상태(다음 실행에도 유지)
    'anthropic_api_key': '',
    'openai_api_key': '',
    'gemini_api_key': '',
    'use_local_cookies': False,  # 로컬 브라우저 쿠키 연동 (안티봇 우회용)
}


def init_defaults(defaults):
    """예전에는 main.py가 기본값을 갖고 있어서 여기에 등록해줘야 했다.
    지금은 DEFAULT_SETTINGS가 이 모듈에 있으므로 아무것도 하지 않는다
    (호출부를 한 번에 다 고치지 않아도 되게 남겨둔 자리)."""


def load_settings():
    settings = DEFAULT_SETTINGS.copy()
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                settings.update(json.load(f))
    except Exception:
        pass
    return settings


def save_settings(settings):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def get_active_ai_config(settings):
    """settings에 저장된 선택된 AI 프로바이더와 그에 맞는 API 키를 하나로 묶어서 돌려준다.
    기본 프로바이더는 ollama(로컬/무료, API 키 불필요)다."""
    provider = settings.get('ai_provider', 'ollama')
    key_field = {'ollama': None, 'anthropic': 'anthropic_api_key', 'openai': 'openai_api_key',
                 'gemini': 'gemini_api_key'}.get(provider, 'anthropic_api_key')
    return {'provider': provider, 'api_key': settings.get(key_field, '') if key_field else ''}


def ai_ready(ai_config):
    """ollama는 API 키 없이 로컬에서 동작하므로 프로바이더가 ollama면 항상 준비된 것으로 본다.
    다른 프로바이더는 API 키가 있어야 준비된 것으로 본다."""
    return ai_config.get('provider') == 'ollama' or bool(ai_config.get('api_key'))


PROJECTS_FILE = os.path.join(CONFIG_DIR, 'projects.json')


def load_projects():
    try:
        if os.path.exists(PROJECTS_FILE):
            with open(PROJECTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return []


def save_projects(projects):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(PROJECTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(projects, f, ensure_ascii=False, indent=2)


def preview_path_for(name, base_path):
    """프로젝트는 안정적인 id가 없고 (name, base_path) 조합으로 식별되므로,
    그 조합을 해시해서 파일 시스템에 안전한 미리보기 파일 경로를 만든다."""
    key_hash = hashlib.md5(f'{name}|{base_path}'.encode('utf-8')).hexdigest()
    return os.path.join(CONFIG_DIR, 'previews', f'{key_hash}.png')


def upsert_project(projects, record):
    """(name, base_path) 조합을 키로 기존 항목을 갱신하거나 새로 추가한다."""
    key = (record['name'], record['base_path'])
    for i, existing in enumerate(projects):
        if (existing['name'], existing['base_path']) == key:
            record['created_at'] = existing.get('created_at', record['created_at'])
            projects[i] = record
            return projects
    projects.append(record)
    return projects

