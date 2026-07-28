# -*- mode: python ; coding: utf-8 -*-

# httrack/ 폴더는 datas가 아니라 COLLECT가 끝난 뒤 별도로 복사한다 (아래 참고).
# PyInstaller의 Analysis가 datas 안에 있는 .exe/.dll(httrack.exe, msvcr90.dll,
# mfc90.dll 등, VC++2008 시절 런타임)을 실제 바이너리로 인식해 그 의존성을
# _internal 최상위로 끌어올리는데(binary vs data reclassification), 이게 우리
# 앱 자신의 tcl/tk(_tkinter) 런타임과 충돌해서 실행 즉시
# "Microsoft Visual C++ Runtime Library: R6034 - An application has made an
# attempt to load the C runtime library incorrectly" 크래시가 나는 것을 확인함.
# datas에서 빼고 빌드 후 순수 파일 복사로 넣으면 Analysis가 아예 건드리지
# 않아서 충돌이 사라진다.

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['playwright.sync_api'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MirrorX_HTTrack',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='MirrorX_HTTrack',
)

# --- httrack 엔진을 Analysis 밖에서 순수 파일 복사로 배치 ---
import os
import shutil

_httrack_src = os.path.join(SPECPATH, 'httrack')
_httrack_dst = os.path.join(DISTPATH, 'MirrorX_HTTrack', '_internal', 'httrack')
if os.path.isdir(_httrack_dst):
    shutil.rmtree(_httrack_dst)
shutil.copytree(_httrack_src, _httrack_dst)

# --- Playwright driver를 같은 이유로 Analysis 밖에서 순수 파일 복사로 배치 ---
# Playwright는 node.exe + cli.js로 된 Node 드라이버를 서브프로세스로 띄우는 방식이라
# httrack.exe와 마찬가지로 자체 런타임 바이너리를 포함한다 (동일한 R6034 충돌 위험).
# playwright._impl._driver.compute_driver_executable()가
# Path(inspect.getfile(playwright)).parent / "driver" 로 경로를 계산하므로,
# PyInstaller가 frozen 상태에서 playwright 패키지의 __file__을 잡아주는 위치
# (_internal/playwright/) 바로 아래에 driver 폴더를 두면 그대로 찾아진다.
# channel='chrome'(사용자 PC의 기존 Chrome을 그대로 사용)만 쓰므로 브라우저 캐시
# (.local-browsers)는 필요 없어 제외한다.
_playwright_driver_src = os.path.join(SPECPATH, 'venv', 'Lib', 'site-packages', 'playwright', 'driver')
_playwright_driver_dst = os.path.join(DISTPATH, 'MirrorX_HTTrack', '_internal', 'playwright', 'driver')
if os.path.isdir(_playwright_driver_dst):
    shutil.rmtree(_playwright_driver_dst)
shutil.copytree(_playwright_driver_src, _playwright_driver_dst,
                 ignore=shutil.ignore_patterns('.local-browsers'))
