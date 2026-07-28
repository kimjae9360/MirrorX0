"""Windows 작업 스케줄러(schtasks.exe)에 예약 크롤링 작업을 등록/해제한다.

핵심 제약: /RU, /RP 플래그는 절대 넣지 않는다. 넣으면 작업이 비대화형(S4U) 세션에서
돌아가게 되어 스마트 크롤링이 띄우는 Chrome 창이 뜰 데스크톱 자체가 없어진다.
/RU/RP를 생략하면 "사용자가 로그온한 상태에서만 실행"이 기본값이 되는데, 이게 바로
우리가 원하는 동작이다 (컴퓨터가 켜져 있고 로그인돼 있으면 앱이 꺼져 있어도 실행됨,
화면이 잠겨 있어도 문제 없음. 다만 완전히 로그오프된 상태에서는 건너뛰어진다).
"""
import os
import sys
import subprocess
from datetime import datetime

CREATE_NO_WINDOW = 0x08000000
TASK_FOLDER = 'MirrorX0'


def _launch_command(job_id):
    if getattr(sys, 'frozen', False):
        exe = sys.executable
        return f'"{exe}" --job {job_id}'
    # sys.argv[0]는 호출부가 어떤 스크립트에서 register_task()를 불렀는지에 따라
    # main.py가 아닐 수 있어 신뢰할 수 없다 (예: 별도 테스트 스크립트에서 호출한 경우).
    # scheduler_win.py는 항상 main.py와 같은 폴더에 있으므로 그 경로를 직접 계산한다.
    pythonw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'main.py')
    return f'"{pythonw}" "{script}" --job {job_id}'


def task_name(job_id):
    return f'\\{TASK_FOLDER}\\job_{job_id}'


def register_task(job):
    """job['schedule']을 바탕으로 schtasks 작업을 만들고(이미 있으면 덮어쓰고) 작업 이름을 돌려준다."""
    tr_value = _launch_command(job['id'])
    tn = task_name(job['id'])
    schedule = job['schedule']

    cmd = ['schtasks', '/create', '/tn', tn, '/tr', tr_value, '/f']
    sched_type = schedule.get('type')
    if sched_type == 'once':
        # schedule['date']는 잠금 없는 ISO 형식('YYYY-MM-DD')으로 저장해두고,
        # schtasks에 넘길 때만 이 Windows가 실제로 요구하는 로캘 날짜 형식으로 바꾼다
        # (예: 한국어 Windows는 "yyyy/mm/dd"를 요구함 - 실행 시 직접 확인된 값).
        date_obj = datetime.strptime(schedule['date'], '%Y-%m-%d')
        sd_value = date_obj.strftime('%Y/%m/%d')
        cmd += ['/sc', 'once', '/sd', sd_value, '/st', schedule['at']]
    elif sched_type == 'daily':
        cmd += ['/sc', 'daily', '/st', schedule['at']]
    elif sched_type == 'weekly':
        cmd += ['/sc', 'weekly', '/d', ','.join(schedule['weekdays']), '/st', schedule['at']]
    else:
        raise ValueError(f'unknown schedule type: {sched_type!r}')

    result = subprocess.run(cmd, creationflags=CREATE_NO_WINDOW, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or 'schtasks failed').strip())
    return tn


def unregister_task(task_name_value):
    if not task_name_value:
        return
    subprocess.run(['schtasks', '/delete', '/tn', task_name_value, '/f'],
                    creationflags=CREATE_NO_WINDOW, capture_output=True, text=True)
