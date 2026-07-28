"""예약 크롤링 작업(jobs.json) 저장/관리.

CONFIG_DIR(main.py와 동일한 %APPDATA%\\MirrorX)을 인자로 받아서, GUI 프로세스와
헤드리스 예약 실행 프로세스(main.py --job <id>)가 같은 파일을 안전하게 공유한다.
"""
import os
import json
import uuid
from datetime import datetime


def jobs_file_path(config_dir):
    return os.path.join(config_dir, 'jobs.json')


def load_jobs(config_dir):
    path = jobs_file_path(config_dir)
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return []


def save_jobs(config_dir, jobs):
    os.makedirs(config_dir, exist_ok=True)
    with open(jobs_file_path(config_dir), 'w', encoding='utf-8') as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)


def find_job(jobs, job_id):
    return next((j for j in jobs if j['id'] == job_id), None)


def new_job(name, urls, save_path, mode, httrack_opts, smart_opts, schedule, ai_extract=None):
    now = datetime.now().isoformat()
    return {
        'id': str(uuid.uuid4()),
        'name': name,
        'enabled': True,
        'urls': urls,
        'save_path': save_path,
        'mode': mode,               # 'httrack' | 'smart' | 'both'
        'httrack': httrack_opts,     # {'action','depth','filters'}
        'smart': smart_opts,         # {'wait_until','max_pages'}
        'schedule': schedule,        # {'type','at','date','weekdays'}
        # 크롤링 방식과 무관하게, 저장된 폴더의 .html 파일들에 대해 동작하는 후처리 단계.
        'ai_extract': ai_extract or {'enabled': False, 'instruction': '', 'fields': [], 'export_formats': ['csv']},
        'scheduler_task_name': None,
        'last_run_at': None,
        'last_status': 'never_run',
        'last_log_path': None,
        'created_at': now,
        'updated_at': now,
    }


def upsert_job(jobs, job):
    for i, existing in enumerate(jobs):
        if existing['id'] == job['id']:
            job['created_at'] = existing.get('created_at', job.get('created_at'))
            jobs[i] = job
            return jobs
    jobs.append(job)
    return jobs


def remove_job(jobs, job_id):
    return [j for j in jobs if j['id'] != job_id]
