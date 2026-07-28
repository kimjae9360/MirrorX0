r"""설정과 프로젝트 기록을 파일로 저장하고 불러오는 부분.

저장 위치는 코드가 있는 폴더가 아니라 %APPDATA%\MirrorX 다.
(프로그램 폴더는 쓰기 권한이 없을 수 있고, exe로 묶으면 임시 폴더가 되기 때문)

    settings.json   환경설정 (연결 수, API 키, 언어 등)
    projects.json   받았던 사이트 기록
    previews/       완료된 사이트의 썸네일
"""
import os
import json
import hashlib

CONFIG_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'MirrorX')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'settings.json')

DEFAULT_SETTINGS = None   # main.py가 채워 넣는다 (아래 init_defaults 참고)


def init_defaults(defaults):
    """main.py가 갖고 있는 기본 설정값을 여기에 등록한다."""
    global DEFAULT_SETTINGS
    DEFAULT_SETTINGS = defaults


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
    """settings에 저장된 선택된 AI 프로바이더와 그에 맞는 API 키를 하나로 묶어서 돌려준다."""
    provider = settings.get('ai_provider', 'anthropic')
    key_field = {'anthropic': 'anthropic_api_key', 'openai': 'openai_api_key', 'gemini': 'gemini_api_key'}.get(
        provider, 'anthropic_api_key')
    return {'provider': provider, 'api_key': settings.get(key_field, '')}


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

