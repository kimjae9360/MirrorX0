"""Ollama(무료·로컬 AI)의 설치/실행/모델 상태를 확인하고, 사용자가 버튼 한 번으로
설치·실행·모델 받기를 할 수 있게 돕는다.

왜 '자동'이 아니라 '원클릭'인가:
    Ollama는 수백 MB짜리 설치 프로그램이고 시스템에 백그라운드 서비스로 상주한다.
    콤보박스에서 항목 하나 골랐다고 그런 일이 조용히 벌어지면 사용자가 놀란다.
    그래서 상태만 자동으로 감지해서 알려주고, 실제 설치·다운로드는 반드시
    사용자가 버튼을 눌렀을 때만 시작한다. (이 앱의 기존 원칙과도 같다 -
    smart_crawl/ai_extract도 '설치 방법을 안내만' 하고 몰래 설치하지 않는다.)

설치는 winget(마이크로소프트 공식 패키지 관리자)을 쓴다. 임의의 exe를 직접
내려받아 실행하는 것보다 출처가 분명하고, 서명 검증도 winget이 대신 해준다.
"""
import os
import json
import shutil
import subprocess
import urllib.error
import urllib.request

CREATE_NO_WINDOW = 0x08000000

OLLAMA_HOST = 'http://127.0.0.1:11434'
WINGET_PACKAGE_ID = 'Ollama.Ollama'
DEFAULT_MODEL = 'llama3.2'
DOWNLOAD_PAGE = 'https://ollama.com/download'

# 상태 값 - UI가 이 값에 따라 어떤 버튼을 보여줄지 정한다.
NOT_INSTALLED = 'not_installed'   # 설치 자체가 안 됨
NOT_RUNNING = 'not_running'       # 설치는 됐는데 서버가 안 떠 있음
NO_MODEL = 'no_model'             # 서버는 떴는데 쓸 모델이 없음
READY = 'ready'                   # 바로 사용 가능


def _run(cmd, timeout=None):
    """콘솔 창을 띄우지 않고 명령을 실행한다(GUI 앱이라 검은 창이 뜨면 안 된다)."""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          creationflags=CREATE_NO_WINDOW)


def find_ollama_exe():
    """PATH와 표준 설치 위치에서 ollama 실행 파일을 찾는다. 없으면 None.
    winget으로 막 설치한 직후에는 현재 프로세스의 PATH에 아직 안 잡히므로,
    표준 설치 경로도 함께 본다."""
    found = shutil.which('ollama')
    if found:
        return found
    candidates = [
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Ollama', 'ollama.exe'),
        os.path.join(os.environ.get('PROGRAMFILES', ''), 'Ollama', 'ollama.exe'),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def is_server_running(timeout=2):
    """Ollama 서버(11434)가 응답하는지 확인한다."""
    try:
        with urllib.request.urlopen(f'{OLLAMA_HOST}/api/tags', timeout=timeout):
            return True
    except Exception:
        return False


def list_models(timeout=5):
    """설치된 모델 이름 목록. 서버가 안 떠 있으면 빈 리스트."""
    try:
        with urllib.request.urlopen(f'{OLLAMA_HOST}/api/tags', timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception:
        return []
    return [m.get('name', '') for m in data.get('models', [])]


def get_status():
    """지금 Ollama를 바로 쓸 수 있는 상태인지 한 번에 판단한다.
    반환: (상태값, 모델 목록)"""
    if is_server_running():
        models = list_models()
        return (READY, models) if models else (NO_MODEL, [])
    if find_ollama_exe():
        return NOT_RUNNING, []
    return NOT_INSTALLED, []


def winget_available():
    return shutil.which('winget') is not None


def install(log_fn=lambda m: None, timeout=900):
    """winget으로 Ollama를 설치한다. 성공하면 True.
    사용자가 명시적으로 설치 버튼을 눌렀을 때만 호출되어야 한다."""
    if not winget_available():
        log_fn(f'[Ollama] winget을 찾을 수 없어 자동 설치를 할 수 없어요. '
               f'{DOWNLOAD_PAGE} 에서 직접 설치해주세요.')
        return False

    log_fn('[Ollama] 설치를 시작합니다. 수백 MB를 받으므로 몇 분 걸릴 수 있어요…')
    cmd = ['winget', 'install', '--id', WINGET_PACKAGE_ID, '--exact', '--silent',
           '--accept-package-agreements', '--accept-source-agreements']
    try:
        result = _run(cmd, timeout=timeout)
    except subprocess.TimeoutExpired:
        log_fn('[Ollama] 설치가 너무 오래 걸려 중단했어요. '
               f'{DOWNLOAD_PAGE} 에서 직접 설치해주세요.')
        return False

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or '').strip().splitlines()
        log_fn(f'[Ollama] 설치에 실패했어요: {detail[-1] if detail else result.returncode}. '
               f'{DOWNLOAD_PAGE} 에서 직접 설치해보세요.')
        return False

    log_fn('[Ollama] 설치가 끝났어요.')
    return True


def start_server(log_fn=lambda m: None):
    """설치된 Ollama 서버를 백그라운드로 띄운다. 이미 떠 있으면 True."""
    if is_server_running():
        return True
    exe = find_ollama_exe()
    if not exe:
        log_fn('[Ollama] 실행 파일을 찾지 못했어요. 먼저 설치해주세요.')
        return False
    try:
        subprocess.Popen([exe, 'serve'], creationflags=CREATE_NO_WINDOW,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        log_fn(f'[Ollama] 서버를 띄우지 못했어요: {e}')
        return False

    # 서버가 뜨는 데 잠깐 걸리므로 잠시 기다리며 확인한다.
    import time
    for _ in range(20):
        time.sleep(0.5)
        if is_server_running():
            log_fn('[Ollama] 서버가 실행됐어요.')
            return True
    log_fn('[Ollama] 서버가 아직 응답하지 않아요. 잠시 후 다시 시도해주세요.')
    return False


def pull_model(model=DEFAULT_MODEL, log_fn=lambda m: None, timeout=1800):
    """모델을 내려받는다(수 GB일 수 있음). 성공하면 True."""
    exe = find_ollama_exe()
    if not exe:
        log_fn('[Ollama] 실행 파일을 찾지 못했어요. 먼저 설치해주세요.')
        return False
    log_fn(f'[Ollama] 모델 "{model}"을(를) 받는 중입니다. 크기가 커서 오래 걸릴 수 있어요…')
    try:
        result = _run([exe, 'pull', model], timeout=timeout)
    except subprocess.TimeoutExpired:
        log_fn('[Ollama] 모델 받기가 너무 오래 걸려 중단했어요.')
        return False
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or '').strip().splitlines()
        log_fn(f'[Ollama] 모델 받기에 실패했어요: {detail[-1] if detail else result.returncode}')
        return False
    log_fn(f'[Ollama] 모델 "{model}" 준비 완료.')
    return True
