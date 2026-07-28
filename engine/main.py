import os
import sys
import re
import json
import time
import locale
import queue
import hashlib
import argparse
import subprocess
import threading
import multiprocessing
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
from datetime import datetime

import jobs as jobs_mod
import scheduler_win
import smart_crawl
import ai_extract
import ai_scope
import preview

# 실행 파일이 있는 경로 확인 (PyInstaller 환경 대응)
if getattr(sys, 'frozen', False):
    application_path = sys._MEIPASS
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

# 내장된 HTTrack 엔진 경로
HTTRACK_EXE = os.path.join(application_path, "httrack", "httrack.exe")

# 환경설정 저장 위치 (실행 파일 위치와 무관하게 항상 쓰기 가능한 사용자 폴더 사용)
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
    'ai_provider': 'anthropic',  # 'anthropic' | 'openai' | 'gemini'
    'anthropic_api_key': '',
    'openai_api_key': '',
    'gemini_api_key': '',
    'use_local_cookies': False,  # 로컬 브라우저 쿠키 연동 (안티봇 우회용)
}

# ---------------- 다국어 (영어/한국어) ----------------
# 앱 UI 언어는 기본 영어, 환경설정에서 한국어로 바꿀 수 있다.
# 언어 변경은 다음 실행부터 적용된다 (실행 중 위젯을 전부 다시 그리지 않음).
LANG_DISPLAY = {'en': 'English', 'ko': 'Korean'}

STRINGS = {
    'en': {
        'app_subtitle': 'A tool to mirror entire websites',
        'preferences_btn': '⚙ Preferences',
        'btn_start': 'Start',
        'btn_stop': 'Stop',
        'btn_cancel': 'Cancel',
        'btn_save': 'Save',
        'btn_browse': 'Browse',
        'btn_open_folder': 'Open Result Folder',
        'btn_no': 'No',
        'btn_cancel_shutdown': 'Cancel Schedule',

        'panel_project': 'Project',
        'label_project_name': 'Project Name',
        'label_save_location': 'Save Location',
        'label_action': 'Collection Method',
        'label_urls': 'URLs to download (one per line)',

        'action_1': 'Download web site(s)',
        'action_2': 'Download all sites linked from page',
        'action_3': 'Get individual files',
        'action_4': 'Update existing download',
        'action_5': 'Continue interrupted download',

        'panel_scope': 'Collection Scope',
        'scope_all': 'Entire site (large, but gets everything)',
        'scope_limit': 'Limit scope',
        'depth_label': 'How many link levels to follow',
        'depth_unit': 'levels',
        'depth_presets_label': 'Common values',
        'depth_preset_1': '1 · This page only',
        'depth_preset_3': '3 · Recommended',
        'depth_preset_5': '5',
        'depth_preset_10': '10 · Covers most sites',
        'depth_caption_limited': 'Only follows links up to the level you set. 1 means just this page; higher numbers reach further.',
        'depth_caption_unlimited': (
            "Same as HTTrack's default: follows links with no limit and downloads every page on the site. "
            "Large sites can take a long time and use a lot of space. Turn on the checkbox above only if you "
            "want to narrow the scope."
        ),
        'label_same_folder': 'Stay in the same folder as the starting address',
        'caption_same_folder': (
            'Only follows links under the same path as your starting URL. e.g. starting at '
            'site.com/book/1234/1 only downloads site.com/book/1234/* — other sections of the same big '
            'site (other books, boards, etc.) are left alone. This is the fix for '
            '"the whole site got pulled in when I only wanted one section."'
        ),
        'label_domain_scope': 'Domain Scope',
        'domain_scope_host': 'Same host only (default)',
        'domain_scope_subdomain': 'Include subdomains',
        'caption_domain_scope': (
            'Same host only never leaves the exact address you gave (e.g. www.site.com stays www.site.com). '
            'Include subdomains also follows other subdomains of the same site (e.g. blog.site.com, shop.site.com).'
        ),

        'panel_files': 'Which files should be downloaded?',
        'filter_images': 'Images (png, gif, jpg, webp, etc.)',
        'filter_style_script': 'Style / Script (css, js)',
        'filter_docs': 'Documents (pdf, doc, xlsx, hwp, etc.)',
        'filter_media': 'Video / Audio (mp4, mp3, avi, etc.)',
        'filter_archive': 'Archives (zip, rar, 7z, etc.)',
        'label_custom_rules': 'Additional rules (optional, advanced)',
        'caption_custom_rules': 'e.g. -*.pdf — add your own +(include)/-(exclude) rules. Can be left blank.',
        'label_applied_rules': 'Rules that will apply',

        'label_advanced_options': 'Advanced Options',
        'hint_tap_row': 'Tap any row below to change it.',
        'btn_done': 'Done',
        'btn_view_log': 'Activity Log',
        'title_log': 'Activity Log',
        'filters_none': 'None',
        'value_off': 'Off',
        'status_ready': 'Ready to start',
        'label_collect_mode': 'Method',

        'panel_power': 'After Completion',
        'power_none': 'Do nothing',
        'power_on_complete': 'Shut down computer when done',
        'power_after_hours': 'Shut down after set time (regardless of completion)',
        'label_hours_until_shutdown': 'Shut down after (hours)',
        'power_caption_after_hours': (
            "Once the time you set has passed, the computer will shut down whether mirroring is finished or "
            "not. Windows' own shutdown notice will appear, and you can cancel any time."
        ),
        'power_caption_on_complete': (
            'Once mirroring finishes normally (including finishing with errors), the computer will shut down '
            'after 1 minute. Pressing "Stop" yourself will cancel the shutdown.'
        ),
        'power_caption_none': 'The computer will not shut down automatically.',

        'panel_progress': 'Progress',
        'label_status': 'Status',
        'status_waiting': 'Waiting',
        'stat_elapsed': 'Elapsed Time',
        'stat_links': 'Links Scanned',
        'stat_files': 'Files Received',
        'stat_bytes': 'Data Received',
        'stat_speed': 'Transfer Speed',
        'stat_errors': 'Errors',
        'panel_log': 'Live Log',
        'job_waiting': 'Waiting (throttled)',
        'job_receiving': 'Receiving files',

        'dialog_browse_folder_title': 'Choose download folder',

        'prefs_title': 'Preferences',
        'prefs_subtitle': "Settings you rarely need to change. Set them once and they'll keep applying.",
        'section_connection': 'Connection',
        'section_speed_time': 'Speed & Time',
        'section_policy': 'Collection Policy',
        'section_network': 'Network',
        'section_language': 'Language',
        'label_user_agent': 'User-Agent',
        'caption_user_agent': "Leave blank to use HTTrack's default.",
        'label_connections': 'Concurrent Connections',
        'caption_connections': 'How many to fetch at once. Higher is faster but riskier for getting blocked.',
        'label_retries': 'Retry Count',
        'caption_retries': 'How many times to retry a failed request.',
        'label_timeout': 'Timeout (sec)',
        'caption_timeout': 'Give up on unresponsive servers after this long.',
        'label_max_rate': 'Max Speed (Byte/s)',
        'caption_max_rate': '0 = unlimited. Going too fast may get you blocked.',
        'label_robots': 'robots.txt Policy',
        'caption_robots': 'Decide whether to respect a site that blocks crawler access.',
        'robots_0': 'Ignore and collect everything',
        'robots_1': 'Follow when possible',
        'robots_2': 'Always follow (recommended)',
        'label_external_links': 'Also fetch one level into linked external sites',
        'caption_external_links': (
            "By default, only the site you specify is downloaded — links leading outside it aren't followed."
        ),
        'label_proxy': 'Proxy (host:port)',
        'caption_proxy': 'Optional. Leave blank to not use a proxy.',
        'label_use_local_cookies': 'Use my browser login',
        'caption_use_local_cookies': (
            'Reuses the login you already have in Chrome/Edge so sites that need signing in still work. '
            'Only cookies for the site you are downloading are used — nothing else is read or saved.'
        ),
        'warn_cookie_lib_missing': (
            "Browser login needs the 'browser_cookie3' package. Install it with: pip install browser_cookie3"
        ),
        'warn_cookie_read_failed': 'Could not read browser cookies: {e}',
        'warn_cookie_none_matched': 'No saved login found in your browser for this site — continuing without it.',
        'log_cookie_exported': 'Using your browser login ({n} cookie(s) for this site).',
        'mode_mirror': 'Site Mirroring',
        'mode_smart': 'Smart Crawl',
        'caption_mode_mirror': 'Downloads the whole site as static files.',
        'caption_mode_smart': 'Renders each page in a real browser first.',
        'panel_smart_options': 'Smart crawl options',
        'label_max_pages': 'Maximum pages',
        'caption_max_pages': 'Stops after this many pages. Each page opens a real browser, so it is slower.',
        'label_follow_depth': 'Follow links',
        'caption_follow_depth': 'How many link hops to follow from the starting address. 1 means the given pages only.',
        'label_wait_until': 'Wait until',
        'caption_wait_until': "'networkidle' waits for the page to settle — safest for pages that load late.",
        'summary_smart': 'Smart crawl',
        'summary_smart_value': '{pages} pages · depth {depth}',
        'warn_playwright_missing': "Smart crawl needs Playwright. Install it with: pip install playwright",
        'log_smart_started': 'Starting smart crawl…',
        'log_smart_done': 'Smart crawl finished: {n} page(s) saved.',
        'log_smart_failed': 'Smart crawl did not save anything.',
        'stat_pages': 'Pages visited',
        'status_done': 'Done',
        'status_done_errors': 'Done - {n} link(s) could not be fetched',
        'status_stopped': 'Stopped',
        'status_running': 'Working…',
        'caption_project_name': 'Folder name created under the save location.',
        'hint_need_url': 'Enter an address below to start',
        'existing_title': 'Already downloaded',
        'existing_header_complete': 'You already have a copy of this site',
        'existing_header_interrupted': 'A previous download was interrupted',
        'existing_body_complete': (
            'MirrorX0 can compare with what you already have and fetch only what changed — '
            'much faster, and it saves the site some traffic.'
        ),
        'existing_body_interrupted': (
            'The last download for this folder stopped partway. You can pick up where it left off '
            'instead of starting over.'
        ),
        'existing_update': 'Get only what changed',
        'existing_update_desc': 'Recommended. Compares with the existing copy and downloads new or updated files.',
        'existing_resume': 'Continue where it stopped',
        'existing_resume_desc': 'Recommended. Downloads only the files that were never finished.',
        'existing_fresh': 'Download everything again',
        'existing_fresh_desc': 'Ignores the existing copy and fetches the whole site from scratch.',
        'label_language': 'Language',
        'caption_language': 'Restart the app for the language change to take effect.',

        'confirm_title': 'Start mirroring?',
        'confirm_header': 'Start with these settings?',
        'summary_project_name': 'Project Name',
        'summary_save_location': 'Save Location',
        'summary_target_urls': 'Target URLs',
        'summary_action': 'Collection Method',
        'summary_scope': 'Collection Scope',
        'summary_power': 'After Completion',
        'scope_unlimited': 'No limit (entire site)',
        'scope_n_levels': '{depth} levels',
        'power_text_after_hours': 'Shut down after {hours}h',
        'power_text_on_complete': 'Shut down when done',
        'power_text_none': 'None',
        'url_count': '{n} URL(s)',

        'warn_need_url': '[Warning] Please enter at least one URL to download!',
        'warn_need_project_name': '[Warning] Please enter a project name!',
        'error_engine_missing': '[ERROR] HTTrack engine not found: {path}',
        'log_engine_init': 'Initializing HTTrack engine...',
        'log_project_folder': 'Project folder: {path}',
        'log_command': 'Running command: {cmd}',
        'log_user_stopped': 'Collection was forcibly stopped by the user.',
        'log_success': 'Mirroring completed successfully.',
        'log_done_with_errors': ('Finished. {n} link(s) could not be fetched - these are usually links that are '
                                 'already broken on the site itself (404). What was downloaded is fine.'),
        'log_done_code': 'Mirroring finished (exit code: {code})',
        'log_fatal_error': 'A fatal error occurred: {result}',
        'warn_folder_not_found': '[Warning] Could not find the folder.',
        'log_prefs_saved': 'Preferences saved.',
        'warn_shutdown_schedule_failed': '[Warning] Failed to schedule shutdown: {e}',
        'notice_shutdown_scheduled': '[Notice] {reason} — scheduled to shut down in {mins} min.',
        'notice_shutdown_cancelled': '[Notice] Scheduled shutdown was cancelled.',
        'shutdown_banner_text': '{reason} — computer will shut down in about {mins} min',
        'reason_after_hours': 'Scheduled shutdown after set time',
        'reason_on_complete': 'Scheduled shutdown after mirroring finished',

        'panel_safety': 'Safety Options',
        'safety_pause_enable': 'Pause between requests',
        'safety_pause_caption': (
            'Waits a random amount of time between each request. Slower, but much gentler on the '
            'target site — lowers the chance of getting blocked.'
        ),
        'safety_pause_between': 'Wait between',
        'safety_pause_and': 'and',
        'safety_pause_unit': 'sec',
        'safety_maxtime_enable': 'Limit total run time',
        'safety_maxtime_label': 'Stop after (hours)',
        'safety_maxtime_caption': 'Mirroring stops automatically once this many hours have passed, finished or not.',
        'safety_maxsize_enable': 'Limit total size',
        'safety_maxsize_label': 'Stop after (MB)',
        'safety_maxsize_caption': 'Mirroring stops automatically once this much data has been downloaded.',
        'safety_hostcontrol_label': 'Give up on slow hosts',
        'hostcontrol_none': "Don't give up",
        'hostcontrol_timeout': 'On timeout',
        'hostcontrol_slow': 'When slow',
        'hostcontrol_both': 'On timeout or when slow',
        'safety_hostcontrol_caption': 'Stops trying a host early if it keeps timing out or responds too slowly.',
        'btn_load_url_file': 'Load from file',
        'dialog_load_url_file_title': 'Choose a text file with one URL per line',
        'log_loaded_urls': '{n} URL(s) loaded from file.',
        'warn_url_file_failed': '[Warning] Could not read the file: {e}',

        'section_advanced': 'Advanced',
        'label_referer': 'Referer header',
        'caption_referer': 'Optional. Sent as the Referer header on every request.',
        'label_lang_header': 'Preferred language header',
        'caption_lang_header': (
            "Sent to sites as the Accept-Language header (e.g. \"ko, en\") — separate from this app's "
            'own display language.'
        ),
        'label_custom_headers': 'Custom HTTP headers',
        'caption_custom_headers': 'One per line, as "Header-Name: value". Leave blank if not needed.',
        'label_cookies_file': 'Cookies file',
        'caption_cookies_file': "Optional. A Netscape-format cookies.txt, useful for sites that need a login.",
        'dialog_cookies_file_title': 'Choose a cookies.txt file',
        'label_link_format': 'Link format in saved pages',
        'link_format_relative': 'Relative (default)',
        'link_format_absolute': 'Absolute',
        'link_format_original': 'Keep original',
        'caption_link_format': 'How links between downloaded pages are rewritten.',
        'label_near_files': 'Also fetch related files just outside the site',
        'caption_near_files': 'e.g. an image hosted on a different subdomain but linked from a saved page.',
        'label_conn_per_sec': 'New connections per second',
        'caption_conn_per_sec': 'Caps how quickly new connections are opened, regardless of the total count above.',
        'label_warc': 'Also save a WARC archive',
        'caption_warc': 'Writes a standard .warc file alongside the regular mirror, for archival tools.',
        'label_search_index': 'Build a search index',
        'caption_search_index': 'Generates a simple search index for the downloaded pages.',

        'tab_schedule': 'Smart Crawl',
        'nav_home': 'Home',
        'nav_preferences': 'Preferences',
        'dashboard_greeting': "Here's a quick look at everything MirrorX0 has done.",
        'section_overview': 'Overview',
        'metric_total_projects': 'Total Projects',
        'metric_total_size': 'Total Downloaded',
        'metric_success_rate': 'Success Rate',
        'metric_activity': 'Recent Activity',
        'metric_scheduled': 'Scheduled Jobs',
        'caption_success_rate': '{success} success · {errors} error(s)',
        'panel_recent_previews': 'Recent Downloads',
        'label_no_previews': "Nothing downloaded yet — start a mirror to see it here.",
        'panel_schedule_list': 'Smart Crawl Jobs',
        'caption_schedule_list': (
            'Runs automatically at the time you set, even while MirrorX0 is closed — as long as the '
            'computer is on and you are logged in (a locked screen is fine).'
        ),
        'label_no_jobs': "You haven't set up a smart crawl yet.",
        'btn_new_job': 'New Smart Crawl',
        'btn_edit_job': 'Edit',
        'btn_delete_job': 'Delete',
        'job_mode_httrack': 'Regular (HTTrack)',
        'job_mode_smart': 'Smart (browser-rendered)',
        'job_mode_both': 'Both',
        'schedule_type_once': 'Once',
        'schedule_type_daily': 'Daily',
        'schedule_type_weekly': 'Weekly',
        'job_status_never_run': 'Not run yet',
        'job_status_running': 'Running',
        'job_status_success': 'Done',
        'job_status_errors': 'Done with errors',
        'job_status_error': 'Failed',
        'dialog_job_title': 'Scheduled Job',
        'label_job_name': 'Job Name',
        'label_job_mode': 'Crawl Mode',
        'label_schedule_type': 'Repeat',
        'label_schedule_time': 'Time',
        'label_schedule_date': 'Date (YYYY-MM-DD) — used for "Once"',
        'label_schedule_weekdays': 'Days of week — used for "Weekly"',
        'weekday_mon': 'Mon', 'weekday_tue': 'Tue', 'weekday_wed': 'Wed', 'weekday_thu': 'Thu',
        'weekday_fri': 'Fri', 'weekday_sat': 'Sat', 'weekday_sun': 'Sun',
        'caption_schedule_note': (
            'The computer must be on and you must be logged in for this to run — a locked screen is fine.'
        ),
        'warn_job_need_name': '[Warning] Please enter a job name!',
        'warn_job_need_url': '[Warning] Please enter at least one URL!',
        'warn_job_need_date': '[Warning] Please enter a date for a one-time job!',
        'warn_job_invalid_date': '[Warning] Date must be in YYYY-MM-DD format!',
        'log_job_saved': 'Scheduled job saved.',
        'log_job_deleted': 'Scheduled job deleted.',
        'warn_job_schedule_failed': '[Warning] Could not register the scheduled task: {e}',

        'section_ai': 'AI Crawling',
        'label_ai_provider': 'AI Provider',
        'caption_ai_provider': 'Which AI is used for field suggestions and data extraction.',
        'label_api_key_anthropic': 'Anthropic API Key',
        'label_api_key_openai': 'OpenAI API Key',
        'label_api_key_gemini': 'Google Gemini API Key',
        'caption_api_key': (
            'Used for AI-powered data extraction. Stored only on this computer and sent only to the '
            'provider you chose above.'
        ),
        'label_ai_extract_enable': 'Extract data with AI',
        'label_ai_instruction': 'What should be extracted?',
        'caption_ai_instruction': 'Describe it in a sentence, e.g. "product name, price, and review count".',
        'btn_propose_fields': 'Suggest Fields',
        'label_extract_fields': 'Fields to extract',
        'field_col_name': 'Field name',
        'field_col_label': 'Label',
        'field_col_type': 'Type',
        'btn_add_field': '+ Add Field',
        'label_export_formats': 'Export as',
        'btn_run_extraction': 'Run Extraction',
        'dialog_ai_extract_title': 'AI Data Extraction',
        'btn_ai_extract': 'AI Extract',
        'warn_need_api_key': '[Warning] Please set your Anthropic API key in Preferences first!',
        'warn_need_instruction': '[Warning] Please describe what to extract!',
        'warn_need_sample_page': '[Warning] Could not fetch a sample page to suggest fields from.',
        'warn_propose_failed': '[Warning] Could not suggest fields: {e}',
        'log_fields_proposed': '{n} field(s) suggested.',
        'warn_need_fields': '[Warning] Please add at least one field to extract!',
        'log_ai_extract_started': 'Starting AI extraction...',
        'warn_ai_skip_no_key': '[AI Extraction] Skipped — no API key set.',

        'btn_ai_scope_rules': 'AI Rule Suggestions',
        'dialog_ai_scope_title': 'AI Download Scope Rules',
        'label_scope_goal': 'What do you want to download?',
        'caption_scope_goal': 'Describe it in a sentence, e.g. "Only the recipe section, skip login/cart pages".',
        'btn_get_scope_rules': 'Suggest Rules',
        'caption_scope_cost': (
            'Looks at a small sample of links from your starting address(es), then suggests rules with a '
            "single AI call — the cost doesn't grow with site size."
        ),
        'label_proposed_rules': 'Suggested rules (you can edit before applying)',
        'btn_apply_rules': 'Apply',
        'warn_scope_need_goal': '[Warning] Please describe what you want to download!',
        'warn_scope_need_url': '[Warning] Please enter at least one URL first!',
        'log_fetching_link_sample': 'Fetching a link sample...',
        'warn_scope_no_links': '[Warning] Could not find any links to analyze.',
        'warn_scope_failed': '[Warning] Could not get rule suggestions: {e}',
        'log_scope_rules_applied': 'AI-suggested rules applied.',

        'panel_recent_projects': 'Recent Projects',
        'caption_recent_projects': 'Pick up where you left off, or start over from a past project.',
        'label_no_projects': "You haven't mirrored anything yet.",
        'btn_load_project': 'Load',
        'btn_continue_project': 'Continue',
        'btn_delete_project': 'Delete',
        'proj_status_never': 'Not run yet',
        'proj_status_running': 'Running',
        'proj_status_success': 'Done',
        'proj_status_errors': 'Done with errors',
        'proj_status_failed': 'Failed',
        'proj_url_count': '{n} URL(s)',
    },
    'ko': {
        'app_subtitle': '사이트를 통째로 담아두는 도구',
        'preferences_btn': '⚙ 환경설정',
        'btn_start': '시작',
        'btn_stop': '중지',
        'btn_cancel': '취소',
        'btn_save': '저장',
        'btn_browse': '찾아보기',
        'btn_open_folder': '결과 폴더 열기',
        'btn_no': '아니오',
        'btn_cancel_shutdown': '예약 취소',

        'panel_project': '프로젝트',
        'label_project_name': '프로젝트 이름',
        'label_save_location': '저장 위치',
        'label_action': '수집 방식',
        'label_urls': '받을 주소 (한 줄에 하나씩)',

        'action_1': '웹 사이트 다운로드',
        'action_2': '페이지 안의 모든 사이트 다운로드',
        'action_3': '개별 파일 얻기',
        'action_4': '기존 다운로드 업데이트',
        'action_5': '중단된 다운로드 이어받기',

        'panel_scope': '수집 범위',
        'scope_all': '사이트 모든 범위 (용량은 크지만 모든 자료를 받습니다)',
        'scope_limit': '받아올 범위 제한하기',
        'depth_label': '링크를 몇 단계까지 따라갈지',
        'depth_unit': '단계',
        'depth_presets_label': '자주 쓰는 값',
        'depth_preset_1': '1 · 이 페이지만',
        'depth_preset_3': '3 · 추천',
        'depth_preset_5': '5',
        'depth_preset_10': '10 · 대부분 커버',
        'depth_caption_limited': '입력한 단계까지만 링크를 따라갑니다. 1이면 지금 주소만, 숫자가 클수록 더 멀리까지 받아요.',
        'depth_caption_unlimited': (
            'HTTrack 기본값과 동일하게 제한 없이 사이트에 있는 모든 페이지를 링크를 따라가며 받습니다. '
            '사이트가 크면 시간이 오래 걸리고 용량도 커질 수 있어요. 범위를 좁히고 싶을 때만 위 체크박스를 켜세요.'
        ),
        'label_same_folder': '시작 주소와 같은 폴더 안에서만',
        'caption_same_folder': (
            '시작 주소와 같은 경로 아래에 있는 링크만 따라갑니다. 예를 들어 site.com/book/1234/1로 '
            '시작하면 site.com/book/1234/* 만 받고, 같은 큰 사이트 안의 다른 섹션(다른 책, 다른 게시판 등)은 '
            '건드리지 않아요. "한 섹션만 필요한데 사이트 전체가 받아졌다" 문제를 위한 기능이에요.'
        ),
        'label_domain_scope': '도메인 범위',
        'domain_scope_host': '같은 호스트만 (기본)',
        'domain_scope_subdomain': '서브도메인 포함',
        'caption_domain_scope': (
            '같은 호스트만은 지정한 주소를 절대 벗어나지 않습니다 (예: www.site.com이면 계속 www.site.com만). '
            '서브도메인 포함은 같은 사이트의 다른 서브도메인도 따라갑니다 (예: blog.site.com, shop.site.com).'
        ),

        'panel_files': '어떤 파일까지 받을까요?',
        'filter_images': '이미지 (png, gif, jpg, webp 등)',
        'filter_style_script': '스타일 / 스크립트 (css, js)',
        'filter_docs': '문서 (pdf, doc, xlsx, hwp 등)',
        'filter_media': '동영상 / 음악 (mp4, mp3, avi 등)',
        'filter_archive': '압축 파일 (zip, rar, 7z 등)',
        'label_custom_rules': '추가 규칙 (선택, 고급 사용자용)',
        'caption_custom_rules': '예: -*.pdf  처럼 +(포함)/-(제외) 규칙을 직접 추가할 수 있어요. 비워둬도 됩니다.',
        'label_applied_rules': '적용될 규칙',

        'label_advanced_options': '고급 옵션',
        'hint_tap_row': '아래 항목을 누르면 바로 바꿀 수 있어요.',
        'btn_done': '완료',
        'btn_view_log': '작업 로그',
        'title_log': '작업 로그',
        'filters_none': '없음',
        'value_off': '꺼짐',
        'status_ready': '시작할 준비가 됐어요',
        'label_collect_mode': '수집 방식',

        'panel_power': '완료 후 동작',
        'power_none': '아무것도 안 함',
        'power_on_complete': '완료되면 컴퓨터 종료',
        'power_after_hours': '지정한 시간 뒤 컴퓨터 종료 (완료 여부와 상관없이)',
        'label_hours_until_shutdown': '시간 뒤 종료',
        'power_caption_after_hours': (
            '지금부터 입력한 시간이 지나면, 미러링이 끝났든 아니든 컴퓨터를 종료합니다. '
            'Windows 자체 종료 안내가 뜨고, 언제든 취소할 수 있어요.'
        ),
        'power_caption_on_complete': (
            '미러링이 정상적으로 끝나면(오류로 끝나도 포함) 1분 뒤 컴퓨터를 종료합니다. '
            '직접 "강제 중지"를 누르면 종료하지 않습니다.'
        ),
        'power_caption_none': '시작해도 컴퓨터를 자동으로 끄지 않습니다.',

        'panel_progress': '진행 상황',
        'label_status': '상태',
        'status_waiting': '대기 중',
        'stat_elapsed': '경과 시간',
        'stat_links': '스캔한 링크',
        'stat_files': '받은 파일',
        'stat_bytes': '받은 용량',
        'stat_speed': '전송 속도',
        'stat_errors': '오류',
        'panel_log': '실시간 로그',
        'job_waiting': '대기 중 (속도 조절)',
        'job_receiving': '파일 수신 중',

        'dialog_browse_folder_title': '다운로드 폴더 선택',

        'prefs_title': '환경설정',
        'prefs_subtitle': '자주 안 바꿔도 되는 값들이에요. 한 번만 맞춰두면 다음부터 계속 적용됩니다.',
        'section_connection': '연결',
        'section_speed_time': '속도 및 시간',
        'section_policy': '수집 정책',
        'section_network': '네트워크',
        'section_language': '언어',
        'label_user_agent': 'User-Agent',
        'caption_user_agent': '비워두면 HTTrack 기본값을 사용합니다.',
        'label_connections': '동시 연결 수',
        'caption_connections': '한 번에 몇 개씩 받을지. 높이면 빠르지만 차단 위험도 커져요.',
        'label_retries': '재시도 횟수',
        'caption_retries': '요청이 실패했을 때 다시 시도할 횟수.',
        'label_timeout': '타임아웃 (초)',
        'caption_timeout': '응답 없는 서버를 이 시간 후 포기합니다.',
        'label_max_rate': '최대 속도 (Byte/s)',
        'caption_max_rate': '0 = 무제한. 너무 빠르면 차단될 수 있어요.',
        'label_robots': 'robots.txt 정책',
        'caption_robots': '사이트가 크롤러 접근을 막아둔 경우 이를 존중할지 정합니다.',
        'robots_0': '무시하고 전부 수집',
        'robots_1': '가능하면 준수',
        'robots_2': '항상 준수 (권장)',
        'label_external_links': '링크로 연결된 외부 사이트도 1단계 받기',
        'caption_external_links': '기본은 지정한 사이트만 받고, 외부로 나가는 링크는 따라가지 않아요.',
        'label_proxy': '프록시 (host:port)',
        'caption_proxy': '선택사항입니다. 비워두면 프록시를 쓰지 않습니다.',
        'label_use_local_cookies': '내 브라우저 로그인 사용',
        'caption_use_local_cookies': (
            '크롬/엣지에 이미 로그인해 둔 상태를 그대로 써서, 로그인이 필요한 사이트도 받을 수 있어요. '
            '지금 받는 사이트의 쿠키만 사용하고 다른 사이트 것은 읽지도 저장하지도 않아요.'
        ),
        'warn_cookie_lib_missing': (
            "브라우저 로그인 사용에는 'browser_cookie3' 패키지가 필요해요. "
            '설치 명령: pip install browser_cookie3'
        ),
        'warn_cookie_read_failed': '브라우저 쿠키를 읽지 못했어요: {e}',
        'warn_cookie_none_matched': '이 사이트에 대해 브라우저에 저장된 로그인이 없어요 — 로그인 없이 진행합니다.',
        'log_cookie_exported': '브라우저 로그인을 사용합니다 (이 사이트 쿠키 {n}개).',
        'mode_mirror': '사이트 미러링',
        'mode_smart': '스마트 크롤링',
        'caption_mode_mirror': '사이트를 정적 파일로 통째로 받아요.',
        'caption_mode_smart': '자바스크립트로 그려지는 화면까지 받아요.',
        'panel_smart_options': '스마트 크롤링 옵션',
        'label_max_pages': '최대 페이지 수',
        'caption_max_pages': '이 개수만큼 받고 멈춰요. 한 페이지마다 브라우저를 열기 때문에 미러링보다 느립니다.',
        'label_follow_depth': '링크 따라가기',
        'caption_follow_depth': '시작 주소에서 링크를 몇 단계까지 따라갈지 정해요. 1이면 입력한 페이지만 받습니다.',
        'label_wait_until': '대기 조건',
        'caption_wait_until': "'networkidle'은 페이지가 잠잠해질 때까지 기다려요 — 늦게 뜨는 내용까지 받기에 가장 안전합니다.",
        'summary_smart': '스마트 크롤링',
        'summary_smart_value': '{pages}페이지 · 깊이 {depth}',
        'warn_playwright_missing': '스마트 크롤링에는 Playwright가 필요해요. 설치 명령: pip install playwright',
        'log_smart_started': '스마트 크롤링을 시작합니다…',
        'log_smart_done': '스마트 크롤링 완료: {n}개 페이지를 저장했어요.',
        'log_smart_failed': '스마트 크롤링이 아무것도 저장하지 못했어요.',
        'stat_pages': '방문한 페이지',
        'status_done': '완료되었어요',
        'status_done_errors': '완료 · 못 받은 링크 {n}개',
        'status_stopped': '중지했어요',
        'status_running': '받는 중…',
        'caption_project_name': '저장 위치 아래에 만들어질 폴더 이름이에요.',
        'hint_need_url': '아래에 받을 주소를 입력하면 시작할 수 있어요',
        'existing_title': '이미 받아둔 게 있어요',
        'existing_header_complete': '이 사이트는 전에 받아둔 게 있어요',
        'existing_header_interrupted': '지난번에 받다가 멈춘 게 있어요',
        'existing_body_complete': (
            '이미 받아둔 것과 비교해서 바뀐 부분만 가져올 수 있어요 — 훨씬 빠르고, '
            '사이트에도 부담을 덜 줍니다.'
        ),
        'existing_body_interrupted': (
            '이 폴더의 지난 다운로드가 중간에 멈췄어요. 처음부터 다시 받지 않고 '
            '멈춘 지점부터 이어받을 수 있어요.'
        ),
        'existing_update': '바뀐 것만 받기',
        'existing_update_desc': '추천. 이미 받아둔 것과 비교해서 새로 생기거나 바뀐 파일만 받아요.',
        'existing_resume': '멈춘 곳부터 이어받기',
        'existing_resume_desc': '추천. 아직 못 받은 파일만 받아요.',
        'existing_fresh': '처음부터 다시 받기',
        'existing_fresh_desc': '기존에 받아둔 것을 무시하고 사이트 전체를 새로 받아요.',
        'label_language': '언어',
        'caption_language': '언어를 바꾸면 앱을 다시 시작해야 적용됩니다.',

        'confirm_title': '미러링을 시작할까요?',
        'confirm_header': '이 설정으로 시작할까요?',
        'summary_project_name': '프로젝트 이름',
        'summary_save_location': '저장 위치',
        'summary_target_urls': '대상 주소',
        'summary_action': '수집 방식',
        'summary_scope': '수집 범위',
        'summary_power': '완료 후 동작',
        'scope_unlimited': '제한 없음 (사이트 전체)',
        'scope_n_levels': '{depth} 단계까지',
        'power_text_after_hours': '{hours}시간 뒤 컴퓨터 종료',
        'power_text_on_complete': '완료되면 컴퓨터 종료',
        'power_text_none': '안 함',
        'url_count': '{n}개',

        'warn_need_url': '[경고] 받을 주소를 최소 하나 이상 입력해주세요!',
        'warn_need_project_name': '[경고] 프로젝트 이름을 입력해주세요!',
        'error_engine_missing': '[ERROR] HTTrack 엔진 경로 누락: {path}',
        'log_engine_init': 'HTTrack 엔진 초기화 중...',
        'log_project_folder': '프로젝트 폴더: {path}',
        'log_command': '명령어 실행: {cmd}',
        'log_user_stopped': '사용자에 의해 수집이 강제 중지되었습니다.',
        'log_success': '미러링이 성공적으로 완료되었습니다.',
        'log_done_with_errors': ('완료했어요. {n}개 링크는 받지 못했는데, 대개 사이트에 원래부터 깨져 있는 '
                                 '링크(404)예요. 받아온 파일 자체는 정상입니다.'),
        'log_done_code': '미러링 종료 (종료 코드: {code})',
        'log_fatal_error': '치명적 오류 발생: {result}',
        'warn_folder_not_found': '[경고] 폴더를 찾을 수 없습니다.',
        'log_prefs_saved': '환경설정이 저장되었습니다.',
        'warn_shutdown_schedule_failed': '[경고] 종료 예약에 실패했습니다: {e}',
        'notice_shutdown_scheduled': '[알림] {reason} — {mins}분 뒤 컴퓨터가 종료되도록 예약했습니다.',
        'notice_shutdown_cancelled': '[알림] 예약된 컴퓨터 종료를 취소했습니다.',
        'shutdown_banner_text': '{reason} — 약 {mins}분 뒤 컴퓨터가 종료됩니다',
        'reason_after_hours': '지정한 시간이 지나 예약된 종료',
        'reason_on_complete': '미러링이 끝나 예약된 종료',

        'panel_safety': '안전장치',
        'safety_pause_enable': '요청 사이 텀 두기',
        'safety_pause_caption': (
            '요청마다 무작위로 시간을 두고 받습니다. 느려지지만 대상 사이트에 부담을 덜 주고 '
            '차단당할 확률을 낮춰줍니다.'
        ),
        'safety_pause_between': '텀',
        'safety_pause_and': '~',
        'safety_pause_unit': '초',
        'safety_maxtime_enable': '최대 실행 시간 제한',
        'safety_maxtime_label': '시간 후 중단',
        'safety_maxtime_caption': '완료 여부와 상관없이 지정한 시간이 지나면 자동으로 멈춥니다.',
        'safety_maxsize_enable': '전체 용량 제한',
        'safety_maxsize_label': 'MB 넘으면 중단',
        'safety_maxsize_caption': '지정한 용량만큼 받으면 자동으로 멈춥니다.',
        'safety_hostcontrol_label': '느린 호스트 자동 포기',
        'hostcontrol_none': '포기 안 함',
        'hostcontrol_timeout': '타임아웃 시',
        'hostcontrol_slow': '느릴 때',
        'hostcontrol_both': '타임아웃 또는 느릴 때',
        'safety_hostcontrol_caption': '특정 호스트가 계속 타임아웃되거나 너무 느리면 일찍 포기하고 넘어갑니다.',
        'btn_load_url_file': '파일에서 불러오기',
        'dialog_load_url_file_title': '한 줄에 하나씩 URL이 담긴 텍스트 파일 선택',
        'log_loaded_urls': '파일에서 URL {n}개를 불러왔습니다.',
        'warn_url_file_failed': '[경고] 파일을 읽을 수 없습니다: {e}',

        'section_advanced': '고급',
        'label_referer': 'Referer 헤더',
        'caption_referer': '선택사항입니다. 모든 요청에 Referer 헤더로 전송됩니다.',
        'label_lang_header': '선호 언어 헤더',
        'caption_lang_header': (
            '사이트에 Accept-Language 헤더로 전송됩니다 (예: "ko, en"). 이 앱 자체의 화면 언어와는 '
            '별개입니다.'
        ),
        'label_custom_headers': '커스텀 HTTP 헤더',
        'caption_custom_headers': '한 줄에 하나씩, "헤더이름: 값" 형식으로 입력하세요. 필요 없으면 비워두세요.',
        'label_cookies_file': '쿠키 파일',
        'caption_cookies_file': '선택사항입니다. 로그인이 필요한 사이트에 쓰는 Netscape 형식 cookies.txt.',
        'dialog_cookies_file_title': 'cookies.txt 파일 선택',
        'label_link_format': '저장된 페이지의 링크 형식',
        'link_format_relative': '상대 경로 (기본)',
        'link_format_absolute': '절대 경로',
        'link_format_original': '원본 그대로 유지',
        'caption_link_format': '받아온 페이지들 사이의 링크를 어떻게 다시 쓸지 정합니다.',
        'label_near_files': '사이트 바로 바깥의 관련 파일도 함께 받기',
        'caption_near_files': '예: 저장된 페이지에 링크된, 다른 서브도메인에 있는 이미지 등.',
        'label_conn_per_sec': '초당 새 연결 수',
        'caption_conn_per_sec': '위 전체 연결 수와 별개로, 새 연결을 얼마나 빠르게 열지 제한합니다.',
        'label_warc': 'WARC 아카이브도 함께 저장',
        'caption_warc': '일반 미러링 결과와 함께 아카이빙 도구용 표준 .warc 파일도 만듭니다.',
        'label_search_index': '검색 인덱스 만들기',
        'caption_search_index': '받아온 페이지들에 대한 간단한 검색 인덱스를 생성합니다.',

        'tab_schedule': '스마트 크롤링',
        'nav_home': '홈',
        'nav_preferences': '환경설정',
        'dashboard_greeting': 'MirrorX0로 지금까지 한 일을 한눈에 볼 수 있어요.',
        'section_overview': '한눈에 보기',
        'metric_total_projects': '전체 프로젝트',
        'metric_total_size': '받은 총 용량',
        'metric_success_rate': '성공률',
        'metric_activity': '최근 활동',
        'metric_scheduled': '예약된 작업',
        'caption_success_rate': '성공 {success} · 오류 {errors}',
        'panel_recent_previews': '최근 받은 사이트',
        'label_no_previews': '아직 받은 게 없어요 — 미러링을 시작하면 여기에 보여요.',
        'panel_schedule_list': '스마트 크롤링 작업',
        'caption_schedule_list': (
            'MirrorX0을 꺼두어도 지정한 시각에 자동으로 실행돼요 — 컴퓨터가 켜져 있고 '
            '로그인된 상태여야 합니다 (잠금 화면은 괜찮아요).'
        ),
        'label_no_jobs': '아직 스마트 크롤링을 설정하지 않았어요.',
        'btn_new_job': '새 스마트 크롤링',
        'btn_edit_job': '수정',
        'btn_delete_job': '삭제',
        'job_mode_httrack': '일반 (HTTrack)',
        'job_mode_smart': '스마트 (브라우저 렌더링)',
        'job_mode_both': '둘 다',
        'schedule_type_once': '1회',
        'schedule_type_daily': '매일',
        'schedule_type_weekly': '매주',
        'job_status_never_run': '실행 전',
        'job_status_running': '실행 중',
        'job_status_success': '완료',
        'job_status_errors': '오류와 함께 완료',
        'job_status_error': '실패',
        'dialog_job_title': '예약 작업',
        'label_job_name': '작업 이름',
        'label_job_mode': '크롤링 방식',
        'label_schedule_type': '반복',
        'label_schedule_time': '시각',
        'label_schedule_date': '날짜 (YYYY-MM-DD) — "1회"일 때 사용',
        'label_schedule_weekdays': '요일 — "매주"일 때 사용',
        'weekday_mon': '월', 'weekday_tue': '화', 'weekday_wed': '수', 'weekday_thu': '목',
        'weekday_fri': '금', 'weekday_sat': '토', 'weekday_sun': '일',
        'caption_schedule_note': '컴퓨터가 켜져 있고 로그인된 상태여야 실행돼요 — 잠금 화면은 괜찮아요.',
        'warn_job_need_name': '[경고] 작업 이름을 입력해주세요!',
        'warn_job_need_url': '[경고] 주소를 최소 하나 이상 입력해주세요!',
        'warn_job_need_date': '[경고] 1회 실행은 날짜를 입력해주세요!',
        'warn_job_invalid_date': '[경고] 날짜는 YYYY-MM-DD 형식으로 입력해주세요!',
        'log_job_saved': '예약 작업이 저장되었습니다.',
        'log_job_deleted': '예약 작업이 삭제되었습니다.',
        'warn_job_schedule_failed': '[경고] 예약 작업 등록에 실패했습니다: {e}',

        'section_ai': 'AI 크롤링',
        'label_ai_provider': 'AI 프로바이더',
        'caption_ai_provider': '필드 제안과 데이터 추출에 어떤 AI를 사용할지 선택합니다.',
        'label_api_key_anthropic': 'Anthropic API 키',
        'label_api_key_openai': 'OpenAI API 키',
        'label_api_key_gemini': 'Google Gemini API 키',
        'caption_api_key': 'AI 기반 데이터 추출에 사용됩니다. 이 컴퓨터에만 저장되고 위에서 고른 프로바이더에만 전송됩니다.',
        'label_ai_extract_enable': 'AI로 데이터 추출하기',
        'label_ai_instruction': '어떤 정보를 추출할까요?',
        'caption_ai_instruction': '한 문장으로 설명해주세요. 예: "상품명, 가격, 리뷰 개수".',
        'btn_propose_fields': '필드 확인',
        'label_extract_fields': '추출할 필드',
        'field_col_name': '필드 이름',
        'field_col_label': '설명',
        'field_col_type': '타입',
        'btn_add_field': '+ 필드 추가',
        'label_export_formats': '내보내기 형식',
        'btn_run_extraction': '추출 실행',
        'dialog_ai_extract_title': 'AI 데이터 추출',
        'btn_ai_extract': 'AI 추출',
        'warn_need_api_key': '[경고] 환경설정에서 Anthropic API 키를 먼저 등록해주세요!',
        'warn_need_instruction': '[경고] 어떤 정보를 추출할지 입력해주세요!',
        'warn_need_sample_page': '[경고] 필드를 제안할 샘플 페이지를 가져오지 못했습니다.',
        'warn_propose_failed': '[경고] 필드 제안에 실패했습니다: {e}',
        'log_fields_proposed': '필드 {n}개를 제안받았습니다.',
        'warn_need_fields': '[경고] 추출할 필드를 최소 하나 이상 추가해주세요!',
        'log_ai_extract_started': 'AI 추출을 시작합니다...',
        'warn_ai_skip_no_key': '[AI 추출] API 키가 설정되어 있지 않아 건너뜁니다.',

        'btn_ai_scope_rules': 'AI로 규칙 제안받기',
        'dialog_ai_scope_title': 'AI 다운로드 범위 규칙',
        'label_scope_goal': '무엇을 받고 싶으신가요?',
        'caption_scope_goal': '한 문장으로 설명해주세요. 예: "레시피 카테고리만 받고 로그인/장바구니 페이지는 빼줘".',
        'btn_get_scope_rules': '규칙 제안받기',
        'caption_scope_cost': (
            '시작 주소에서 링크 샘플을 조금 살펴본 뒤, 단 한 번의 AI 호출로 규칙을 제안합니다 — '
            '사이트 크기와 무관하게 비용이 고정됩니다.'
        ),
        'label_proposed_rules': '제안된 규칙 (적용 전에 수정할 수 있어요)',
        'btn_apply_rules': '적용',
        'warn_scope_need_goal': '[경고] 무엇을 받고 싶은지 입력해주세요!',
        'warn_scope_need_url': '[경고] 먼저 주소를 입력해주세요!',
        'log_fetching_link_sample': '링크 샘플을 가져오는 중...',
        'warn_scope_no_links': '[경고] 분석할 링크를 찾지 못했습니다.',
        'warn_scope_failed': '[경고] 규칙 제안을 받지 못했습니다: {e}',
        'log_scope_rules_applied': 'AI가 제안한 규칙을 적용했습니다.',

        'panel_recent_projects': '최근 프로젝트',
        'caption_recent_projects': '이전에 받던 프로젝트를 이어서 하거나, 그때 설정을 다시 불러올 수 있어요.',
        'label_no_projects': '아직 받은 프로젝트가 없어요.',
        'btn_load_project': '불러오기',
        'btn_continue_project': '이어받기',
        'btn_delete_project': '삭제',
        'proj_status_never': '실행 전',
        'proj_status_running': '실행 중',
        'proj_status_success': '완료',
        'proj_status_errors': '오류와 함께 완료',
        'proj_status_failed': '실패',
        'proj_url_count': '{n}개',
    },
}

_current_lang = 'en'


def set_language(lang):
    global _current_lang
    _current_lang = lang if lang in STRINGS else 'en'


def t(key, **kwargs):
    template = STRINGS.get(_current_lang, STRINGS['en']).get(key, STRINGS['en'].get(key, key))
    return template.format(**kwargs) if kwargs else template


def get_actions():
    return [(code, t(f'action_{code}')) for code in ('1', '2', '3', '4', '5')]


def get_robots_options():
    return [(code, t(f'robots_{code}')) for code in ('0', '1', '2')]


def get_filter_groups():
    """파일 종류 체크박스 그룹: (표시 이름, 매칭 확장자들, 기본 선택 여부)"""
    return [
        (t('filter_images'), ['png', 'gif', 'jpg', 'jpeg', 'webp', 'svg', 'ico', 'avif', 'bmp', 'tiff'], True),
        (t('filter_style_script'), ['css', 'js', 'mjs'], True),
        (t('filter_docs'),
         ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'hwp', 'hwpx', 'txt', 'csv', 'epub'], False),
        (t('filter_media'), ['mp4', 'mp3', 'avi', 'webm', 'wav', 'mkv', 'mov', 'flac', 'ogg', 'm4a'], False),
        (t('filter_archive'), ['zip', 'rar', '7z', 'tar', 'gz'], False),
    ]


def get_job_labels():
    return {
        'waiting (throttle)': t('job_waiting'),
        'receiving files': t('job_receiving'),
    }


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

# ---------------- 팔레트 & 폰트 ----------------
# 차갑고 기술적인 남색/파랑 계열 대신, 따뜻하면서도 정제된 다크 테마.
# 배경은 중성 다크 그레이, 포인트는 따뜻한 호박색(amber/terracotta) 하나로 통일.
# ---------------- 팔레트 (2026 모던 라이트: 소프트 화이트 + 오렌지) ----------------
# 애플 시스템 컬러 계열의 차분한 무채색 위에 따뜻한 오렌지 하나만 강조색으로 쓴다.
# 강조색은 아껴서(주요 동작 = 시작 버튼/브랜드 배너에만) 쓰고, 상태는 의미 기반
# 색(Success/Caution/Critical)으로만 구분한다.
BG = '#F6F4F1'              # 페이지 배경 - 아주 옅은 웜 그레이
PANEL = '#FFFFFF'           # 카드/패널 배경 - 흰색
PANEL_LIGHT = '#F3F0EC'     # 카드 안의 한 단계 더 옅은 표면(입력창 등)
BORDER = '#E9E5DF'          # 카드 테두리/구분선
ACCENT = '#F97316'          # 브랜드 오렌지
ACCENT_HOVER = '#EA6A0A'
ACCENT_DEEP = '#DC5A00'     # 그라데이션 끝 색(배너/원형 버튼의 아래쪽)
ACCENT_SOFT = '#FFF3E8'     # 은은한 오렌지 틴트 배경
ACCENT_TEXT = '#C2410C'     # 작은 글씨를 오렌지로 쓸 때(흰 배경에서 읽히도록 더 진하게)
FG = '#1C1C1E'              # 본문 텍스트 - 애플 label 계열
FG_MUTED = '#8A8A8E'        # 보조 텍스트 - 애플 secondary label 계열
ON_ACCENT = '#FFFFFF'       # 강조색 위에 올라가는 텍스트
ON_DANGER = '#FFFFFF'       # 위험색 위에 올라가는 텍스트

# 지표 카드용 - 브랜드 오렌지에서 채도만 거의 뺀 웜 아이보리.
# 페이지 배경(웜 그레이) → 지표 카드(아이보리) → 콘텐츠 카드(순백)로 3단 레이어를 만든다.
STAT_BG = '#FCF7F1'
STAT_BORDER = '#F0E5D8'

SUCCESS = '#2FB457'         # 진행률 링/성공 - 애플 그린 계열(흰 배경에서도 선명하게)
CAUTION = '#B45309'
CRITICAL = '#E5484D'
ATTENTION = '#0A84FF'       # 정보/파란 톤

# 기존 코드와의 하위 호환용 별칭 (같은 의미 색으로 매핑)
GREEN = SUCCESS
RED = CRITICAL
AMBER = CAUTION
TAB_INACTIVE = '#ECE8E3'    # 선택 안 된 탭은 배경보다 살짝 더 어둡게 눌러서 구분

FONT_UI = 'Malgun Gothic'   # resolve_fonts()가 설치된 폰트를 보고 더 나은 것으로 바꾼다
FONT_DISPLAY = 'Segoe UI Variable Display'   # 로고/큰 숫자용
FONT_MONO = 'Consolas'


def resolve_fonts():
    """설치된 폰트 중 가장 보기 좋은 것을 골라 전역 폰트 이름을 확정한다.
    families()는 Tk 루트가 있어야 조회되므로 앱 시작 시점에 한 번 호출한다.
    본문용은 한글/영문을 한 벌로 예쁘게 처리하는 Noto Sans KR을 우선하고,
    로고처럼 영문만 쓰는 곳은 Segoe UI Variable Display를 우선한다."""
    global FONT_UI, FONT_DISPLAY, FONT_MONO
    import tkinter.font as tkfont
    try:
        available = set(tkfont.families())
    except Exception:
        return

    def pick(candidates, fallback):
        return next((name for name in candidates if name in available), fallback)

    FONT_UI = pick(['Noto Sans KR', 'Segoe UI Variable Text', 'Segoe UI'], FONT_UI)
    FONT_DISPLAY = pick(['Segoe UI Variable Display', 'Segoe UI', 'Noto Sans KR'], FONT_UI)
    FONT_MONO = pick(['Cascadia Mono', 'Consolas'], FONT_MONO)

# Windows 11 타입 램프(Segoe UI Variable 기준 실측값) - 이 앱 전역에서 이 크기만 사용한다.
# 한 단계씩만 차이 나는 하나의 스케일로 통일한다. 화면 어디서든 이 상수만 쓰고
# 숫자를 직접 적지 않아야 크기 밸런스가 흐트러지지 않는다.
TYPE_CAPTION = 11       # 캡션/보조 설명
TYPE_BODY = 13          # 본문 기본 (라벨, 버튼)
TYPE_INPUT = 15         # 입력창/드롭다운 - 실제로 타이핑·선택하는 곳이라 한 단계 크게
TYPE_BODY_LARGE = 17    # 강조된 본문 (지표 값 등)
TYPE_SUBTITLE = 19      # 패널/다이얼로그 제목
TYPE_TITLE = 26         # 화면 최상위 제목


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


_SIZE_UNIT_RE = re.compile(r'([KMGT])i([Bb])')
_DECIMAL_COMMA_RE = re.compile(r'(\d),(\d)')


def friendly_size(text):
    """HTTrack이 내는 '2,76GiB' 같은 표기를 '2.76GB'처럼 보기 편한 형태로 바꾼다."""
    if not text or text == '-':
        return text
    text = _DECIMAL_COMMA_RE.sub(r'\1.\2', text)
    text = _SIZE_UNIT_RE.sub(r'\1\2', text)
    return text


def format_bytes(n):
    """int 바이트 수를 사람이 읽기 좋은 단위로. friendly_size()는 HTTrack 문자열용,
    이건 우리가 직접 계산한 정수 바이트용이라 별도로 둔다."""
    n = float(n)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or unit == 'TB':
            return f'{int(n)} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} TB'


def _folder_size(folder):
    total = 0
    if not os.path.isdir(folder):
        return 0
    for root_dir, _dirs, files in os.walk(folder):
        for fname in files:
            try:
                total += os.path.getsize(os.path.join(root_dir, fname))
            except OSError:
                pass
    return total


def compute_dashboard_metrics(projects, jobs_list, days=7):
    """대시보드용 5개 지표를 계산한다. 프로젝트가 실제로 차지한 용량은 저장된
    숫자가 없으므로(HTTrack 실행 중에만 파싱되는 값) 폴더를 직접 스캔해서 구한다 -
    항상 정확하고, 예전에 만든 프로젝트에도 그대로 적용된다."""
    from datetime import timedelta
    total_projects = len(projects)
    success_count = sum(1 for p in projects if p.get('last_status') == 'success')
    error_count = sum(1 for p in projects if p.get('last_status') in ('errors', 'failed', 'error'))
    total_size_bytes = sum(_folder_size(os.path.join(p.get('base_path', ''), p.get('name', ''))) for p in projects)
    scheduled_enabled = sum(1 for j in jobs_list if j.get('enabled'))

    today = datetime.now().date()
    day_list = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
    counts = {}
    for p in projects:
        ts = p.get('last_run_at')
        if not ts:
            continue
        try:
            d = datetime.fromisoformat(ts).date()
        except ValueError:
            continue
        counts[d] = counts.get(d, 0) + 1

    return {
        'total_projects': total_projects,
        'success_count': success_count,
        'error_count': error_count,
        'total_size_bytes': total_size_bytes,
        'scheduled_enabled': scheduled_enabled,
        'activity_values': [counts.get(d, 0) for d in day_list],
        'activity_labels': [d.strftime('%a') for d in day_list],
    }


def draw_bar_chart(canvas, values, labels, width, height, color=None):
    """캔버스에 직접 그리는 단순 막대그래프 (matplotlib 없이). 새 의존성 없이
    RoundedCard/RoundedButton과 동일한 '캔버스에 직접 그린다' 원칙을 그대로 따름."""
    color = color or ACCENT
    canvas.delete('all')
    if not values:
        return
    max_val = max(values) or 1
    n = len(values)
    pad = 14
    baseline = height - 22
    gap = (width - 2 * pad) / n
    bar_w = gap * 0.5
    for i, v in enumerate(values):
        x_center = pad + gap * i + gap / 2
        bar_h = (v / max_val) * (baseline - 14) if max_val else 0
        fill = color if v > 0 else BORDER
        canvas.create_rectangle(x_center - bar_w / 2, baseline - bar_h, x_center + bar_w / 2, baseline,
                                 fill=fill, outline=fill)
        canvas.create_text(x_center, baseline + 12, text=labels[i], font=(FONT_UI, 9), fill=FG_MUTED)


def draw_donut_chart(canvas, success, errors, width, height):
    """성공/오류 비율을 도넛(링) 형태로 그린다."""
    canvas.delete('all')
    total = success + errors
    cx, cy = width / 2, height / 2
    r = min(width, height) / 2 - 10
    if total <= 0:
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=BORDER, width=14)
        canvas.create_text(cx, cy, text='-', font=(FONT_UI, TYPE_BODY_LARGE, 'bold'), fill=FG_MUTED)
        return
    success_angle = 360 * success / total
    if success_angle > 0:
        canvas.create_arc(cx - r, cy - r, cx + r, cy + r, start=90, extent=-success_angle,
                           style='arc', outline=SUCCESS, width=14)
    if success_angle < 360:
        canvas.create_arc(cx - r, cy - r, cx + r, cy + r, start=90 - success_angle, extent=-(360 - success_angle),
                           style='arc', outline=CRITICAL, width=14)
    pct = int(round(100 * success / total))
    canvas.create_text(cx, cy, text=f'{pct}%', font=(FONT_UI, TYPE_TITLE, 'bold'), fill=FG)


def make_scrollable(parent, bg=BG):
    """parent를 스크롤 가능한 세로 영역으로 만들고, 내용을 채울 내부 프레임을 돌려준다.
    창/화면이 작아서 내용이 다 안 보일 때를 대비한 공통 처리 (환경설정 창과 미러링 탭에서 공용으로 씀)."""
    container = tk.Frame(parent, bg=bg)
    container.pack(fill='both', expand=True)
    canvas = tk.Canvas(container, bg=bg, highlightthickness=0)
    scrollbar = ttk.Scrollbar(container, orient='vertical', command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side='left', fill='both', expand=True)
    scrollbar.pack(side='right', fill='y')

    inner = ttk.Frame(canvas)
    inner_window = canvas.create_window((0, 0), window=inner, anchor='nw')

    def _sync_scrollregion(_event=None):
        canvas.configure(scrollregion=canvas.bbox('all'))
    inner.bind('<Configure>', _sync_scrollregion)

    def _sync_width(event):
        canvas.itemconfig(inner_window, width=event.width)
    canvas.bind('<Configure>', _sync_width)

    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
    canvas.bind('<Enter>', lambda e: canvas.bind_all('<MouseWheel>', _on_mousewheel))
    canvas.bind('<Leave>', lambda e: canvas.unbind_all('<MouseWheel>'))

    return inner


def _rounded_rect_points(x1, y1, x2, y2, r):
    """둥근 사각형을 그리기 위한 점 목록. canvas.create_polygon(..., smooth=True)에
    넘기면 각 모서리의 꺾인 점들이 부드럽게 이어져 둥근 모서리처럼 보인다."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]


def _hex_to_rgb(color):
    color = color.lstrip('#')
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def lerp_color(color_a, color_b, ratio):
    """두 색 사이를 ratio(0~1)만큼 섞은 색을 '#rrggbb'로 돌려준다.
    Tkinter에는 그라데이션 기능이 없어서, 얇은 선/사각형을 여러 개 그려
    부드러운 그라데이션처럼 보이게 하는 데 쓴다."""
    ratio = max(0.0, min(1.0, ratio))
    a, b = _hex_to_rgb(color_a), _hex_to_rgb(color_b)
    mixed = tuple(round(a[i] + (b[i] - a[i]) * ratio) for i in range(3))
    return '#%02x%02x%02x' % mixed


def draw_vertical_gradient(canvas, x1, y1, x2, y2, color_top, color_bottom, tags=None):
    """세로 그라데이션을 1px 가로선을 쌓아서 그린다."""
    height = int(y2 - y1)
    if height <= 0:
        return
    for i in range(height):
        color = lerp_color(color_top, color_bottom, i / max(1, height - 1))
        canvas.create_line(x1, y1 + i, x2, y1 + i, fill=color, tags=tags or ())


def draw_soft_shadow(canvas, x1, y1, x2, y2, radius, page_bg, depth=7, spread=1.6):
    """둥근 사각형 아래에 은은한 그림자를 깔아준다. Tkinter에는 그림자가 없어서
    바깥에서 안쪽으로 갈수록 진해지는 둥근 사각형을 여러 겹 그려 흉내 낸다."""
    for i in range(depth, 0, -1):
        offset = i * spread
        color = lerp_color(page_bg, '#B9B2A8', 0.30 * (1 - (i - 1) / depth))
        points = _rounded_rect_points(x1 + offset * 0.4, y1 + offset * 0.6,
                                      x2 - offset * 0.4, y2 + offset, radius + offset)
        canvas.create_polygon(points, smooth=True, fill=color, outline=color)


class BrandHeader(tk.Canvas):
    """상단 브랜드 헤더. 주황 배너 대신 흰 카드 + 부드러운 그림자로 가볍게 띄운다.
    로고는 'Mirror'(먹색) + 'X0'(강조색)로 팔레트 포인트만 살짝 준다."""

    def __init__(self, parent, subtitle, height=82, page_bg=BG):
        super().__init__(parent, height=height, highlightthickness=0, bd=0, bg=page_bg)
        self.subtitle_text = subtitle
        self.page_bg = page_bg
        self.bind('<Configure>', lambda _e: self._redraw())

    def _redraw(self):
        self.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1 or h <= 1:
            return
        pad_x, pad_y = 22, 10
        x1, y1, x2, y2 = pad_x, pad_y, w - pad_x, h - pad_y - 6
        draw_soft_shadow(self, x1, y1, x2, y2, 18, self.page_bg)
        points = _rounded_rect_points(x1, y1, x2, y2, 18)
        self.create_polygon(points, smooth=True, fill=PANEL, outline=BORDER, width=1)

        cy = (y1 + y2) / 2
        tx = x1 + 28
        # 두 조각으로 나눠 그리기 위해 앞부분 폭을 재서 이어 붙인다.
        first = self.create_text(tx, cy, text='Mirror', anchor='w', fill=FG,
                                 font=(FONT_DISPLAY, 30, 'bold'))
        bounds = self.bbox(first)
        self.create_text(bounds[2], cy, text='X0', anchor='w', fill=ACCENT,
                         font=(FONT_DISPLAY, 30, 'bold'))
        self.create_text(x2 - 28, cy, text=self.subtitle_text, anchor='e',
                         fill=FG_MUTED, font=(FONT_UI, TYPE_BODY))


class SegmentedControl(tk.Canvas):
    """알약 모양 2분할 선택기 (애플/ExpressVPN류 세그먼트 컨트롤).
    바탕은 옅은 트랙이고, 선택된 칸만 흰 '썸'으로 떠올라 보인다.
    ttk에는 이런 위젯이 없어서 Canvas에 직접 그린다."""

    def __init__(self, parent, variable, options, command=None, page_bg=None,
                 width=360, height=44, radius=None):
        page_bg = page_bg if page_bg is not None else BG
        super().__init__(parent, width=width, height=height, bg=page_bg,
                         highlightthickness=0, bd=0)
        self.variable = variable
        self.options = list(options)          # [(value, label), ...]
        self.command = command
        self.w, self.h = width, height
        self.radius = radius if radius is not None else height / 2
        self._hover_index = None

        self.bind('<Button-1>', self._on_click)
        self.bind('<Motion>', self._on_motion)
        self.bind('<Leave>', self._on_leave)
        self.bind('<Configure>', self._on_configure)
        self._trace_id = variable.trace_add('write', lambda *_a: self._redraw())
        self.bind('<Destroy>', self._on_destroy)
        self._redraw()

    def _on_destroy(self, _event=None):
        try:
            self.variable.trace_remove('write', self._trace_id)
        except Exception:
            pass

    def _on_configure(self, event):
        self.w, self.h = event.width, event.height
        self.radius = self.h / 2
        self._redraw()

    def _index_at(self, x):
        if not self.options:
            return None
        idx = int(x // (self.w / len(self.options)))
        return max(0, min(len(self.options) - 1, idx))

    def _on_click(self, event):
        idx = self._index_at(event.x)
        if idx is None:
            return
        value = self.options[idx][0]
        if value != self.variable.get():
            self.variable.set(value)
            if self.command:
                self.command(value)

    def _on_motion(self, event):
        idx = self._index_at(event.x)
        if idx != self._hover_index:
            self._hover_index = idx
            self.configure(cursor='hand2')
            self._redraw()

    def _on_leave(self, _event):
        self._hover_index = None
        self.configure(cursor='')
        self._redraw()

    def _redraw(self):
        self.delete('all')
        if self.w <= 1 or self.h <= 1 or not self.options:
            return
        # 트랙
        track = _rounded_rect_points(1, 1, self.w - 1, self.h - 1, self.radius)
        self.create_polygon(track, smooth=True, fill=PANEL_LIGHT, outline=BORDER, width=1)

        current = self.variable.get()
        seg_w = self.w / len(self.options)
        pad = 3
        for i, (value, label) in enumerate(self.options):
            x1 = i * seg_w
            x2 = x1 + seg_w
            selected = (value == current)
            if selected:
                # 선택된 칸만 흰 썸으로 떠올린다 (그림자 대신 얇은 테두리로 입체감).
                thumb = _rounded_rect_points(x1 + pad, pad, x2 - pad, self.h - pad,
                                             self.radius - pad)
                self.create_polygon(thumb, smooth=True, fill=PANEL,
                                    outline=lerp_color(BORDER, '#FFFFFF', 0.35), width=1)
            fg = FG if selected else (FG if self._hover_index == i else FG_MUTED)
            weight = 'bold' if selected else 'normal'
            self.create_text((x1 + x2) / 2, self.h / 2, text=label, fill=fg,
                             font=(FONT_UI, TYPE_BODY, weight))


class CircularStartButton(tk.Canvas):
    """ExpressVPN의 원형 전원 버튼을 참고한 메인 동작 버튼.
    바깥 링이 다운로드 진행률에 따라 초록으로 차오르고, 안쪽 원은 오렌지
    그라데이션으로 채워진다. 창 크기에 맞춰 set_size()로 지름을 조절할 수 있다."""

    RING_WIDTH_RATIO = 0.075
    GLOW_RATIO = 0.115      # 캔버스 바깥쪽에서 글로우(빛번짐)가 차지하는 비율

    def __init__(self, parent, command=None, size=210, page_bg=BG):
        super().__init__(parent, width=size, height=size, bg=page_bg, highlightthickness=0, bd=0)
        self.command = command
        self.size = size
        self.page_bg = page_bg
        self._progress = 0.0
        self._running = False
        self._hover = False
        self._enabled = False   # 받을 주소를 넣기 전에는 누를 수 없다
        self.bind('<ButtonRelease-1>', self._on_release)
        self.bind('<Enter>', self._on_enter)
        self.bind('<Leave>', self._on_leave)
        self._redraw()

    # --- 외부에서 상태를 바꾸는 API ---
    def set_size(self, size):
        size = max(120, int(size))
        if size == self.size:
            return
        self.size = size
        self.configure(width=size, height=size)
        self._redraw()

    def set_progress(self, pct):
        self._progress = max(0.0, min(100.0, float(pct)))
        self._redraw()

    def set_running(self, running):
        self._running = bool(running)
        if not running:
            self._progress = 0.0
        self._redraw()

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        self._redraw()

    def is_running(self):
        return self._running

    def _clickable(self):
        # 실행 중에는 (중지해야 하므로) 주소 입력 여부와 무관하게 항상 누를 수 있다.
        return self._running or self._enabled

    # --- 내부 ---
    def _on_enter(self, _event):
        if not self._clickable():
            return
        self._hover = True
        self.configure(cursor='hand2')
        self._redraw()

    def _on_leave(self, _event):
        self._hover = False
        self.configure(cursor='')
        self._redraw()

    def _on_release(self, event):
        if (self._clickable() and self.command
                and 0 <= event.x <= self.size and 0 <= event.y <= self.size):
            self.command()

    def _redraw(self):
        self.delete('all')
        s = self.size
        glow = s * self.GLOW_RATIO
        ring_w = max(8, (s - glow * 2) * self.RING_WIDTH_RATIO)
        pad = glow + ring_w / 2

        # 0) 글로우 - 배경색에서 강조색 쪽으로 서서히 물드는 동심원을 바깥에서
        #    안쪽으로 겹쳐 그려, 버튼 주변이 은은하게 빛나 보이게 한다.
        if self._clickable():
            glow_color = SUCCESS if self._running else ACCENT
            peak = 0.46 if self._hover else 0.30
            steps = max(6, int(glow))
            for i in range(steps):
                depth = (i + 1) / steps          # 안쪽으로 갈수록 1에 가까워진다
                spread = glow * (1 - depth)
                color = lerp_color(self.page_bg, glow_color, peak * depth ** 2)
                self.create_oval(pad - spread, pad - spread, s - pad + spread, s - pad + spread,
                                 outline=color, width=2)

        # 1) 진행률 링의 바탕 트랙 (항상 옅은 회색 원)
        self.create_oval(pad, pad, s - pad, s - pad, outline=BORDER, width=ring_w)

        # 2) 진행률 - 12시 방향에서 시계 방향으로 차오른다.
        if self._progress > 0:
            self.create_arc(pad, pad, s - pad, s - pad, start=90, extent=-359.99 * self._progress / 100,
                            style='arc', outline=SUCCESS, width=ring_w)

        # 3) 안쪽 원 - 오렌지 그라데이션. Canvas는 원에 직접 그라데이션을 못 넣어서
        #    원의 각 y줄마다 반지름을 계산해 가로선을 그려 채운다.
        inner_pad = pad + ring_w / 2 + s * 0.045
        cx = cy = s / 2
        radius = cx - inner_pad
        if radius > 4:
            if self._running:
                top, bottom = '#FFFFFF', '#F4F1EC'
            elif not self._enabled:
                # 받을 주소를 넣기 전 - 회색으로 눌러 "아직 못 누른다"를 분명히 보여준다.
                top, bottom = PANEL_LIGHT, BORDER
            elif self._hover:
                top, bottom = lerp_color(ACCENT, '#FFFFFF', 0.12), ACCENT
            else:
                top, bottom = ACCENT, ACCENT_DEEP
            steps = int(radius * 2)
            for i in range(steps):
                y = cy - radius + i
                # 원의 방정식으로 이 y줄에서의 가로 반폭을 구한다.
                dy = y - cy
                half = (radius ** 2 - dy ** 2) ** 0.5 if abs(dy) < radius else 0
                if half <= 0:
                    continue
                color = lerp_color(top, bottom, i / max(1, steps - 1))
                self.create_line(cx - half, y, cx + half, y, fill=color)
            if self._running or not self._enabled:
                self.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                                 outline=BORDER, width=1)
            elif self._enabled:
                # 위쪽에 옅은 광택 호를 얹어 유리알처럼 살짝 볼록해 보이게 한다.
                inset_h = radius * 0.16
                self.create_arc(cx - radius + inset_h, cy - radius + inset_h * 0.7,
                                cx + radius - inset_h, cy + radius * 0.35,
                                start=20, extent=140, style='arc',
                                outline=lerp_color(ACCENT, '#FFFFFF', 0.45),
                                width=max(2, int(radius * 0.05)))

        # 4) 가운데 표시
        #    실행 중  : 큰 완료 퍼센트 + 아래에 '중지'
        #    대기/비활성: 전원 아이콘 + '시작'
        if self._running:
            self.create_text(cx, cy - s * 0.045, text=f'{self._progress:.0f}%', fill=FG,
                             font=(FONT_UI, max(20, int(s * 0.20)), 'bold'))
            self.create_text(cx, cy + s * 0.145, text=t('btn_stop'), fill=CRITICAL,
                             font=(FONT_UI, max(11, int(s * 0.078)), 'bold'))
        else:
            glyph_color = FG_MUTED if not self._enabled else ON_ACCENT
            self.create_text(cx, cy - s * 0.055, text='⏻', fill=glyph_color,
                             font=(FONT_UI, max(20, int(s * 0.20))))
            self.create_text(cx, cy + s * 0.135, text=t('btn_start'), fill=glyph_color,
                             font=(FONT_UI, max(11, int(s * 0.075)), 'bold'))


class RoundedCard(tk.Frame):
    """카드처럼 보이는 둥근 모서리 컨테이너 (Windows 지오메트리 가이드의 8px
    규칙). Tkinter/ttk가 모서리 둥글리기를 기본 지원하지 않아서, Canvas에
    직접 둥근 사각형을 그리고 그 위에 실제 콘텐츠를 담을 프레임(.body)을
    얹는 방식으로 흉내 낸다 - make_scrollable()의 캔버스+임베드 프레임
    패턴과 같은 원리. 실제 콘텐츠는 반드시 .body 안에 넣어야 한다."""

    def __init__(self, parent, page_bg=None, card_bg=None, border=None, radius=14, padding=14, expand=False,
                 body_style='Panel.TFrame', inset=None):
        page_bg = page_bg if page_bg is not None else BG
        card_bg = card_bg if card_bg is not None else PANEL
        border = border if border is not None else BORDER
        super().__init__(parent, bg=page_bg)
        self.radius = radius
        self.card_bg = card_bg
        self.border_color = border
        # inset: 카드 테두리와 내용 사이의 여백(px). 기본은 radius와 같게 두지만,
        # 촘촘한 목록 행처럼 세로 공간을 아껴야 하는 곳에서는 따로 줄일 수 있다.
        self.inset = radius if inset is None else inset
        self.expand_mode = expand

        self.canvas = tk.Canvas(self, bg=page_bg, highlightthickness=0)
        self.canvas.pack(fill='both' if expand else 'x', expand=expand)

        # body_style: 카드 배경색이 PANEL이 아닐 때(예: 설정 요약 행의 PANEL_LIGHT)
        # 내부 프레임 배경도 같이 맞추기 위해 다른 ttk 스타일을 넘길 수 있게 한다.
        self.body = ttk.Frame(self.canvas, style=body_style, padding=padding)
        self._window_id = self.canvas.create_window(self.inset, self.inset, window=self.body, anchor='nw')

        self.body.bind('<Configure>', self._sync)
        self.canvas.bind('<Configure>', self._sync)

    def _sync(self, _event=None):
        w = self.canvas.winfo_width()
        if w <= 1:
            # 아직 배치 전이면 잠시 뒤 다시 시도한다. after_idle이 아니라 타이머로 거는 게
            # 중요한데, after_idle로 걸면 update_idletasks()가 이 콜백을 처리하고 그 안에서
            # 다시 등록되는 일이 반복돼 update_idletasks()가 영원히 안 끝난다.
            self.after(16, self._sync)
            return
        body_w = max(1, w - 2 * self.inset)
        self.canvas.itemconfig(self._window_id, width=body_w)
        if self.expand_mode:
            # 콘텐츠 크기가 아니라 부모가 준 만큼(fill='both', expand=True)의 공간을 그대로 채운다
            # - 실시간 로그 패널처럼 남는 세로 공간을 다 차지해야 하는 카드용.
            h_avail = self.canvas.winfo_height()
            body_h = max(1, h_avail - 2 * self.inset)
            self.canvas.itemconfig(self._window_id, height=body_h)
            total_h = h_avail
        else:
            self.body.update_idletasks()
            body_h = self.body.winfo_reqheight()
            total_h = body_h + 2 * self.inset
            if self.canvas.winfo_height() != total_h:
                self.canvas.configure(height=total_h)
        self._redraw(w, total_h)

    def _redraw(self, w, h):
        self.canvas.delete('card_bg')
        points = _rounded_rect_points(1, 1, w - 1, h - 1, self.radius)
        self.canvas.create_polygon(points, smooth=True, fill=self.card_bg,
                                    outline=self.border_color, width=1, tags='card_bg')
        self.canvas.tag_lower('card_bg')


class RoundedButton(tk.Canvas):
    """Canvas에 직접 그리는 둥근 버튼. ttk.Button은 모서리를 둥글릴 수 없어서
    ExpressVPN류의 세련된 느낌을 내기 위해 이걸로 대체한다.
    variant: 'accent'(주요 동작) / 'danger'(위험한 동작) / 'neutral'(보조 동작,
    채워진 배경) / 'ghost'(테두리만, 보조 중에서도 가장 가벼운 동작)."""

    _VARIANTS = {
        'accent': {'bg': ACCENT, 'hover': ACCENT_HOVER, 'fg': ON_ACCENT, 'outline': None},
        'danger': {'bg': CRITICAL, 'hover': '#A82317', 'fg': ON_DANGER, 'outline': None},
        'neutral': {'bg': PANEL_LIGHT, 'hover': BORDER, 'fg': FG, 'outline': BORDER},
        'ghost': {'bg': None, 'hover': ACCENT_SOFT, 'fg': FG, 'outline': BORDER},
        # 사이드바 내비게이션 항목용 - 배경과 자연스럽게 섞이다가 선택되면 은은한
        # 강조 배경의 "필(pill)"로 떠 보이는 스타일 (NordVPN류 아이콘 레일 참고).
        'nav': {'bg': None, 'hover': ACCENT_SOFT, 'fg': FG_MUTED, 'outline': None},
        'nav_selected': {'bg': ACCENT_SOFT, 'hover': ACCENT_SOFT, 'fg': ACCENT_HOVER, 'outline': None},
    }

    def __init__(self, parent, text, command=None, variant='neutral', radius=10,
                 page_bg=None, font=None, padx=18, pady=10, wrap_width=None):
        page_bg = page_bg if page_bg is not None else BG
        super().__init__(parent, bg=page_bg, highlightthickness=0)
        self.command = command
        self.variant = variant
        self.radius = radius
        self.text = text
        self.font = font or (FONT_UI, TYPE_BODY, 'bold')
        self.padx = padx
        self.pady = pady
        # wrap_width: 버튼 폭이 미리 정해진 경우(예: 고정폭 사이드바) 긴 라벨이
        # 캔버스 밖으로 잘리지 않고 줄바꿈되도록 강제할 너비(px). None이면 기존처럼
        # 텍스트 폭 그대로 한 줄로 측정한다.
        self.wrap_width = wrap_width
        self._enabled = True

        style = self._VARIANTS[variant]
        self._bg_color = style['bg'] if style['bg'] is not None else page_bg
        self._hover_color = style['hover']
        self._fg_color = style['fg']
        self._outline_color = style['outline']
        self._current_bg = self._bg_color

        self.bind('<Configure>', lambda e: self._redraw())
        self.bind('<Enter>', self._on_enter)
        self.bind('<Leave>', self._on_leave)
        self.bind('<ButtonRelease-1>', self._on_release)

        self._measure_and_set_size()
        self._redraw()

    def _measure_and_set_size(self):
        text_kwargs = {'width': self.wrap_width} if self.wrap_width else {}
        tmp_id = self.create_text(0, 0, text=self.text, font=self.font, justify='center', **text_kwargs)
        bbox = self.bbox(tmp_id)
        self.delete(tmp_id)
        text_w = self.wrap_width if self.wrap_width else bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        self.configure(width=text_w + self.padx * 2, height=text_h + self.pady * 2)

    def _redraw(self):
        self.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1 or h <= 1:
            return
        if not self._enabled:
            fill, text_fg = BORDER, FG_MUTED
        else:
            fill, text_fg = self._current_bg, self._fg_color
        outline = self._outline_color if self._outline_color else fill
        points = _rounded_rect_points(1, 1, w - 1, h - 1, self.radius)
        self.create_polygon(points, smooth=True, fill=fill, outline=outline, width=1, tags='btn_bg')
        # wrap_width가 있으면 좁은 고정폭 버튼(사이드바 등)에서 긴 라벨이 밖으로
        # 잘리지 않고 자동 줄바꿈되도록 캔버스 텍스트에도 같은 폭을 강제한다.
        text_kwargs = {'width': self.wrap_width} if self.wrap_width else {}
        self.create_text(w / 2, h / 2, text=self.text, font=self.font, fill=text_fg, justify='center', **text_kwargs)

    def _on_enter(self, _event):
        if self._enabled:
            self._current_bg = self._hover_color
            self._redraw()
            self.configure(cursor='hand2')

    def _on_leave(self, _event):
        self._current_bg = self._bg_color
        self._redraw()
        self.configure(cursor='')

    def _on_release(self, event):
        if (self._enabled and self.command
                and 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()):
            self.command()

    def set_enabled(self, enabled):
        self._enabled = enabled
        self._current_bg = self._bg_color
        self._redraw()

    def set_text(self, text):
        self.text = text
        self._measure_and_set_size()
        self._redraw()

    def set_variant(self, variant):
        """사이드바 내비게이션처럼 같은 버튼이 선택/비선택 상태에 따라
        색상 variant를 바꿔야 하는 경우를 위한 헬퍼."""
        self.variant = variant
        style = self._VARIANTS[variant]
        self._bg_color = style['bg'] if style['bg'] is not None else self.cget('bg')
        self._hover_color = style['hover']
        self._fg_color = style['fg']
        self._outline_color = style['outline']
        self._current_bg = self._bg_color
        self._redraw()


class ToggleSwitch(tk.Canvas):
    """ExpressVPN류 앱에서 흔한 초록색 알약 모양 ON/OFF 스위치. tk.BooleanVar와
    직접 연동되어 값이 (다른 코드에 의해) 바뀌면 자동으로 다시 그려지고,
    클릭하면 값을 뒤집는다 - 기존 ttk.Checkbutton을 그대로 대체할 수 있다."""

    def __init__(self, parent, variable, command=None, page_bg=None, width=44, height=24):
        page_bg = page_bg if page_bg is not None else PANEL
        super().__init__(parent, width=width, height=height, bg=page_bg, highlightthickness=0)
        self.variable = variable
        self.command = command
        self.w, self.h = width, height
        self.bind('<Button-1>', self._on_click)
        self.bind('<Enter>', lambda e: self.configure(cursor='hand2'))
        self._trace_id = variable.trace_add('write', lambda *a: self._redraw())
        self.bind('<Destroy>', self._on_destroy)
        self._redraw()

    def _on_destroy(self, _event=None):
        try:
            self.variable.trace_remove('write', self._trace_id)
        except Exception:
            pass

    def _on_click(self, _event=None):
        self.variable.set(not self.variable.get())
        if self.command:
            self.command()

    def _redraw(self):
        self.delete('all')
        on = bool(self.variable.get())
        track_color = SUCCESS if on else BORDER
        r = self.h / 2
        points = _rounded_rect_points(1, 1, self.w - 1, self.h - 1, r)
        self.create_polygon(points, smooth=True, fill=track_color, outline=track_color, tags='track')
        knob_r = r - 3
        cx = self.w - r if on else r
        self.create_oval(cx - knob_r, r - knob_r, cx + knob_r, r + knob_r, fill='#FFFFFF', outline='#FFFFFF')


class PreferencesDialog(tk.Toplevel):
    """ExpressVPN류 앱의 "아이콘 + 굵은 제목 + 회색 설명 + 우측 컨트롤(토글/드롭다운/입력)"
    행 패턴 + 행 사이 구분선으로 구성. pack 기반이라 grid 행 번호를 손으로 맞추다
    생기는 겹침 버그를 원천적으로 피한다."""

    def __init__(self, parent, settings, on_save):
        super().__init__(parent)
        self.title(t('prefs_title'))
        self.configure(bg=BG)
        self.geometry('900x840')
        self.minsize(720, 560)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.settings = settings
        self.on_save = on_save

        # 저장/취소 버튼은 스크롤 영역 밖(Toplevel에 직접) 고정한다. 예전에는 맨 아래
        # AI 섹션 뒤에 있어서, 설정(언어 등)을 바꾸고 끝까지 스크롤하지 않은 채 창을
        # 닫으면 저장이 안 된 채 사라지는 문제가 있었다 - 항상 보이게 해서 방지.
        footer = tk.Frame(self, bg=BG)
        footer.pack(side='bottom', fill='x', padx=20, pady=(0, 16))
        tk.Frame(footer, bg=BORDER, height=1).pack(fill='x', pady=(0, 12))
        btn_row = ttk.Frame(footer)
        btn_row.pack(fill='x')
        RoundedButton(btn_row, t('btn_save'), command=self._save, variant='accent').pack(side='right', padx=(6, 0))
        RoundedButton(btn_row, t('btn_cancel'), command=self.destroy, variant='ghost').pack(side='right')

        # 내용이 창보다 길어져도(글자 크기를 키우거나 설정이 늘어나도) 잘리지 않도록
        # 스크롤 가능한 캔버스 안에 실제 내용을 넣는다.
        outer = make_scrollable(self)
        outer.configure(padding=20)

        ttk.Label(outer, text=t('prefs_title'), style='Title2.TLabel').pack(anchor='w', pady=(0, 2))
        ttk.Label(outer, text=t('prefs_subtitle'), style='Sub.TLabel').pack(anchor='w', pady=(0, 14))

        # --- 연결 ---
        sec1 = self._section(outer, t('section_connection'))
        self.ua_var = tk.StringVar(value=settings['user_agent'])
        self._row(sec1, '🧭', t('label_user_agent'), t('caption_user_agent'),
                  lambda p: ttk.Entry(p, textvariable=self.ua_var).pack(fill='x', ipady=3), full_width=True)

        self.conn_var = tk.StringVar(value=str(settings['connections']))
        self._row(sec1, '🔌', t('label_connections'), t('caption_connections'),
                  lambda p: ttk.Spinbox(p, from_=1, to=32, textvariable=self.conn_var, width=8).pack())
        self.retry_var = tk.StringVar(value=str(settings['retries']))
        self._row(sec1, '🔁', t('label_retries'), t('caption_retries'),
                  lambda p: ttk.Spinbox(p, from_=0, to=10, textvariable=self.retry_var, width=8).pack())

        # --- 속도 & 시간 ---
        sec2 = self._section(outer, t('section_speed_time'))
        self.timeout_var = tk.StringVar(value=str(settings['timeout']))
        self._row(sec2, '⏱', t('label_timeout'), t('caption_timeout'),
                  lambda p: ttk.Spinbox(p, from_=5, to=600, increment=5, textvariable=self.timeout_var,
                                        width=8).pack())
        self.rate_var = tk.StringVar(value=str(settings['max_rate']))
        self._row(sec2, '🚀', t('label_max_rate'), t('caption_max_rate'),
                  lambda p: ttk.Spinbox(p, from_=0, to=100_000_000, increment=1000, textvariable=self.rate_var,
                                        width=12).pack())

        # --- 정책 ---
        sec3 = self._section(outer, t('section_policy'))
        robots_options = get_robots_options()
        self.robots_var = tk.StringVar(value=next(
            (label for code, label in robots_options if code == str(settings['robots'])), robots_options[2][1]))
        self._row(sec3, '🤖', t('label_robots'), t('caption_robots'),
                  lambda p: ttk.Combobox(p, textvariable=self.robots_var, state='readonly', width=16,
                                         values=[label for _, label in robots_options]).pack())

        self.external_var = tk.BooleanVar(value=bool(settings.get('external_links', False)))
        self._row(sec3, '🔗', t('label_external_links'), t('caption_external_links'),
                  lambda p: ToggleSwitch(p, variable=self.external_var, page_bg=PANEL).pack())

        # --- 네트워크 ---
        sec4 = self._section(outer, t('section_network'))
        self.proxy_var = tk.StringVar(value=settings['proxy'])
        self._row(sec4, '🛰', t('label_proxy'), t('caption_proxy'),
                  lambda p: ttk.Entry(p, textvariable=self.proxy_var, width=32).pack(ipady=3))

        self.use_local_cookies_var = tk.BooleanVar(value=bool(settings.get('use_local_cookies', False)))
        self._row(sec4, '🍪', t('label_use_local_cookies'), t('caption_use_local_cookies'),
                  lambda p: ToggleSwitch(p, variable=self.use_local_cookies_var, page_bg=PANEL).pack())

        # --- 언어 ---
        sec5 = self._section(outer, t('section_language'))
        current_lang = settings.get('language', 'en')
        self.lang_var = tk.StringVar(value=LANG_DISPLAY.get(current_lang, LANG_DISPLAY['en']))
        self._row(sec5, '🌐', t('label_language'), t('caption_language'),
                  lambda p: ttk.Combobox(p, textvariable=self.lang_var, state='readonly', width=14,
                                         values=[LANG_DISPLAY['en'], LANG_DISPLAY['ko']]).pack())

        # --- 고급 ---
        sec6 = self._section(outer, t('section_advanced'))
        self.referer_var = tk.StringVar(value=settings.get('referer', ''))
        self._row(sec6, '🔗', t('label_referer'), t('caption_referer'),
                  lambda p: ttk.Entry(p, textvariable=self.referer_var).pack(fill='x', ipady=3), full_width=True)

        self.lang_header_var = tk.StringVar(value=settings.get('lang_header', ''))
        self._row(sec6, '🗣', t('label_lang_header'), t('caption_lang_header'),
                  lambda p: ttk.Entry(p, textvariable=self.lang_header_var, width=26).pack(ipady=3))

        self.custom_headers_text = tk.Text(sec6, height=3, bg=PANEL_LIGHT, fg=FG, insertbackground=FG,
                                            relief='flat', font=(FONT_MONO, 10), highlightthickness=1,
                                            highlightbackground=BORDER, highlightcolor=ACCENT, padx=6, pady=4)
        self.custom_headers_text.insert('1.0', settings.get('custom_headers', ''))
        def _custom_headers_control(p):
            self.custom_headers_text.pack(in_=p, fill='x')
        self._row(sec6, '🧩', t('label_custom_headers'), t('caption_custom_headers'),
                  _custom_headers_control, full_width=True)

        def _cookies_control(p):
            row = ttk.Frame(p, style='Panel.TFrame')
            row.pack(fill='x')
            ttk.Entry(row, textvariable=self.cookies_file_var).pack(side='left', fill='x', expand=True, ipady=3)
            RoundedButton(row, t('btn_browse'), command=self._browse_cookies_file,
                          variant='ghost', page_bg=PANEL).pack(side='left', padx=(6, 0))
        self.cookies_file_var = tk.StringVar(value=settings.get('cookies_file', ''))
        self._row(sec6, '🍪', t('label_cookies_file'), t('caption_cookies_file'), _cookies_control, full_width=True)

        link_format_options = [
            ('relative', t('link_format_relative')),
            ('absolute', t('link_format_absolute')),
            ('original', t('link_format_original')),
        ]
        self.link_format_var = tk.StringVar(value=next(
            (label for code, label in link_format_options if code == settings.get('link_format', 'relative')),
            link_format_options[0][1]))
        self._link_format_options = link_format_options
        self._row(sec6, '🔀', t('label_link_format'), t('caption_link_format'),
                  lambda p: ttk.Combobox(p, textvariable=self.link_format_var, state='readonly', width=16,
                                         values=[label for _, label in link_format_options]).pack())

        self.conn_per_sec_var = tk.StringVar(value=str(settings.get('conn_per_sec', 0)))
        self._row(sec6, '⚡', t('label_conn_per_sec'), t('caption_conn_per_sec'),
                  lambda p: ttk.Spinbox(p, from_=0, to=100, textvariable=self.conn_per_sec_var, width=8).pack())

        self.near_files_var = tk.BooleanVar(value=bool(settings.get('near_files', False)))
        self._row(sec6, '📎', t('label_near_files'), t('caption_near_files'),
                  lambda p: ToggleSwitch(p, variable=self.near_files_var, page_bg=PANEL).pack())

        self.warc_var = tk.BooleanVar(value=bool(settings.get('warc', False)))
        self._row(sec6, '📦', t('label_warc'), t('caption_warc'),
                  lambda p: ToggleSwitch(p, variable=self.warc_var, page_bg=PANEL).pack())

        self.search_index_var = tk.BooleanVar(value=bool(settings.get('search_index', False)))
        self._row(sec6, '🔍', t('label_search_index'), t('caption_search_index'),
                  lambda p: ToggleSwitch(p, variable=self.search_index_var, page_bg=PANEL).pack())

        # --- AI 크롤링 ---
        sec7 = self._section(outer, t('section_ai'))
        self._provider_options = [(p, ai_extract.PROVIDER_DISPLAY_NAMES[p]) for p in ai_extract.PROVIDERS]
        current_provider = settings.get('ai_provider', 'anthropic')
        self.ai_provider_var = tk.StringVar(value=next(
            (label for code, label in self._provider_options if code == current_provider),
            self._provider_options[0][1]))
        self._row(sec7, '🧠', t('label_ai_provider'), t('caption_ai_provider'),
                  lambda p: ttk.Combobox(p, textvariable=self.ai_provider_var, state='readonly', width=18,
                                         values=[label for _, label in self._provider_options]).pack())

        self.anthropic_key_var = tk.StringVar(value=settings.get('anthropic_api_key', ''))
        self._row(sec7, '🔑', t('label_api_key_anthropic'), None,
                  lambda p: ttk.Entry(p, textvariable=self.anthropic_key_var, show='*').pack(
                      fill='x', ipady=3), full_width=True)
        self.openai_key_var = tk.StringVar(value=settings.get('openai_api_key', ''))
        self._row(sec7, '🔑', t('label_api_key_openai'), None,
                  lambda p: ttk.Entry(p, textvariable=self.openai_key_var, show='*').pack(
                      fill='x', ipady=3), full_width=True)
        self.gemini_key_var = tk.StringVar(value=settings.get('gemini_api_key', ''))
        self._row(sec7, '🔑', t('label_api_key_gemini'), t('caption_api_key'),
                  lambda p: ttk.Entry(p, textvariable=self.gemini_key_var, show='*').pack(
                      fill='x', ipady=3), full_width=True)

    def _section(self, parent, title):
        card = RoundedCard(parent, radius=14, padding=16)
        card.pack(fill='x', pady=(0, 12))
        ttk.Label(card.body, text=title, style='Header.TLabel').pack(anchor='w', pady=(0, 6))
        return card.body

    def _row(self, parent, icon, title, caption, control_factory, full_width=False):
        """아이콘 + 굵은 제목 + 회색 설명(좌측) + 우측(또는 하단, full_width) 컨트롤
        한 행 + 아래 구분선. ExpressVPN 설정 화면의 행 패턴을 그대로 따른다."""
        row = ttk.Frame(parent, style='Panel.TFrame')
        row.pack(fill='x', pady=(10, 10))

        top = ttk.Frame(row, style='Panel.TFrame')
        top.pack(fill='x')
        left = ttk.Frame(top, style='Panel.TFrame')
        left.pack(side='left', fill='x', expand=True)
        title_row = ttk.Frame(left, style='Panel.TFrame')
        title_row.pack(anchor='w', fill='x')
        tk.Label(title_row, text=icon, bg=PANEL, fg=FG_MUTED, font=(FONT_UI, TYPE_BODY_LARGE)).pack(
            side='left', padx=(0, 10))
        ttk.Label(title_row, text=title, style='RowTitle.TLabel').pack(side='left', anchor='w')
        if caption:
            ttk.Label(left, text=caption, style='Caption.TLabel', wraplength=380).pack(
                anchor='w', padx=(34, 0), pady=(2, 0))

        if full_width:
            control_parent = ttk.Frame(row, style='Panel.TFrame')
            control_parent.pack(fill='x', pady=(8, 0), padx=(34, 0))
        else:
            control_parent = ttk.Frame(top, style='Panel.TFrame')
            control_parent.pack(side='right')
        control_factory(control_parent)

        tk.Frame(parent, bg=BORDER, height=1).pack(fill='x')
        return row

    def _browse_cookies_file(self):
        selected = filedialog.askopenfilename(title=t('dialog_cookies_file_title'), parent=self)
        if selected:
            self.cookies_file_var.set(selected)

    def _save(self):
        robots_options = get_robots_options()
        robots_code = next((code for code, label in robots_options if label == self.robots_var.get()), '2')
        lang_code = next((code for code, name in LANG_DISPLAY.items() if name == self.lang_var.get()), 'en')
        link_format_code = next(
            (code for code, label in self._link_format_options if label == self.link_format_var.get()), 'relative')
        self.settings['user_agent'] = self.ua_var.get().strip()
        self.settings['connections'] = int(self.conn_var.get() or DEFAULT_SETTINGS['connections'])
        self.settings['retries'] = int(self.retry_var.get() or DEFAULT_SETTINGS['retries'])
        self.settings['timeout'] = int(self.timeout_var.get() or DEFAULT_SETTINGS['timeout'])
        self.settings['max_rate'] = int(self.rate_var.get() or 0)
        self.settings['robots'] = robots_code
        self.settings['external_links'] = bool(self.external_var.get())
        self.settings['proxy'] = self.proxy_var.get().strip()
        self.settings['language'] = lang_code
        self.settings['referer'] = self.referer_var.get().strip()
        self.settings['lang_header'] = self.lang_header_var.get().strip()
        self.settings['custom_headers'] = self.custom_headers_text.get('1.0', 'end').strip()
        self.settings['cookies_file'] = self.cookies_file_var.get().strip()
        self.settings['link_format'] = link_format_code
        self.settings['near_files'] = bool(self.near_files_var.get())
        self.settings['conn_per_sec'] = int(self.conn_per_sec_var.get() or 0)
        self.settings['warc'] = bool(self.warc_var.get())
        self.settings['search_index'] = bool(self.search_index_var.get())
        provider_code = next(
            (code for code, label in self._provider_options if label == self.ai_provider_var.get()), 'anthropic')
        self.settings['ai_provider'] = provider_code
        self.settings['anthropic_api_key'] = self.anthropic_key_var.get().strip()
        self.settings['openai_api_key'] = self.openai_key_var.get().strip()
        self.settings['gemini_api_key'] = self.gemini_key_var.get().strip()
        self.settings['use_local_cookies'] = bool(self.use_local_cookies_var.get())
        save_settings(self.settings)
        self.on_save()
        self.destroy()


class ExistingMirrorDialog(tk.Toplevel):
    """같은 폴더에 이미 받아둔 미러가 있을 때, 다시 통째로 받을지 바뀐 것만 받을지 물어본다.
    HTTrack은 원래 업데이트(-iC2)/이어받기(-iC1)를 지원하지만 사용자가 '수집 방식'에서
    직접 골라야만 해서, 모르면 매번 처음부터 다시 받게 된다. 그래서 먼저 물어본다.
    on_choose(action_code)로 선택한 HTTrack 액션 코드를 돌려준다."""

    def __init__(self, parent, kind, on_choose):
        super().__init__(parent)
        self.on_choose = on_choose
        self.title(t('existing_title'))
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        interrupted = (kind == 'interrupted')
        outer = ttk.Frame(self, padding=24)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer,
                  text=t('existing_header_interrupted') if interrupted else t('existing_header_complete'),
                  style='Title2.TLabel').pack(anchor='w')
        ttk.Label(outer,
                  text=t('existing_body_interrupted') if interrupted else t('existing_body_complete'),
                  style='Sub.TLabel', wraplength=470, justify='left').pack(anchor='w', pady=(6, 16))

        # 상황에 맞는 쪽을 첫 번째(추천)로 올린다.
        if interrupted:
            choices = [('5', t('existing_resume'), t('existing_resume_desc'), True),
                       ('1', t('existing_fresh'), t('existing_fresh_desc'), False)]
        else:
            choices = [('4', t('existing_update'), t('existing_update_desc'), True),
                       ('1', t('existing_fresh'), t('existing_fresh_desc'), False)]

        for code, title, desc, recommended in choices:
            card = RoundedCard(outer, page_bg=BG, card_bg=PANEL,
                               border=ACCENT if recommended else BORDER,
                               radius=13, inset=6, padding=(14, 11))
            card.pack(fill='x', pady=(0, 8))
            tk.Label(card.body, text=title, bg=PANEL, fg=FG,
                     font=(FONT_UI, TYPE_BODY, 'bold')).pack(anchor='w')
            tk.Label(card.body, text=desc, bg=PANEL, fg=FG_MUTED, font=(FONT_UI, TYPE_CAPTION),
                     wraplength=440, justify='left').pack(anchor='w', pady=(2, 0))

            def _pick(_event=None, c=code):
                self._choose(c)

            for w in (card, card.canvas, card.body, *card.body.winfo_children()):
                w.bind('<Button-1>', _pick)
                try:
                    w.configure(cursor='hand2')
                except tk.TclError:
                    pass

        RoundedButton(outer, t('btn_cancel'), command=self.destroy,
                      variant='ghost').pack(anchor='e', pady=(6, 0))

        self.geometry('520x400')
        self.after(120, self._fit)

    def _fit(self):
        self.update_idletasks()
        h = self.winfo_children()[0].winfo_reqheight()
        parent = self.master
        px = parent.winfo_rootx() + (parent.winfo_width() - 520) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f'520x{h}+{max(px, 0)}+{max(py, 0)}')

    def _choose(self, action_code):
        self.destroy()
        self.on_choose(action_code)


class StartConfirmDialog(tk.Toplevel):
    """시작 전에 설정을 요약해서 보여주고 진짜 시작할지 한 번 더 확인받는 창."""

    def __init__(self, parent, summary_items, on_confirm):
        super().__init__(parent)
        self.title(t('confirm_title'))
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.on_confirm = on_confirm

        # 창 폭을 먼저 고정하고 값 라벨을 그 안에서 줄바꿈시킨다. 폭을 내용에 맞춰
        # 재려고 하면, 카드가 내부 프레임 폭을 캔버스 폭에 맞춰 강제하는 특성 때문에
        # 긴 저장 경로/수집 방식 이름이 잘려버린다.
        dialog_w = 640
        label_col_w = 150
        # outer padding(24*2) + 카드 inset(14*2) + 카드 padding(16*2) + 라벨 열 + 열 간격
        value_wrap = dialog_w - 24 * 2 - 14 * 2 - 16 * 2 - label_col_w - 12 - 8

        outer = ttk.Frame(self, padding=24)
        outer.pack(fill='both', expand=True)

        ttk.Label(outer, text=t('confirm_header'), style='Title2.TLabel').pack(anchor='w', pady=(0, 14))

        card = RoundedCard(outer, radius=14, padding=16)
        card.pack(fill='x')
        grid = ttk.Frame(card.body, style='Panel.TFrame')
        grid.pack(fill='x')
        grid.grid_columnconfigure(0, minsize=label_col_w)
        grid.grid_columnconfigure(1, weight=1)
        for i, (label, value) in enumerate(summary_items):
            ttk.Label(grid, text=label, style='Muted.TLabel').grid(
                row=i, column=0, sticky='nw', pady=4, padx=(0, 12))
            ttk.Label(grid, text=str(value), style='Panel.TLabel',
                      wraplength=value_wrap, justify='left').grid(row=i, column=1, sticky='w', pady=4)

        btn_frame = ttk.Frame(outer)
        btn_frame.pack(fill='x', pady=(18, 0))
        RoundedButton(btn_frame, t('btn_no'), command=self.destroy, variant='ghost').pack(side='right')
        RoundedButton(btn_frame, t('btn_start'), command=self._confirm, variant='accent').pack(
            side='right', padx=(0, 8))

        # 폭을 먼저 확정해 카드가 그 폭에 맞춰 배치되게 하고, 높이는 카드가 자기
        # 높이를 잡은 뒤(타이머) 다시 재서 적용한다 - 곧바로 재면 아직 덜 잡힌
        # 높이가 나와 내용이 잘린다.
        self._dialog_w = dialog_w
        self._outer = outer
        self._parent = parent
        self.geometry(f'{dialog_w}x320')
        self.after(120, self._fit_to_content)

    def _fit_to_content(self):
        self.update_idletasks()
        h = self._outer.winfo_reqheight()
        parent = self._parent
        px = parent.winfo_rootx() + (parent.winfo_width() - self._dialog_w) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f'{self._dialog_w}x{h}+{max(px, 0)}+{max(py, 0)}')

    def _confirm(self):
        self.destroy()
        self.on_confirm()


class ScheduleJobDialog(tk.Toplevel):
    """예약 크롤링 작업을 새로 만들거나 수정하는 창. 저장 시 Windows 작업 스케줄러에도 등록한다."""

    MODE_OPTIONS = [('httrack', 'job_mode_httrack'), ('smart', 'job_mode_smart'), ('both', 'job_mode_both')]
    SCHEDULE_OPTIONS = [('once', 'schedule_type_once'), ('daily', 'schedule_type_daily'), ('weekly', 'schedule_type_weekly')]
    WEEKDAYS = [('MON', 'weekday_mon'), ('TUE', 'weekday_tue'), ('WED', 'weekday_wed'), ('THU', 'weekday_thu'),
                ('FRI', 'weekday_fri'), ('SAT', 'weekday_sat'), ('SUN', 'weekday_sun')]

    def __init__(self, parent, on_save, log_fn, settings, existing_job=None):
        super().__init__(parent)
        self.title(t('dialog_job_title'))
        self.configure(bg=BG)
        self.geometry('560x760')
        self.minsize(480, 420)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.on_save = on_save
        self.log_fn = log_fn
        self.settings = settings
        self.existing_job = existing_job

        outer = make_scrollable(self)
        outer.configure(padding=20)

        ttk.Label(outer, text=t('dialog_job_title'), style='Title2.TLabel').pack(anchor='w', pady=(0, 14))

        ttk.Label(outer, text=t('label_job_name'), style='MutedRoot.TLabel').pack(anchor='w')
        self.name_var = tk.StringVar(value=(existing_job or {}).get('name', ''))
        ttk.Entry(outer, textvariable=self.name_var).pack(fill='x', pady=(4, 12), ipady=3)

        ttk.Label(outer, text=t('label_save_location'), style='MutedRoot.TLabel').pack(anchor='w')
        path_row = ttk.Frame(outer)
        path_row.pack(fill='x', pady=(4, 12))
        self.save_path_var = tk.StringVar(value=(existing_job or {}).get('save_path', ''))
        ttk.Entry(path_row, textvariable=self.save_path_var).pack(side='left', fill='x', expand=True, ipady=3)
        RoundedButton(path_row, t('btn_browse'), command=self._browse_path, variant='ghost').pack(
            side='left', padx=(6, 0))

        ttk.Label(outer, text=t('label_urls'), style='MutedRoot.TLabel').pack(anchor='w')
        self.urls_text = tk.Text(outer, height=3, bg=PANEL_LIGHT, fg=FG, insertbackground=FG,
                                  relief='flat', font=(FONT_MONO, 10), highlightthickness=1,
                                  highlightbackground=BORDER, highlightcolor=ACCENT, padx=8, pady=6)
        self.urls_text.insert('1.0', '\n'.join((existing_job or {}).get('urls', [])))
        self.urls_text.pack(fill='x', pady=(4, 12))

        ttk.Label(outer, text=t('label_job_mode'), style='MutedRoot.TLabel').pack(anchor='w')
        current_mode = (existing_job or {}).get('mode', 'httrack')
        self.mode_var = tk.StringVar(value=next(
            (t(key) for code, key in self.MODE_OPTIONS if code == current_mode), t(self.MODE_OPTIONS[0][1])))
        ttk.Combobox(outer, textvariable=self.mode_var, state='readonly',
                     values=[t(key) for _, key in self.MODE_OPTIONS]).pack(fill='x', pady=(4, 12), ipady=2)

        ttk.Label(outer, text=t('label_schedule_type'), style='MutedRoot.TLabel').pack(anchor='w')
        schedule = (existing_job or {}).get('schedule', {})
        current_type = schedule.get('type', 'daily')
        self.schedule_type_var = tk.StringVar(value=next(
            (t(key) for code, key in self.SCHEDULE_OPTIONS if code == current_type), t(self.SCHEDULE_OPTIONS[1][1])))
        ttk.Combobox(outer, textvariable=self.schedule_type_var, state='readonly',
                     values=[t(key) for _, key in self.SCHEDULE_OPTIONS]).pack(fill='x', pady=(4, 12), ipady=2)

        time_row = ttk.Frame(outer)
        time_row.pack(fill='x', pady=(0, 12))
        ttk.Label(time_row, text=t('label_schedule_time'), style='MutedRoot.TLabel').pack(side='left')
        at_value = schedule.get('at', '09:00')
        h, m = (at_value.split(':') + ['00'])[:2]
        self.hour_var = tk.StringVar(value=h)
        self.minute_var = tk.StringVar(value=m)
        ttk.Spinbox(time_row, from_=0, to=23, textvariable=self.hour_var, width=4, format='%02.0f').pack(
            side='left', padx=(10, 2))
        ttk.Label(time_row, text=':').pack(side='left')
        ttk.Spinbox(time_row, from_=0, to=59, textvariable=self.minute_var, width=4, format='%02.0f').pack(
            side='left', padx=(2, 0))

        ttk.Label(outer, text=t('label_schedule_date'), style='MutedRoot.TLabel').pack(anchor='w')
        self.date_var = tk.StringVar(value=schedule.get('date') or '')
        ttk.Entry(outer, textvariable=self.date_var).pack(fill='x', pady=(4, 12), ipady=3)

        ttk.Label(outer, text=t('label_schedule_weekdays'), style='MutedRoot.TLabel').pack(anchor='w', pady=(0, 4))
        weekday_row = ttk.Frame(outer)
        weekday_row.pack(fill='x', pady=(0, 4))
        existing_weekdays = set(schedule.get('weekdays', []))
        self.weekday_vars = []
        for code, key in self.WEEKDAYS:
            var = tk.BooleanVar(value=code in existing_weekdays)
            self.weekday_vars.append((code, var))
            ttk.Checkbutton(weekday_row, text=t(key), variable=var).pack(side='left', padx=(0, 6))

        caption_box = tk.Frame(outer, bg=ACCENT_SOFT)
        caption_box.pack(fill='x', pady=(10, 0))
        tk.Label(caption_box, text=t('caption_schedule_note'), bg=ACCENT_SOFT, fg=FG,
                 font=(FONT_UI, TYPE_CAPTION), wraplength=480, justify='left', padx=12, pady=10).pack(anchor='w')

        # 크롤링 방식(HTTrack 정적/스마트 브라우저)과 무관하게, 받아온 폴더에
        # 대해 동작하는 후처리 단계라 여기 같이 둔다.
        self.ai_panel = AIExtractPanel(
            outer, get_ai_config=lambda: get_active_ai_config(self.settings),
            log_fn=self.log_fn, get_sample_html=self._get_sample_html,
            existing=(existing_job or {}).get('ai_extract'))

        btn_frame = ttk.Frame(outer)
        btn_frame.pack(fill='x', pady=(16, 0))
        RoundedButton(btn_frame, t('btn_save'), command=self._save, variant='accent').pack(
            side='right', padx=(6, 0))
        RoundedButton(btn_frame, t('btn_cancel'), command=self.destroy, variant='ghost').pack(side='right')

    def _browse_path(self):
        selected = filedialog.askdirectory(title=t('dialog_browse_folder_title'), parent=self)
        if selected:
            self.save_path_var.set(selected)

    def _get_sample_html(self):
        urls = [u.strip() for u in self.urls_text.get('1.0', 'end').split('\n') if u.strip()]
        if not urls:
            return None
        return _fetch_sample_html_from_url(urls[0])

    def _save(self):
        name = self.name_var.get().strip()
        urls = [u.strip() for u in self.urls_text.get('1.0', 'end').split('\n') if u.strip()]
        if not name:
            self.log_fn(t('warn_job_need_name'))
            return
        if not urls:
            self.log_fn(t('warn_job_need_url'))
            return

        mode = next((code for code, key in self.MODE_OPTIONS if t(key) == self.mode_var.get()), 'httrack')
        sched_type = next((code for code, key in self.SCHEDULE_OPTIONS if t(key) == self.schedule_type_var.get()),
                           'daily')
        at_value = f'{int(self.hour_var.get()):02d}:{int(self.minute_var.get()):02d}'
        date_value = self.date_var.get().strip() or None
        if sched_type == 'once':
            if not date_value:
                self.log_fn(t('warn_job_need_date'))
                return
            try:
                datetime.strptime(date_value, '%Y-%m-%d')
            except ValueError:
                self.log_fn(t('warn_job_invalid_date'))
                return
        weekdays = [code for code, var in self.weekday_vars if var.get()]

        schedule = {'type': sched_type, 'at': at_value, 'date': date_value, 'weekdays': weekdays}
        httrack_opts = {'action': '1', 'depth': None, 'filters': list(BASE_FILTER_RULES)}
        smart_opts = {'wait_until': 'networkidle', 'max_pages': 50}
        ai_extract_cfg = self.ai_panel.get_config()

        if self.existing_job is not None:
            job = dict(self.existing_job)
            job.update({'name': name, 'urls': urls, 'save_path': self.save_path_var.get().strip(),
                        'mode': mode, 'httrack': httrack_opts, 'smart': smart_opts, 'schedule': schedule,
                        'ai_extract': ai_extract_cfg})
        else:
            job = jobs_mod.new_job(name, urls, self.save_path_var.get().strip(), mode,
                                    httrack_opts, smart_opts, schedule, ai_extract=ai_extract_cfg)

        try:
            job['scheduler_task_name'] = scheduler_win.register_task(job)
        except Exception as e:
            self.log_fn(t('warn_job_schedule_failed', e=e))
            return

        self.on_save(job)
        self.destroy()


class AIExtractPanel:
    """'AI로 데이터 추출하기' 설정 UI. 예약 작업 다이얼로그와 즉시 실행 다이얼로그
    양쪽에서 그대로 재사용한다. parent 프레임 안에 위젯을 직접 그려 넣고,
    get_config()로 최종 설정 dict를 꺼낼 수 있다."""

    TYPE_OPTIONS = ['string', 'number', 'boolean']

    def __init__(self, parent, get_ai_config, log_fn, get_sample_html, existing=None):
        existing = existing or {}
        self.get_ai_config = get_ai_config
        self.log_fn = log_fn
        self.get_sample_html = get_sample_html
        self.field_rows = []

        self.enabled_var = tk.BooleanVar(value=existing.get('enabled', False))
        ttk.Checkbutton(parent, text=t('label_ai_extract_enable'),
                         variable=self.enabled_var, command=self._on_toggle).pack(anchor='w', pady=(12, 0))

        self.body = ttk.Frame(parent, style='Panel.TFrame')

        ttk.Label(self.body, text=t('label_ai_instruction'), style='Muted.TLabel').pack(anchor='w', pady=(6, 2))
        self.instruction_text = tk.Text(self.body, height=2, bg=PANEL_LIGHT, fg=FG, insertbackground=FG,
                                         relief='flat', font=(FONT_MONO, 10), highlightthickness=1,
                                         highlightbackground=BORDER, highlightcolor=ACCENT, padx=6, pady=4)
        self.instruction_text.insert('1.0', existing.get('instruction', ''))
        self.instruction_text.pack(fill='x')
        ttk.Label(self.body, text=t('caption_ai_instruction'), style='Caption.TLabel').pack(anchor='w')

        RoundedButton(self.body, t('btn_propose_fields'), command=self._on_propose,
                      variant='neutral', page_bg=PANEL).pack(anchor='w', pady=(6, 6))

        ttk.Label(self.body, text=t('label_extract_fields'), style='Muted.TLabel').pack(anchor='w')
        self.fields_frame = ttk.Frame(self.body, style='Panel.TFrame')
        self.fields_frame.pack(fill='x', pady=(2, 4))
        for f in existing.get('fields', []):
            self._add_field_row(f.get('name', ''), f.get('label', ''), f.get('type', 'string'))
        RoundedButton(self.body, t('btn_add_field'), command=lambda: self._add_field_row('', '', 'string'),
                      variant='ghost', page_bg=PANEL).pack(anchor='w', pady=(0, 8))

        export_row = ttk.Frame(self.body, style='Panel.TFrame')
        export_row.pack(fill='x', pady=(0, 4))
        ttk.Label(export_row, text=t('label_export_formats'), style='Muted.TLabel').pack(side='left')
        existing_formats = existing.get('export_formats', ['csv'])
        self.csv_var = tk.BooleanVar(value='csv' in existing_formats)
        self.json_var = tk.BooleanVar(value='json' in existing_formats)
        self.xlsx_var = tk.BooleanVar(value='xlsx' in existing_formats)
        ttk.Checkbutton(export_row, text='CSV', variable=self.csv_var).pack(side='left', padx=(10, 0))
        ttk.Checkbutton(export_row, text='JSON', variable=self.json_var).pack(side='left', padx=(10, 0))
        ttk.Checkbutton(export_row, text='Excel', variable=self.xlsx_var).pack(side='left', padx=(10, 0))

        self._on_toggle()

    def _on_toggle(self):
        if self.enabled_var.get():
            self.body.pack(fill='x')
        else:
            self.body.pack_forget()

    def _add_field_row(self, name, label, type_):
        row = ttk.Frame(self.fields_frame, style='Panel.TFrame')
        row.pack(fill='x', pady=2)
        name_var = tk.StringVar(value=name)
        label_var = tk.StringVar(value=label)
        type_var = tk.StringVar(value=type_ if type_ in self.TYPE_OPTIONS else 'string')
        ttk.Entry(row, textvariable=name_var, width=16).pack(side='left', padx=(0, 4))
        ttk.Entry(row, textvariable=label_var, width=18).pack(side='left', padx=(0, 4))
        ttk.Combobox(row, textvariable=type_var, state='readonly', values=self.TYPE_OPTIONS, width=8).pack(
            side='left', padx=(0, 4))
        entry = [name_var, label_var, type_var, row]
        RoundedButton(row, '×', command=lambda: self._remove_field_row(entry), variant='ghost',
                      page_bg=PANEL, padx=8, pady=4).pack(side='left')
        self.field_rows.append(entry)

    def _remove_field_row(self, entry):
        if entry in self.field_rows:
            self.field_rows.remove(entry)
        entry[3].destroy()

    def _on_propose(self):
        ai_config = self.get_ai_config()
        if not ai_config.get('api_key'):
            self.log_fn(t('warn_need_api_key'))
            return
        instruction = self.instruction_text.get('1.0', 'end').strip()
        if not instruction:
            self.log_fn(t('warn_need_instruction'))
            return
        sample_html = self.get_sample_html()
        if not sample_html:
            self.log_fn(t('warn_need_sample_page'))
            return
        try:
            proposed = ai_extract.propose_fields(instruction, sample_html, ai_config['api_key'],
                                                   provider=ai_config['provider'])
        except Exception as e:
            self.log_fn(t('warn_propose_failed', e=e))
            return
        for entry in list(self.field_rows):
            self._remove_field_row(entry)
        for f in proposed:
            self._add_field_row(f.get('name', ''), f.get('label', ''), f.get('type', 'string'))
        self.log_fn(t('log_fields_proposed', n=len(proposed)))

    def get_config(self):
        formats = []
        if self.csv_var.get():
            formats.append('csv')
        if self.json_var.get():
            formats.append('json')
        if self.xlsx_var.get():
            formats.append('xlsx')
        fields = [{'name': nv.get().strip(), 'label': lv.get().strip(), 'type': tv.get()}
                  for nv, lv, tv, _ in self.field_rows if nv.get().strip()]
        return {
            'enabled': self.enabled_var.get(),
            'instruction': self.instruction_text.get('1.0', 'end').strip(),
            'fields': fields,
            'export_formats': formats or ['csv'],
        }


def _fetch_sample_html_from_url(url, timeout=10):
    """필드 제안용 샘플 페이지를 간단한 HTTP GET으로 가져온다 (아직 크롤링 전이므로
    렌더링 없이 원본 HTML만 있으면 충분함). 실패하면 None."""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except Exception:
        return None


class AIExtractRunDialog(tk.Toplevel):
    """이미 받아둔 프로젝트 폴더에 대해 바로 AI 추출을 실행하는 즉시 실행 창."""

    def __init__(self, parent, out_dir, settings, log_fn, on_run):
        super().__init__(parent)
        self.title(t('dialog_ai_extract_title'))
        self.configure(bg=BG)
        self.geometry('520x600')
        self.minsize(460, 400)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.on_run = on_run

        outer = make_scrollable(self)
        outer.configure(padding=20)
        ttk.Label(outer, text=t('dialog_ai_extract_title'), style='Title2.TLabel').pack(anchor='w', pady=(0, 10))

        def get_sample():
            files = ai_extract.find_html_files(out_dir, max_files=1)
            if not files:
                return None
            with open(files[0], 'r', encoding='utf-8', errors='replace') as f:
                return f.read()

        self.ai_panel = AIExtractPanel(
            outer, get_ai_config=lambda: get_active_ai_config(settings),
            log_fn=log_fn, get_sample_html=get_sample)
        self.ai_panel.enabled_var.set(True)
        self.ai_panel._on_toggle()

        btn_frame = ttk.Frame(outer)
        btn_frame.pack(fill='x', pady=(16, 0))
        RoundedButton(btn_frame, t('btn_run_extraction'), command=self._run, variant='accent').pack(
            side='right', padx=(6, 0))
        RoundedButton(btn_frame, t('btn_cancel'), command=self.destroy, variant='ghost').pack(side='right')

    def _run(self):
        config = self.ai_panel.get_config()
        self.destroy()
        self.on_run(config)


class AIScopeRulesDialog(tk.Toplevel):
    """'추가 규칙' 옆의 AI 도우미. 자연어 목표 + 링크 샘플을 API 호출 1회로 보내서
    HTTrack 필터 규칙(+/-)을 제안받는다 - 사이트 크기와 무관하게 비용이 고정된다."""

    def __init__(self, parent, urls, settings, log_fn, on_apply):
        super().__init__(parent)
        self.title(t('dialog_ai_scope_title'))
        self.configure(bg=BG)
        self.geometry('560x560')
        self.minsize(460, 420)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.urls = urls
        self.settings = settings
        self.log_fn = log_fn
        self.on_apply = on_apply

        outer = make_scrollable(self)
        outer.configure(padding=20)
        ttk.Label(outer, text=t('dialog_ai_scope_title'), style='Title2.TLabel').pack(anchor='w', pady=(0, 10))

        ttk.Label(outer, text=t('label_scope_goal'), style='MutedRoot.TLabel').pack(anchor='w')
        self.goal_text = tk.Text(outer, height=2, bg=PANEL_LIGHT, fg=FG, insertbackground=FG,
                                  relief='flat', font=(FONT_MONO, 10), highlightthickness=1,
                                  highlightbackground=BORDER, highlightcolor=ACCENT, padx=6, pady=4)
        self.goal_text.pack(fill='x', pady=(4, 2))
        ttk.Label(outer, text=t('caption_scope_goal'), style='Caption.TLabel').pack(anchor='w')

        caption_box = tk.Frame(outer, bg=ACCENT_SOFT)
        caption_box.pack(fill='x', pady=(10, 10))
        tk.Label(caption_box, text=t('caption_scope_cost'), bg=ACCENT_SOFT, fg=FG,
                 font=(FONT_UI, TYPE_CAPTION), wraplength=480, justify='left', padx=12, pady=10).pack(anchor='w')

        RoundedButton(outer, t('btn_get_scope_rules'), command=self._on_get_rules, variant='neutral').pack(anchor='w')

        ttk.Label(outer, text=t('label_proposed_rules'), style='MutedRoot.TLabel').pack(anchor='w', pady=(14, 2))
        self.rules_text = tk.Text(outer, height=6, bg=PANEL_LIGHT, fg=FG, insertbackground=FG,
                                   relief='flat', font=(FONT_MONO, 10), highlightthickness=1,
                                   highlightbackground=BORDER, highlightcolor=ACCENT, padx=6, pady=4)
        self.rules_text.pack(fill='both', expand=True, pady=(0, 4))

        btn_frame = ttk.Frame(outer)
        btn_frame.pack(fill='x', pady=(10, 0))
        RoundedButton(btn_frame, t('btn_apply_rules'), command=self._on_apply, variant='accent').pack(
            side='right', padx=(6, 0))
        RoundedButton(btn_frame, t('btn_cancel'), command=self.destroy, variant='ghost').pack(side='right')

    def _on_get_rules(self):
        goal = self.goal_text.get('1.0', 'end').strip()
        if not goal:
            self.log_fn(t('warn_scope_need_goal'))
            return
        if not self.urls:
            self.log_fn(t('warn_scope_need_url'))
            return
        ai_config = get_active_ai_config(self.settings)
        if not ai_config.get('api_key'):
            self.log_fn(t('warn_need_api_key'))
            return

        self.log_fn(t('log_fetching_link_sample'))
        self.update_idletasks()
        sample = ai_scope.fetch_link_sample(self.urls)
        if not sample:
            self.log_fn(t('warn_scope_no_links'))
            return
        try:
            result = ai_scope.propose_scope_rules(
                goal, sample, self.urls[0], ai_config['api_key'], provider=ai_config['provider'])
        except Exception as e:
            self.log_fn(t('warn_scope_failed', e=e))
            return

        self.rules_text.delete('1.0', 'end')
        self.rules_text.insert('1.0', '\n'.join(result.get('rules', [])))
        explanation = result.get('explanation', '')
        if explanation:
            self.log_fn(f'[AI] {explanation}')

    def _on_apply(self):
        rules_text = self.rules_text.get('1.0', 'end').strip()
        self.destroy()
        self.on_apply(rules_text)


# ---------------- HTTrack 실행 엔진 (GUI/헤드리스 공용) ----------------
# GUI(스레드+큐)와 헤드리스 예약 작업(스케줄러) 양쪽에서 그대로 재사용할 수 있도록
# Tkinter에 의존하지 않는 순수 함수로 분리해둔다.

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


class OptionsDialog(tk.Toplevel):
    """메인 화면의 설정 요약 행을 눌렀을 때, 그 그룹 하나만 편집하는 작은 창.
    ExpressVPN이 'Selected Location  >' 같은 행을 누르면 그 설정만 보여주는
    방식을 그대로 따른다 - 모든 설정을 환경설정에 몰아넣지 않고, 지금 값이
    메인 화면에 보이고 누르면 바로 고칠 수 있게 하기 위함."""

    TITLES = {'scope': 'panel_scope', 'files': 'panel_files',
              'safety': 'panel_safety', 'power': 'panel_power',
              'smart': 'panel_smart_options'}

    def __init__(self, parent, app, group):
        super().__init__(parent)
        self.app = app
        self.group = group
        self.title(t(self.TITLES[group]))
        self.configure(bg=BG)
        self.geometry('720x620')
        self.minsize(560, 420)
        self.transient(parent)
        self.grab_set()

        footer = tk.Frame(self, bg=BG)
        footer.pack(side='bottom', fill='x', padx=24, pady=(0, 18))
        RoundedButton(footer, t('btn_done'), command=self._close, variant='accent').pack(side='right')

        outer = make_scrollable(self, bg=BG)
        outer.configure(padding=24)
        card = RoundedCard(outer, radius=16, padding=18)
        card.pack(fill='both', expand=True)
        body = card.body

        {'scope': self._build_scope, 'files': self._build_files,
         'safety': self._build_safety, 'power': self._build_power,
         'smart': self._build_smart}[group](body)

        self.protocol('WM_DELETE_WINDOW', self._close)

    def _close(self):
        self.app._refresh_option_summaries()
        self.destroy()

    # ---------------- 수집 범위 ----------------
    def _build_scope(self, parent):
        app = self.app
        ttk.Checkbutton(parent, text=t('scope_all'), variable=app.all_scope_var,
                        command=self._on_all_scope_toggle).pack(anchor='w')
        ttk.Checkbutton(parent, text=t('scope_limit'), variable=app.limit_depth_var,
                        command=self._on_limit_depth_toggle).pack(anchor='w', pady=(8, 0))

        self.depth_input_row = ttk.Frame(parent, style='Panel.TFrame')
        depth_num_row = ttk.Frame(self.depth_input_row, style='Panel.TFrame')
        depth_num_row.pack(fill='x')
        ttk.Label(depth_num_row, text=t('depth_label'), style='Muted.TLabel').pack(side='left')
        ttk.Spinbox(depth_num_row, from_=1, to=999, textvariable=app.depth_var, width=8).pack(
            side='left', padx=(10, 6))
        ttk.Label(depth_num_row, text=t('depth_unit'), style='Muted.TLabel').pack(side='left')

        depth_preset_row = ttk.Frame(self.depth_input_row, style='Panel.TFrame')
        depth_preset_row.pack(fill='x', pady=(8, 0))
        ttk.Label(depth_preset_row, text=t('depth_presets_label'), style='Muted.TLabel').pack(
            side='left', padx=(0, 8))
        for value, label in [(1, t('depth_preset_1')), (3, t('depth_preset_3')),
                             (5, t('depth_preset_5')), (10, t('depth_preset_10'))]:
            RoundedButton(depth_preset_row, label, command=lambda v=value: app.depth_var.set(str(v)),
                          variant='ghost', page_bg=PANEL, padx=12, pady=6).pack(side='left', padx=(0, 6))

        caption_box = tk.Frame(parent, bg=ACCENT_SOFT)
        caption_box.pack(fill='x', pady=(10, 0))
        tk.Label(caption_box, textvariable=app.depth_caption_var, bg=ACCENT_SOFT, fg=FG,
                 font=(FONT_UI, TYPE_CAPTION), wraplength=560, justify='left',
                 padx=12, pady=10).pack(anchor='w')

        ttk.Checkbutton(parent, text=t('label_same_folder'),
                        variable=app.same_folder_var).pack(anchor='w', pady=(14, 0))
        ttk.Label(parent, text=t('caption_same_folder'), style='Caption.TLabel',
                  wraplength=580).pack(anchor='w', pady=(2, 0))

        ttk.Label(parent, text=t('label_domain_scope'), style='Muted.TLabel').pack(anchor='w', pady=(14, 0))
        ttk.Combobox(parent, textvariable=app.domain_scope_var, state='readonly',
                     values=[label for _, label in app.domain_scope_options]).pack(fill='x', pady=(4, 2), ipady=2)
        ttk.Label(parent, text=t('caption_domain_scope'), style='Caption.TLabel',
                  wraplength=580).pack(anchor='w')

        self._sync_scope_rows()

    def _on_all_scope_toggle(self):
        # 두 체크박스는 서로 배타적: '모든 범위'를 켜면 '제한하기'는 꺼진다.
        self.app.limit_depth_var.set(not self.app.all_scope_var.get())
        self._sync_scope_rows()

    def _on_limit_depth_toggle(self):
        self.app.all_scope_var.set(not self.app.limit_depth_var.get())
        self._sync_scope_rows()

    def _sync_scope_rows(self):
        if self.app.limit_depth_var.get():
            self.depth_input_row.pack(anchor='w', pady=(8, 0))
            self.app.depth_caption_var.set(t('depth_caption_limited'))
        else:
            self.depth_input_row.pack_forget()
            self.app.depth_caption_var.set(t('depth_caption_unlimited'))

    # ---------------- 받을 파일 종류 ----------------
    def _build_files(self, parent):
        app = self.app
        grid = ttk.Frame(parent, style='Panel.TFrame')
        grid.pack(fill='x')
        for i, (var, _exts, label) in enumerate(app.filter_entries):
            ttk.Checkbutton(grid, text=label, variable=var,
                            command=app._refresh_filter_preview).grid(
                row=i // 2, column=i % 2, sticky='w', padx=(0, 20), pady=4)

        ttk.Label(parent, text=t('label_custom_rules'), style='Muted.TLabel').pack(anchor='w', pady=(14, 2))
        ttk.Entry(parent, textvariable=app.custom_filters_var).pack(fill='x', ipady=3)
        ttk.Label(parent, text=t('caption_custom_rules'), style='Caption.TLabel',
                  wraplength=580).pack(anchor='w', pady=(2, 0))

        preview_box = tk.Frame(parent, bg=BG, highlightbackground=BORDER, highlightthickness=1)
        preview_box.pack(fill='x', pady=(12, 0))
        ttk.Label(preview_box, text=t('label_applied_rules'), style='Caption.TLabel',
                  background=BG).pack(anchor='w', padx=10, pady=(6, 0))
        tk.Label(preview_box, textvariable=app.filter_preview_var, bg=BG, fg=FG_MUTED,
                 font=(FONT_MONO, 9), wraplength=580, justify='left', anchor='w').pack(
            fill='x', padx=10, pady=(0, 8))
        app._refresh_filter_preview()

    # ---------------- 안전장치 ----------------
    def _build_safety(self, parent):
        app = self.app
        ttk.Checkbutton(parent, text=t('safety_pause_enable'), variable=app.pause_enable_var,
                        command=self._sync_safety_rows).pack(anchor='w')
        self.pause_row = ttk.Frame(parent, style='Panel.TFrame')
        ttk.Label(self.pause_row, text=t('safety_pause_between'), style='Muted.TLabel').pack(side='left')
        ttk.Spinbox(self.pause_row, from_=0, to=300, textvariable=app.pause_min_var, width=6).pack(
            side='left', padx=(8, 4))
        ttk.Label(self.pause_row, text=t('safety_pause_and'), style='Muted.TLabel').pack(side='left')
        ttk.Spinbox(self.pause_row, from_=0, to=300, textvariable=app.pause_max_var, width=6).pack(
            side='left', padx=(4, 4))
        ttk.Label(self.pause_row, text=t('safety_pause_unit'), style='Muted.TLabel').pack(side='left')
        ttk.Label(parent, text=t('safety_pause_caption'), style='Caption.TLabel',
                  wraplength=580).pack(anchor='w', pady=(4, 0))

        ttk.Checkbutton(parent, text=t('safety_maxtime_enable'), variable=app.maxtime_enable_var,
                        command=self._sync_safety_rows).pack(anchor='w', pady=(14, 0))
        self.maxtime_row = ttk.Frame(parent, style='Panel.TFrame')
        ttk.Label(self.maxtime_row, text=t('safety_maxtime_label'), style='Muted.TLabel').pack(side='left')
        ttk.Spinbox(self.maxtime_row, from_=1, to=999, textvariable=app.maxtime_hours_var, width=6).pack(
            side='left', padx=(8, 0))
        ttk.Label(parent, text=t('safety_maxtime_caption'), style='Caption.TLabel',
                  wraplength=580).pack(anchor='w', pady=(4, 0))

        ttk.Checkbutton(parent, text=t('safety_maxsize_enable'), variable=app.maxsize_enable_var,
                        command=self._sync_safety_rows).pack(anchor='w', pady=(14, 0))
        self.maxsize_row = ttk.Frame(parent, style='Panel.TFrame')
        ttk.Label(self.maxsize_row, text=t('safety_maxsize_label'), style='Muted.TLabel').pack(side='left')
        ttk.Spinbox(self.maxsize_row, from_=1, to=1_000_000, textvariable=app.maxsize_mb_var, width=9).pack(
            side='left', padx=(8, 0))
        ttk.Label(parent, text=t('safety_maxsize_caption'), style='Caption.TLabel',
                  wraplength=580).pack(anchor='w', pady=(4, 0))

        ttk.Label(parent, text=t('safety_hostcontrol_label'), style='Muted.TLabel').pack(anchor='w', pady=(14, 0))
        ttk.Combobox(parent, textvariable=app.hostcontrol_var, state='readonly',
                     values=[label for _, label in app.hostcontrol_options]).pack(fill='x', pady=(4, 2), ipady=2)
        ttk.Label(parent, text=t('safety_hostcontrol_caption'), style='Caption.TLabel',
                  wraplength=580).pack(anchor='w')

        self._sync_safety_rows()

    def _sync_safety_rows(self):
        for enabled_var, row in ((self.app.pause_enable_var, self.pause_row),
                                 (self.app.maxtime_enable_var, self.maxtime_row),
                                 (self.app.maxsize_enable_var, self.maxsize_row)):
            if enabled_var.get():
                row.pack(anchor='w', pady=(6, 0))
            else:
                row.pack_forget()

    # ---------------- 스마트 크롤링 옵션 ----------------
    def _build_smart(self, parent):
        app = self.app

        def spin_row(label_key, caption_key, variable, from_, to):
            ttk.Label(parent, text=t(label_key), style='RowTitle.TLabel').pack(anchor='w', pady=(10, 0))
            ttk.Spinbox(parent, from_=from_, to=to, textvariable=variable, width=10).pack(anchor='w', pady=(4, 0))
            ttk.Label(parent, text=t(caption_key), style='Caption.TLabel',
                      wraplength=580).pack(anchor='w', pady=(2, 0))

        spin_row('label_max_pages', 'caption_max_pages', app.max_pages_var, 1, 5000)
        spin_row('label_follow_depth', 'caption_follow_depth', app.follow_depth_var, 1, 20)

        ttk.Label(parent, text=t('label_wait_until'), style='RowTitle.TLabel').pack(anchor='w', pady=(14, 0))
        ttk.Combobox(parent, textvariable=app.wait_until_var, state='readonly',
                     values=['networkidle', 'load', 'domcontentloaded']).pack(fill='x', pady=(4, 0), ipady=2)
        ttk.Label(parent, text=t('caption_wait_until'), style='Caption.TLabel',
                  wraplength=580).pack(anchor='w', pady=(2, 0))

        # 로그인이 필요한 사이트는 이 토글이 핵심이라 스마트 옵션 안에도 같이 노출한다.
        ttk.Label(parent, text=t('label_use_local_cookies'), style='RowTitle.TLabel').pack(anchor='w', pady=(16, 0))
        ToggleSwitch(parent, variable=app.use_local_cookies_var, page_bg=PANEL,
                     command=app._save_use_local_cookies).pack(anchor='w', pady=(4, 0))
        ttk.Label(parent, text=t('caption_use_local_cookies'), style='Caption.TLabel',
                  wraplength=580).pack(anchor='w', pady=(2, 0))

    # ---------------- 완료 후 동작 ----------------
    def _build_power(self, parent):
        app = self.app
        for value, label_key in (('none', 'power_none'), ('on_complete', 'power_on_complete'),
                                 ('after_hours', 'power_after_hours')):
            ttk.Radiobutton(parent, text=t(label_key), value=value, variable=app.power_action_var,
                            command=self._sync_power_rows).pack(anchor='w', pady=(0, 8))

        self.power_hours_row = ttk.Frame(parent, style='Panel.TFrame')
        ttk.Label(self.power_hours_row, text=t('label_hours_until_shutdown'),
                  style='Muted.TLabel').pack(side='left')
        ttk.Spinbox(self.power_hours_row, from_=1, to=48, textvariable=app.power_hours_var, width=6).pack(
            side='left', padx=(8, 0))

        caption_box = tk.Frame(parent, bg=ACCENT_SOFT)
        caption_box.pack(fill='x', pady=(10, 0))
        tk.Label(caption_box, textvariable=app.power_caption_var, bg=ACCENT_SOFT, fg=FG,
                 font=(FONT_UI, TYPE_CAPTION), wraplength=560, justify='left',
                 padx=12, pady=10).pack(anchor='w')

        self._sync_power_rows()

    def _sync_power_rows(self):
        mode = self.app.power_action_var.get()
        if mode == 'after_hours':
            self.power_hours_row.pack(anchor='w', pady=(4, 0))
            self.app.power_caption_var.set(t('power_caption_after_hours'))
        else:
            self.power_hours_row.pack_forget()
            self.app.power_caption_var.set(
                t('power_caption_on_complete') if mode == 'on_complete' else t('power_caption_none'))


class MirrorXApp:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        set_language(self.settings.get('language', 'en'))
        self.current_process = None
        self.msg_queue = queue.Queue()
        self.progress_state = {}
        self.worker_thread = None
        self._shutdown_armed = False
        self._user_stopped = False
        self.projects = load_projects()
        self._current_project_key = None
        self.jobs = jobs_mod.load_jobs(CONFIG_DIR)

        resolve_fonts()
        self._build_style()
        self._init_option_vars()
        self._build_ui()
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        self.root.after(80, self._poll_queue)

    # ---------------- 스타일 ----------------
    def _build_style(self):
        style = ttk.Style(self.root)
        style.theme_use('clam')
        self.root.configure(bg=BG)

        base_font = (FONT_UI, TYPE_BODY)
        style.configure('.', background=BG, foreground=FG, fieldbackground=PANEL_LIGHT, font=base_font)
        style.configure('TFrame', background=BG)
        style.configure('Panel.TFrame', background=PANEL)
        style.configure('PanelLight.TFrame', background=PANEL_LIGHT)
        style.configure('Stat.TFrame', background=STAT_BG)
        style.configure('TLabel', background=BG, foreground=FG, font=base_font)
        style.configure('Panel.TLabel', background=PANEL, foreground=FG, font=base_font)
        style.configure('Muted.TLabel', background=PANEL, foreground=FG_MUTED, font=base_font)
        style.configure('MutedRoot.TLabel', background=BG, foreground=FG_MUTED, font=base_font)
        style.configure('Header.TLabel', background=PANEL, foreground=FG, font=(FONT_UI, TYPE_SUBTITLE, 'bold'))
        style.configure('RowTitle.TLabel', background=PANEL, foreground=FG, font=(FONT_UI, TYPE_BODY, 'bold'))
        style.configure('Title.TLabel', background=BG, foreground=ACCENT, font=(FONT_UI, TYPE_TITLE, 'bold'))
        style.configure('Title2.TLabel', background=BG, foreground=FG, font=(FONT_UI, TYPE_SUBTITLE, 'bold'))
        style.configure('Sub.TLabel', background=BG, foreground=FG_MUTED, font=(FONT_UI, TYPE_CAPTION))
        style.configure('Caption.TLabel', background=PANEL, foreground=FG_MUTED, font=(FONT_UI, TYPE_CAPTION))
        style.configure('Badge.TLabel', background=ACCENT_SOFT, foreground=ACCENT,
                         font=(FONT_UI, TYPE_CAPTION, 'bold'), padding=(9, 4))

        style.configure('TCheckbutton', background=PANEL, foreground=FG, font=base_font)
        style.map('TCheckbutton', background=[('active', PANEL)])
        style.configure('TRadiobutton', background=PANEL, foreground=FG, font=base_font)
        style.map('TRadiobutton', background=[('active', PANEL)])

        # 실제로 타이핑하는 입력창은 본문보다 한 단계 크게 - 작으면 읽기 불편하다.
        field_font = (FONT_UI, TYPE_INPUT)
        style.configure('TEntry', fieldbackground=PANEL_LIGHT, foreground=FG, insertcolor=FG,
                         bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, font=field_font,
                         padding=6)
        style.configure('TCombobox', fieldbackground=PANEL_LIGHT, foreground=FG, arrowcolor=FG_MUTED,
                         font=field_font, padding=5)
        style.map('TCombobox', fieldbackground=[('readonly', PANEL_LIGHT)], foreground=[('readonly', FG)])
        style.configure('TSpinbox', fieldbackground=PANEL_LIGHT, foreground=FG, arrowsize=14, font=field_font)

        # ttk Combobox의 드롭다운 목록은 내부적으로 일반 tk.Listbox라서 위 스타일 font가
        # 적용되지 않는다 (그대로 두면 시스템 기본 작은 글씨로 나옴) - 전역 옵션으로 별도 지정.
        self.root.option_add('*TCombobox*Listbox.font', field_font)
        self.root.option_add('*TCombobox*Listbox.background', PANEL_LIGHT)
        self.root.option_add('*TCombobox*Listbox.foreground', FG)
        self.root.option_add('*TCombobox*Listbox.selectBackground', ACCENT)
        self.root.option_add('*TCombobox*Listbox.selectForeground', ON_ACCENT)

        style.configure('TButton', background=PANEL_LIGHT, foreground=FG, padding=9, borderwidth=0,
                         font=base_font)
        style.map('TButton', background=[('active', BORDER)])
        style.configure('Accent.TButton', background=ACCENT, foreground=ON_ACCENT, padding=(18, 10),
                         font=(FONT_UI, TYPE_BODY, 'bold'), borderwidth=0)
        style.map('Accent.TButton', background=[('active', ACCENT_HOVER), ('disabled', '#E7E1D4')])
        style.configure('Danger.TButton', background=RED, foreground=ON_DANGER, padding=(18, 10),
                         font=(FONT_UI, TYPE_BODY, 'bold'), borderwidth=0)
        style.map('Danger.TButton', background=[('active', '#A82317')])

        style.configure('Horizontal.TProgressbar', background=ACCENT, troughcolor=PANEL_LIGHT,
                         bordercolor=PANEL, lightcolor=ACCENT, darkcolor=ACCENT, thickness=10)
        style.configure('TScale', background=PANEL, troughcolor=PANEL_LIGHT)

        # 탭 (Notebook) - 지금 보고 있는 탭이 뚜렷이 커지고 색도 분명히 달라지도록
        style.configure('TNotebook', background=BG, borderwidth=0, tabmargins=(0, 8, 0, 0))
        style.configure('TNotebook.Tab', background=TAB_INACTIVE, foreground=FG_MUTED,
                         font=(FONT_UI, TYPE_BODY), padding=(18, 9), borderwidth=0)
        style.map('TNotebook.Tab',
                  background=[('selected', BG)],
                  foreground=[('selected', ACCENT)],
                  font=[('selected', (FONT_UI, TYPE_BODY_LARGE, 'bold'))],
                  padding=[('selected', (26, 14))])

    def _build_ui(self):
        self.root.title('MirrorX0')
        self.root.geometry('1340x900')
        self.root.minsize(1080, 740)

        # 스크롤 없이 한 화면에 다 들어가는 구조. grid의 weight로 창을 줄이면
        # 각 영역이 같이 줄어들고(원형 버튼까지), minsize가 하한을 지켜준다.
        #   0행 브랜드 배너 / 1행 히어로(통계 · 원형 시작버튼 · 통계) / 2행 하단(설정 | 로그)
        root_frame = tk.Frame(self.root, bg=BG)
        root_frame.pack(fill='both', expand=True)
        root_frame.grid_columnconfigure(0, weight=1)
        root_frame.grid_rowconfigure(2, weight=1)
        self._root_frame = root_frame

        header = BrandHeader(root_frame, t('app_subtitle'))
        header.grid(row=0, column=0, sticky='ew')

        self._build_hero(root_frame)

        bottom = tk.Frame(root_frame, bg=BG)
        bottom.grid(row=2, column=0, sticky='nsew', padx=26, pady=(4, 20))
        bottom.grid_rowconfigure(0, weight=1)
        bottom.grid_columnconfigure(0, weight=3, uniform='bottom')
        bottom.grid_columnconfigure(1, weight=2, uniform='bottom')

        settings_col = tk.Frame(bottom, bg=BG)
        settings_col.grid(row=0, column=0, sticky='nsew', padx=(0, 9))
        log_col = tk.Frame(bottom, bg=BG)
        log_col.grid(row=0, column=1, sticky='nsew', padx=(9, 0))
        self._build_settings_column(settings_col)
        self._build_log_column(log_col)

        # 예약 종료 배너 - 평소엔 숨겨두고 종료가 예약됐을 때만 맨 아래에 띄운다.
        self.shutdown_banner = tk.Frame(root_frame, bg=CRITICAL)
        self.shutdown_banner_var = tk.StringVar()
        tk.Label(self.shutdown_banner, textvariable=self.shutdown_banner_var, bg=CRITICAL, fg=ON_DANGER,
                 font=(FONT_UI, TYPE_CAPTION, 'bold'), padx=14, pady=9).pack(side='left')
        RoundedButton(self.shutdown_banner, t('btn_cancel_shutdown'), command=self._cancel_shutdown,
                      variant='neutral', page_bg=CRITICAL).pack(side='right', padx=12, pady=7)

        self._refresh_option_summaries()
        self._sync_start_button()
        # 레이아웃이 완전히 잡힌 뒤 실제로 필요한 높이를 재서 최소 크기로 잡아준다.
        # 이렇게 하면 사용자가 창을 줄여도 내용이 잘리는 지점 아래로는 못 줄인다.
        # RoundedCard들이 타이머로 자기 높이를 확정하므로 after_idle이 아니라 조금 뒤에
        # 재야 한다 - 너무 일찍 재면 아직 0에 가까운 높이로 계산된다.
        self.root.after(180, self._apply_min_size)

    def _apply_min_size(self):
        self.root.update_idletasks()
        # 화면보다 큰 최소 크기를 잡으면 창을 아예 못 쓰게 되므로 화면 크기로 한 번 자른다.
        max_w = self.root.winfo_screenwidth() - 60
        max_h = self.root.winfo_screenheight() - 100
        needed_w = min(max(1040, self._root_frame.winfo_reqwidth()), max_w)
        needed_h = min(self._root_frame.winfo_reqheight(), max_h)
        self.root.minsize(needed_w, needed_h)
        if self.root.winfo_height() < needed_h or self.root.winfo_width() < needed_w:
            self.root.geometry(f'{max(needed_w, self.root.winfo_width())}x'
                               f'{max(needed_h, self.root.winfo_height())}')

    def _init_option_vars(self):
        """작업 옵션(범위/파일/안전장치/전원)의 상태 변수를 앱이 직접 들고 있는다.
        위젯은 OptionsDialog가 필요할 때만 만들어 이 변수들에 묶기 때문에, 다이얼로그를
        닫아도 값은 그대로 남고 메인 화면의 요약 행이 항상 현재 값을 보여줄 수 있다."""
        # 수집 범위
        self.all_scope_var = tk.BooleanVar(value=True)
        self.limit_depth_var = tk.BooleanVar(value=False)
        self.depth_var = tk.StringVar(value='5')
        self.depth_caption_var = tk.StringVar(value=t('depth_caption_unlimited'))
        self.same_folder_var = tk.BooleanVar(value=False)
        self.domain_scope_options = [('host', t('domain_scope_host')),
                                     ('subdomain', t('domain_scope_subdomain'))]
        self.domain_scope_var = tk.StringVar(value=self.domain_scope_options[0][1])

        # 받을 파일 종류 - (변수, 확장자들, 표시 이름)
        self.filter_entries = [(tk.BooleanVar(value=default_on), exts, label)
                               for label, exts, default_on in get_filter_groups()]
        self.custom_filters_var = tk.StringVar(value='')
        self.custom_filters_var.trace_add('write', lambda *_a: self._refresh_filter_preview())
        self.filter_preview_var = tk.StringVar()

        # 안전장치
        self.pause_enable_var = tk.BooleanVar(value=False)
        self.pause_min_var = tk.StringVar(value='2')
        self.pause_max_var = tk.StringVar(value='6')
        self.maxtime_enable_var = tk.BooleanVar(value=False)
        self.maxtime_hours_var = tk.StringVar(value='6')
        self.maxsize_enable_var = tk.BooleanVar(value=False)
        self.maxsize_mb_var = tk.StringVar(value='1000')
        self.hostcontrol_options = [
            ('none', t('hostcontrol_none')), ('timeout', t('hostcontrol_timeout')),
            ('slow', t('hostcontrol_slow')), ('both', t('hostcontrol_both')),
        ]
        self.hostcontrol_var = tk.StringVar(value=self.hostcontrol_options[0][1])

        # 브라우저 로그인(쿠키) 연동 - 환경설정 창과 스마트 옵션 창이 같은 변수를 쓴다.
        self.use_local_cookies_var = tk.BooleanVar(
            value=bool(self.settings.get('use_local_cookies', False)))

        # 스마트 크롤링 옵션 (Playwright로 실제 브라우저를 띄워 받는 모드)
        self.max_pages_var = tk.StringVar(value='50')
        self.follow_depth_var = tk.StringVar(value='1')
        self.wait_until_var = tk.StringVar(value='networkidle')

        # 완료 후 동작
        self.power_action_var = tk.StringVar(value='none')
        self.power_hours_var = tk.StringVar(value='2')
        self.power_caption_var = tk.StringVar(value=t('power_caption_none'))

        self._refresh_filter_preview()

    def _build_hero(self, parent):
        """원형 시작 버튼을 가운데 두고 좌우로 실시간 지표 카드를 배치한다."""
        hero = tk.Frame(parent, bg=BG)
        hero.grid(row=1, column=0, sticky='ew', padx=26, pady=(10, 4))
        # 지표 카드 열은 내용 폭만 차지하게 두고(weight=0), 남는 폭은 전부 가운데가
        # 가져간다 - 그래야 카드가 쓸데없이 길어지지 않고 버튼 주변에 여백이 생긴다.
        hero.grid_columnconfigure(0, weight=0, uniform='hero')
        hero.grid_columnconfigure(1, weight=1)
        hero.grid_columnconfigure(2, weight=0, uniform='hero')

        left_stats = tk.Frame(hero, bg=BG)
        left_stats.grid(row=0, column=0, sticky='n')
        center = tk.Frame(hero, bg=BG)
        center.grid(row=0, column=1, padx=48)
        right_stats = tk.Frame(hero, bg=BG)
        right_stats.grid(row=0, column=2, sticky='n')

        self.elapsed_stat = self._stat_card(left_stats, '⏱', t('stat_elapsed'))
        self.links_stat, self._links_caption = self._stat_card(left_stats, '🔗', t('stat_links'),
                                                               with_caption=True)
        self.files_stat = self._stat_card(left_stats, '📄', t('stat_files'))
        self.bytes_stat = self._stat_card(right_stats, '💾', t('stat_bytes'))
        self.speed_stat = self._stat_card(right_stats, '⚡', t('stat_speed'))
        self.errors_stat = self._stat_card(right_stats, '⚠', t('stat_errors'))

        # 무엇을 받을지 고르는 곳 - 이 앱의 유일한 진짜 분기라서 시작 버튼 바로 위에 둔다.
        self.mode_var = tk.StringVar(value='mirror')
        SegmentedControl(center, self.mode_var,
                         [('mirror', t('mode_mirror')), ('smart', t('mode_smart'))],
                         command=self._on_mode_changed, page_bg=BG, width=340).pack(pady=(0, 6))
        self._mode_caption_var = tk.StringVar(value=t('caption_mode_mirror'))
        tk.Label(center, textvariable=self._mode_caption_var, bg=BG, fg=FG_MUTED,
                 font=(FONT_UI, TYPE_CAPTION), wraplength=380, justify='center').pack(pady=(0, 10))

        self.start_button = CircularStartButton(center, command=self._on_power_clicked, size=180)
        self.start_button.pack()
        self.job_var = tk.StringVar()
        # height=1로 한 줄을 미리 잡아둔다. 상태 문구가 나타났다 사라질 때
        # 아래 내용이 위아래로 밀리지 않게 하기 위함.
        self._status_label = tk.Label(center, textvariable=self.job_var, bg=BG, fg=FG_MUTED,
                                      height=1, font=(FONT_UI, TYPE_BODY, 'bold'))
        self._status_label.pack(pady=(12, 0))
        # 기존 진행률 로직과의 호환용 - 실제 표시는 원형 버튼의 링이 담당한다.
        self.progress_var = tk.DoubleVar(value=0)

        hero.bind('<Configure>', self._on_hero_resize)

    def _on_hero_resize(self, event):
        """창을 줄이면 원형 버튼도 같이 줄어든다.
        높이가 아니라 폭에만 반응시킨다 - 높이에 반응시키면 (버튼이 커짐 → 창이
        더 필요해짐 → 다시 계산) 식으로 서로를 밀어내며 흔들릴 수 있기 때문."""
        # 캔버스에는 글로우 여백도 포함되므로 실제 원보다 조금 크게 잡는다.
        self.start_button.set_size(max(146, min(180, event.width * 0.22)))

    def _sync_stat_captions(self):
        """모드에 따라 지표 이름을 바꾼다 (미러링은 '스캔한 링크', 스마트는 '방문한 페이지')."""
        self._links_caption.configure(
            text=t('stat_pages') if self.mode_var.get() == 'smart' else t('stat_links'))

    def _stat_card(self, parent, icon, caption, with_caption=False):
        # inset을 radius와 분리해 작게 준다 - 기본값(=radius)이면 카드마다 위아래로
        # 28px씩 낭비돼 지표 카드 세 장만으로도 화면이 넘친다.
        card = RoundedCard(parent, page_bg=BG, card_bg=STAT_BG, border=STAT_BORDER,
                           radius=13, inset=5, padding=(12, 8), body_style='Stat.TFrame')
        card.pack(fill='x', pady=2)
        row = ttk.Frame(card.body, style='Stat.TFrame')
        row.pack(fill='x')
        tk.Label(row, text=icon, bg=STAT_BG, fg=ACCENT,
                 font=(FONT_UI, TYPE_CAPTION)).pack(side='left', padx=(0, 9))
        col = ttk.Frame(row, style='Stat.TFrame')
        col.pack(side='left', fill='x', expand=True)
        caption_lbl = tk.Label(col, text=caption, bg=STAT_BG, fg=FG_MUTED,
                               font=(FONT_UI, TYPE_CAPTION), width=11, anchor='w')
        caption_lbl.pack(anchor='w', fill='x')
        # width를 글자 수로 고정해 둔다. 값이 '-' ↔ '386/411'처럼 바뀔 때마다 라벨의
        # 요청 크기가 달라지면 카드가 매번 다시 레이아웃되면서 눈에 띄게 들썩인다.
        value = tk.Label(col, text='-', bg=STAT_BG, fg=FG, font=(FONT_UI, TYPE_INPUT, 'bold'),
                         width=10, anchor='w')
        value.pack(anchor='w', fill='x')
        return (value, caption_lbl) if with_caption else value

    def _build_settings_column(self, parent):
        """좌측 열: 지금 설정된 값들(주소/프로젝트/방식 + 옵션 요약 행).
        expand=False로 두어 카드가 '내용에 맞는 높이'를 갖게 한다 - expand=True면
        남는 공간에 맞춰 내용을 우겨넣어 아래쪽 행이 잘리기 때문."""
        card = RoundedCard(parent, radius=18, padding=14, inset=10)
        card.pack(fill='x')
        self._settings_card = card
        body = card.body

        self._lockable = []

        head = ttk.Frame(body, style='Panel.TFrame')
        head.pack(fill='x', pady=(0, 12))
        ttk.Label(head, text=t('panel_project'), style='Header.TLabel').pack(side='left')
        prefs_btn = RoundedButton(head, f"⚙  {t('nav_preferences')}", command=self._open_preferences,
                                  variant='ghost', page_bg=PANEL, padx=14, pady=7)
        prefs_btn.pack(side='right')
        self._lockable.append(prefs_btn)

        ttk.Label(body, text=t('label_urls'), style='Muted.TLabel').pack(anchor='w')
        url_row = ttk.Frame(body, style='Panel.TFrame')
        url_row.pack(fill='x', pady=(4, 12))
        self.urls_var = tk.StringVar()
        # 받을 주소가 바뀌면 시작 버튼 활성 여부와 프로젝트 이름 자동 채우기를 갱신한다.
        self.urls_var.trace_add('write', lambda *_a: self._on_urls_changed())
        url_entry = ttk.Entry(url_row, textvariable=self.urls_var)
        url_entry.pack(side='left', fill='x', expand=True, ipady=5)
        load_btn = RoundedButton(url_row, t('btn_load_url_file'), command=self._load_url_file,
                                 variant='ghost', page_bg=PANEL, padx=12, pady=7)
        load_btn.pack(side='left', padx=(8, 0))
        self._lockable += [url_entry, load_btn]

        # 프로젝트명 · 수집 방식을 한 줄에 나란히 둔다(세로 공간 절약).
        fields = ttk.Frame(body, style='Panel.TFrame')
        fields.pack(fill='x', pady=(0, 10))
        fields.grid_columnconfigure(0, weight=1, uniform='field')
        fields.grid_columnconfigure(1, weight=1, uniform='field')

        name_col = ttk.Frame(fields, style='Panel.TFrame')
        name_col.grid(row=0, column=0, sticky='ew', padx=(0, 8))
        ttk.Label(name_col, text=t('label_project_name'), style='Muted.TLabel').pack(anchor='w')
        self.project_var = tk.StringVar()
        # 사용자가 직접 고친 이름은 주소가 바뀌어도 덮어쓰지 않는다.
        self._project_name_is_auto = True
        self.project_var.trace_add('write', lambda *_a: self._on_project_name_typed())
        name_entry = ttk.Entry(name_col, textvariable=self.project_var)
        name_entry.pack(fill='x', pady=(4, 0))
        self._lockable.append(name_entry)

        # '수집 방식'(HTTrack 액션)은 미러링 모드에서만 의미가 있어 모드에 따라 감춘다.
        self._action_col = ttk.Frame(fields, style='Panel.TFrame')
        self._action_col.grid(row=0, column=1, sticky='ew', padx=(8, 0))
        ttk.Label(self._action_col, text=t('label_collect_mode'), style='Muted.TLabel').pack(anchor='w')
        self.actions = get_actions()
        self.action_var = tk.StringVar(value=self.actions[0][1])
        action_combo = ttk.Combobox(self._action_col, textvariable=self.action_var, state='readonly',
                                    values=[label for _, label in self.actions])
        action_combo.pack(fill='x', pady=(4, 0))
        self._lockable.append(action_combo)

        ttk.Label(body, text=t('label_save_location'), style='Muted.TLabel').pack(anchor='w')
        path_row = ttk.Frame(body, style='Panel.TFrame')
        path_row.pack(fill='x', pady=(4, 12))
        self.base_path_var = tk.StringVar(value=self.settings['base_path'])
        path_entry = ttk.Entry(path_row, textvariable=self.base_path_var)
        path_entry.pack(side='left', fill='x', expand=True)
        browse_btn = RoundedButton(path_row, t('btn_browse'), command=self._browse_folder,
                                   variant='ghost', page_bg=PANEL, padx=12, pady=7)
        browse_btn.pack(side='left', padx=(8, 0))
        self._lockable += [path_entry, browse_btn]

        tk.Frame(body, bg=BORDER, height=1).pack(fill='x', pady=(0, 9))

        # 지금 설정된 값이 그대로 보이고, 행을 누르면 그 그룹만 바로 편집할 수 있다
        # (ExpressVPN의 'Selected Location  >' 행과 같은 방식).
        # 모드에 따라 보여줄 항목이 다르므로 이 영역만 통째로 다시 그린다.
        self._options_area = ttk.Frame(body, style='Panel.TFrame')
        self._options_area.pack(fill='x')
        self._summary_vars = {}
        self._rebuild_options_area()

    # 모드별로 보여줄 옵션 행 정의 - (그룹키, 아이콘, 제목 문자열 키)
    _OPTION_ROWS = {
        'mirror': (('scope', '🎯', 'panel_scope'), ('files', '📦', 'panel_files'),
                   ('safety', '🛡', 'panel_safety'), ('power', '⏻', 'panel_power')),
        'smart': (('smart', '🧠', 'panel_smart_options'), ('power', '⏻', 'panel_power')),
    }

    def _rebuild_options_area(self):
        """현재 모드에 맞는 옵션 요약 행만 남기고 다시 그린다."""
        for child in self._options_area.winfo_children():
            child.destroy()
        self._options_area.grid_columnconfigure(0, weight=1, uniform='opt')
        self._options_area.grid_columnconfigure(1, weight=1, uniform='opt')

        rows = self._OPTION_ROWS[self.mode_var.get()]
        for i, (group, icon, title_key) in enumerate(rows):
            self._summary_vars.setdefault(group, tk.StringVar())
            row_card = self._option_row(self._options_area, group, icon, t(title_key),
                                        self._summary_vars[group])
            row_card.grid(row=i // 2, column=i % 2, sticky='ew',
                          padx=(0, 4) if i % 2 == 0 else (4, 0), pady=3)
        self._refresh_option_summaries()

    def _on_mode_changed(self, _value=None):
        """세그먼트로 모드를 바꿨을 때: 공통 입력값은 그대로 두고 다른 부분만 바꾼다."""
        if getattr(self, '_busy', False):
            return
        smart = self.mode_var.get() == 'smart'
        if smart:
            self._action_col.grid_remove()
        else:
            self._action_col.grid()
        self._mode_caption_var.set(t('caption_mode_smart') if smart else t('caption_mode_mirror'))
        self._rebuild_options_area()
        self._sync_stat_captions()

    def _option_row(self, parent, group, icon, title, value_var):
        # inset을 작게 줘서 행 높이를 촘촘하게 유지한다(네 행이 스크롤 없이 다 들어가야 함).
        card = RoundedCard(parent, page_bg=PANEL, card_bg=PANEL_LIGHT, radius=11, inset=4,
                           padding=(11, 6), body_style='PanelLight.TFrame')
        inner = card.body
        tk.Label(inner, text=icon, bg=PANEL_LIGHT, fg=FG_MUTED,
                 font=(FONT_UI, TYPE_CAPTION)).pack(side='left', padx=(0, 9))
        tk.Label(inner, text='›', bg=PANEL_LIGHT, fg=FG_MUTED,
                 font=(FONT_UI, TYPE_BODY_LARGE, 'bold')).pack(side='right', padx=(6, 2))
        col = ttk.Frame(inner, style='PanelLight.TFrame')
        col.pack(side='left', fill='x', expand=True)
        tk.Label(col, text=title, bg=PANEL_LIGHT, fg=FG_MUTED,
                 font=(FONT_UI, TYPE_CAPTION)).pack(anchor='w')
        # 값이 길어도 잘리지 않게 한 줄로 유지하되, 폭이 모자라면 말줄임 대신 그대로 두고
        # 카드가 늘어나도록 한다(잘림 방지가 우선).
        tk.Label(col, textvariable=value_var, bg=PANEL_LIGHT, fg=FG, anchor='w',
                 font=(FONT_UI, TYPE_BODY, 'bold')).pack(anchor='w', fill='x')

        def _open(_event=None):
            self._open_options_dialog(group)

        # 행 전체가 눌리도록 자식 위젯까지 같은 핸들러를 걸어준다.
        for widget in (card, card.canvas, inner, col, *inner.winfo_children(), *col.winfo_children()):
            widget.bind('<Button-1>', _open)
            try:
                widget.configure(cursor='hand2')
            except tk.TclError:
                pass
        return card

    def _build_log_column(self, parent):
        """우측 열: 실시간 로그."""
        card = RoundedCard(parent, radius=18, padding=16, expand=True)
        card.pack(fill='both', expand=True)
        body = card.body

        head = ttk.Frame(body, style='Panel.TFrame')
        head.pack(fill='x', pady=(0, 10))
        ttk.Label(head, text=t('panel_log'), style='Header.TLabel').pack(side='left')
        self.open_folder_btn = RoundedButton(head, t('btn_open_folder'), command=self._open_result_folder,
                                             variant='ghost', page_bg=PANEL, padx=13, pady=7)
        self.open_folder_btn.set_enabled(False)
        self.open_folder_btn.pack(side='right')

        # height는 '요청 크기'일 뿐이고 실제로는 남는 공간을 채운다. 기본값(24줄)을 두면
        # 창의 최소 높이가 불필요하게 커지므로 작게 잡아둔다.
        self.log_text = scrolledtext.ScrolledText(
            body, bg='#16151A', fg='#8FE3A6', insertbackground='#8FE3A6',
            font=(FONT_MONO, 10), relief='flat', state='disabled', wrap='word',
            highlightthickness=0, borderwidth=0, height=8)
        self.log_text.pack(fill='both', expand=True)

    # ---------------- 설정 요약 / 옵션 다이얼로그 ----------------
    def _set_busy(self, busy):
        """작업 중에는 설정을 못 바꾸게 잠근다.
        실행 중에 값을 바꿔봐야 이미 돌고 있는 명령에는 반영되지 않는데 화면 값만
        바뀌면 '바꿨는데 왜 그대로지?' 하고 헷갈리기 때문이다."""
        self._busy = busy
        state = 'disabled' if busy else 'normal'
        for widget in getattr(self, '_lockable', []):
            try:
                if isinstance(widget, RoundedButton):
                    widget.set_enabled(not busy)
                elif isinstance(widget, ttk.Combobox):
                    widget.configure(state='disabled' if busy else 'readonly')
                else:
                    widget.configure(state=state)
            except tk.TclError:
                pass

    def _open_options_dialog(self, group):
        if getattr(self, '_busy', False):
            return
        OptionsDialog(self.root, self, group)

    def _save_use_local_cookies(self):
        self.settings['use_local_cookies'] = bool(self.use_local_cookies_var.get())
        save_settings(self.settings)

    def _refresh_option_summaries(self):
        """메인 화면의 요약 행에 지금 설정된 값을 사람이 읽는 문장으로 채운다."""
        if not hasattr(self, '_summary_vars'):
            return
        if 'smart' in self._summary_vars:
            self._summary_vars['smart'].set(t('summary_smart_value',
                                              pages=self.max_pages_var.get(),
                                              depth=self.follow_depth_var.get()))
        if 'scope' not in self._summary_vars:
            # 스마트 모드에서는 미러링 전용 요약 행이 없으므로 여기서 끝낸다.
            self._set_power_summary()
            return
        depth = self._effective_depth()
        scope_text = t('scope_unlimited') if depth is None else t('scope_n_levels', depth=depth)
        if self.same_folder_var.get():
            scope_text += f" · {t('label_same_folder')}"
        self._summary_vars['scope'].set(scope_text)

        chosen = [label for var, _exts, label in self.filter_entries if var.get()]
        self._summary_vars['files'].set(' · '.join(chosen) if chosen else t('filters_none'))

        safety_parts = []
        if self.pause_enable_var.get():
            safety_parts.append(f"{self.pause_min_var.get()}~{self.pause_max_var.get()}s")
        if self.maxtime_enable_var.get():
            safety_parts.append(f"{self.maxtime_hours_var.get()}h")
        if self.maxsize_enable_var.get():
            safety_parts.append(f"{self.maxsize_mb_var.get()}MB")
        self._summary_vars['safety'].set(' · '.join(safety_parts) if safety_parts else t('value_off'))

        self._set_power_summary()

    def _set_power_summary(self):
        mode = self.power_action_var.get()
        if mode == 'after_hours':
            power_text = t('power_text_after_hours', hours=self.power_hours_var.get())
        elif mode == 'on_complete':
            power_text = t('power_text_on_complete')
        else:
            power_text = t('power_text_none')
        self._summary_vars['power'].set(power_text)

    def _sync_start_button(self):
        """받을 주소가 있어야 시작 버튼이 활성화된다."""
        if not hasattr(self, 'start_button'):
            return
        has_urls = bool(self._get_urls())
        self.start_button.set_enabled(has_urls)
        # 상태줄은 '할 말이 있을 때만' 말한다. 주소가 없어 못 누르는 상황에서는
        # 그 이유를 알려주고, 누를 수 있는 평상시에는 비워 둔다 - 버튼에 이미
        # '시작'이라고 쓰여 있어서 굳이 한 번 더 말할 필요가 없다.
        # (실행 중/완료 메시지는 각자 덮어쓰므로 여기서 건드리지 않는다.)
        if not getattr(self, '_busy', False):
            self._set_status('' if has_urls else t('hint_need_url'))

    def _set_status(self, text, emphasis=False):
        """버튼 아래 상태줄. 완료처럼 중요한 순간만 진한 색으로 강조한다."""
        self.job_var.set(text)
        if hasattr(self, '_status_label'):
            self._status_label.configure(fg=FG if emphasis else FG_MUTED)

    def _on_urls_changed(self):
        self._sync_start_button()
        self._autofill_project_name()

    def _on_project_name_typed(self):
        # 자동으로 채워 넣는 중이 아니면 사용자가 직접 고친 것으로 본다.
        if not getattr(self, '_filling_project_name', False):
            self._project_name_is_auto = False

    def _autofill_project_name(self):
        """받을 주소의 도메인에서 프로젝트(폴더) 이름을 자동으로 만든다.
        사용자가 직접 이름을 고쳤다면 건드리지 않는다."""
        if not getattr(self, '_project_name_is_auto', True):
            return
        urls = self._get_urls()
        if not urls:
            return
        from urllib.parse import urlparse
        raw = urls[0]
        host = urlparse(raw if '://' in raw else 'http://' + raw).hostname or ''
        host = re.sub(r'^www\.', '', host)
        name = re.sub(r'[^A-Za-z0-9._-]+', '_', host).strip('_')
        if not name:
            return
        self._filling_project_name = True
        try:
            self.project_var.set(name)
        finally:
            self._filling_project_name = False

    def _on_power_clicked(self):
        """가운데 원형 버튼 하나로 시작/중지를 모두 처리한다."""
        if self.start_button.is_running():
            self._stop_mirroring()
        else:
            self._on_start_clicked()

    def _get_urls(self):
        # 주소 입력은 한 줄이지만, 공백이나 쉼표로 여러 개를 넣는 경우도 받아준다.
        raw = self.urls_var.get().replace(',', ' ')
        return [u.strip() for u in raw.split() if u.strip()]

    def _set_urls(self, urls):
        self.urls_var.set(' '.join(urls))

    def _build_schedule_tab(self, parent):
        panel = self._panel(parent, t('panel_schedule_list'), expand=True)
        ttk.Label(panel, text=t('caption_schedule_list'), style='Caption.TLabel',
                  wraplength=760).pack(anchor='w', pady=(0, 10))
        new_job_row = ttk.Frame(panel, style='Panel.TFrame')
        new_job_row.pack(fill='x', pady=(0, 10))
        RoundedButton(new_job_row, t('btn_new_job'), command=self._open_new_job_dialog,
                      variant='accent', page_bg=PANEL).pack(side='left')
        self.jobs_list_frame = ttk.Frame(panel, style='Panel.TFrame')
        self.jobs_list_frame.pack(fill='both', expand=True)
        self._refresh_jobs_panel()

    def _refresh_jobs_panel(self):
        for child in self.jobs_list_frame.winfo_children():
            child.destroy()

        if not self.jobs:
            tk.Label(self.jobs_list_frame, text=t('label_no_jobs'),
                      bg=PANEL, fg=FG_MUTED, font=(FONT_UI, TYPE_CAPTION)).pack(anchor='w')
            return

        status_labels = {
            'never_run': t('job_status_never_run'), 'running': t('job_status_running'),
            'success': t('job_status_success'), 'errors': t('job_status_errors'),
            'error': t('job_status_error'),
        }
        mode_labels = {'httrack': t('job_mode_httrack'), 'smart': t('job_mode_smart'), 'both': t('job_mode_both')}
        schedule_labels = {'once': t('schedule_type_once'), 'daily': t('schedule_type_daily'),
                            'weekly': t('schedule_type_weekly')}
        for job in self.jobs:
            row = tk.Frame(self.jobs_list_frame, bg=BG, highlightbackground=BORDER, highlightthickness=1)
            row.pack(fill='x', pady=3)
            info = tk.Frame(row, bg=BG)
            info.pack(side='left', fill='x', expand=True, padx=10, pady=6)
            tk.Label(info, text=job['name'], bg=BG, fg=FG, font=(FONT_UI, TYPE_BODY_LARGE, 'bold')).pack(anchor='w')
            schedule = job.get('schedule', {})
            schedule_text = f"{schedule_labels.get(schedule.get('type'), '')} {schedule.get('at', '')}"
            status_text = status_labels.get(job.get('last_status', 'never_run'), job.get('last_status', ''))
            subtitle = f"{mode_labels.get(job.get('mode'), '')} · {schedule_text} · {status_text}"
            tk.Label(info, text=subtitle, bg=BG, fg=FG_MUTED, font=(FONT_UI, TYPE_CAPTION)).pack(anchor='w')

            btns = ttk.Frame(row)
            btns.pack(side='right', padx=10)
            RoundedButton(btns, t('btn_delete_job'), command=lambda j=job: self._delete_job(j),
                          variant='danger', page_bg=BG).pack(side='right', padx=(6, 0))
            RoundedButton(btns, t('btn_edit_job'), command=lambda j=job: self._edit_job(j),
                          variant='ghost', page_bg=BG).pack(side='right')

    def _open_new_job_dialog(self):
        ScheduleJobDialog(self.root, on_save=self._on_job_saved, log_fn=self._log, settings=self.settings)

    def _edit_job(self, job):
        ScheduleJobDialog(self.root, on_save=self._on_job_saved, log_fn=self._log,
                           settings=self.settings, existing_job=job)

    def _on_job_saved(self, job):
        self.jobs = jobs_mod.upsert_job(self.jobs, job)
        jobs_mod.save_jobs(CONFIG_DIR, self.jobs)
        self._refresh_jobs_panel()
        self._log(t('log_job_saved'))

    def _delete_job(self, job):
        scheduler_win.unregister_task(job.get('scheduler_task_name'))
        self.jobs = jobs_mod.remove_job(self.jobs, job['id'])
        jobs_mod.save_jobs(CONFIG_DIR, self.jobs)
        self._refresh_jobs_panel()
        self._log(t('log_job_deleted'))

    def _panel(self, parent, title, expand=False):
        card = RoundedCard(parent, radius=14, padding=14, expand=expand)
        card.pack(fill='both' if expand else 'x', expand=expand, pady=(0, 12))
        ttk.Label(card.body, text=title, style='Header.TLabel').pack(anchor='w', pady=(0, 8))
        card.body.card = card  # 카드 바깥 프레임 참조(셔틀다운 배너 위치 지정 등에 필요)
        return card.body

    def _schedule_shutdown(self, seconds, reason):
        try:
            subprocess.run(['shutdown', '/s', '/t', str(int(seconds))],
                            creationflags=0x08000000, check=False)
        except Exception as e:
            self._log(t('warn_shutdown_schedule_failed', e=e))
            return
        self._shutdown_armed = True
        mins = max(1, int(seconds // 60))
        self.shutdown_banner_var.set(t('shutdown_banner_text', reason=reason, mins=mins))
        self.shutdown_banner.grid(row=3, column=0, sticky='ew')
        self._log(t('notice_shutdown_scheduled', reason=reason, mins=mins))

    def _cancel_shutdown(self):
        try:
            subprocess.run(['shutdown', '/a'], creationflags=0x08000000, check=False)
        except Exception:
            pass
        self._shutdown_armed = False
        self.shutdown_banner.grid_remove()
        self._log(t('notice_shutdown_cancelled'))

    def _effective_depth(self):
        # None이면 -r 플래그를 아예 안 붙인다 = HTTrack 자체 기본값(9999, 사실상 무제한)을 그대로 사용
        if not self.limit_depth_var.get():
            return None
        try:
            return max(1, int(self.depth_var.get()))
        except ValueError:
            return None

    def _effective_filters(self):
        rules = []
        for var, exts, _label in self.filter_entries:
            if var.get():
                rules.extend(f'+*.{ext}' for ext in exts)
        rules.extend(BASE_FILTER_RULES)
        extra = self.custom_filters_var.get().strip()
        if extra:
            rules.extend(extra.split())
        return rules

    def _refresh_filter_preview(self):
        self.filter_preview_var.set(' '.join(self._effective_filters()))
        self._refresh_option_summaries()

    # ---------------- 최근 프로젝트 ----------------
    def _refresh_projects_panel(self):
        # 최근 프로젝트 목록은 지금 화면에 없다(단일 화면 단순화). 목록 데이터 자체는
        # 계속 저장되므로, 패널이 없을 때는 조용히 넘어간다.
        if not hasattr(self, 'projects_list_frame'):
            return
        for child in self.projects_list_frame.winfo_children():
            child.destroy()

        if not self.projects:
            tk.Label(self.projects_list_frame, text=t('label_no_projects'),
                      bg=PANEL, fg=FG_MUTED, font=(FONT_UI, TYPE_CAPTION)).pack(anchor='w')
            return

        status_labels = {
            'never': t('proj_status_never'), 'running': t('proj_status_running'),
            'success': t('proj_status_success'), 'errors': t('proj_status_errors'),
            'failed': t('proj_status_failed'),
        }
        ordered = sorted(self.projects, key=lambda p: p.get('last_run_at') or p.get('created_at') or '', reverse=True)
        for record in ordered[:5]:
            row = tk.Frame(self.projects_list_frame, bg=BG, highlightbackground=BORDER, highlightthickness=1)
            row.pack(fill='x', pady=3)
            info = tk.Frame(row, bg=BG)
            info.pack(side='left', fill='x', expand=True, padx=10, pady=6)
            tk.Label(info, text=record['name'], bg=BG, fg=FG, font=(FONT_UI, TYPE_BODY_LARGE, 'bold')).pack(anchor='w')
            status_text = status_labels.get(record.get('last_status', 'never'), record.get('last_status', ''))
            subtitle = f"{t('proj_url_count', n=len(record.get('urls', [])))} · {status_text} · {record.get('base_path', '')}"
            tk.Label(info, text=subtitle, bg=BG, fg=FG_MUTED, font=(FONT_UI, TYPE_CAPTION)).pack(anchor='w')

            btns = ttk.Frame(row)
            btns.pack(side='right', padx=10)
            RoundedButton(btns, t('btn_delete_project'), command=lambda r=record: self._delete_project(r),
                          variant='danger', page_bg=BG).pack(side='right', padx=(6, 0))
            RoundedButton(btns, t('btn_ai_extract'), command=lambda r=record: self._open_ai_extract_dialog(r),
                          variant='ghost', page_bg=BG).pack(side='right', padx=(6, 0))
            RoundedButton(btns, t('btn_continue_project'), command=lambda r=record: self._continue_project(r),
                          variant='ghost', page_bg=BG).pack(side='right', padx=(6, 0))
            RoundedButton(btns, t('btn_load_project'), command=lambda r=record: self._load_project_into_form(r),
                          variant='ghost', page_bg=BG).pack(side='right')

    def _load_project_into_form(self, record, action_code=None):
        self.project_var.set(record['name'])
        self.base_path_var.set(record['base_path'])
        self._set_urls(record.get('urls', []))

        code = action_code or record.get('action_code', '1')
        label = next((lbl for c, lbl in self.actions if c == code), self.actions[0][1])
        self.action_var.set(label)

        depth = record.get('depth')
        if depth is None:
            self.all_scope_var.set(True)
            self.limit_depth_var.set(False)
        else:
            self.all_scope_var.set(False)
            self.limit_depth_var.set(True)
            self.depth_var.set(str(depth))
        self._refresh_option_summaries()

    def _continue_project(self, record):
        # 이어받기(action=5)로 강제 전환해서 폼에 불러온 뒤, 확인창을 거쳐 바로 시작 흐름을 탄다.
        self._load_project_into_form(record, action_code='5')
        self._on_start_clicked()

    def _delete_project(self, record):
        self.projects = [p for p in self.projects if p is not record]
        save_projects(self.projects)
        self._refresh_projects_panel()

    def _open_ai_extract_dialog(self, record):
        out_dir = os.path.join(record['base_path'], record['name'])
        AIExtractRunDialog(self.root, out_dir, self.settings, log_fn=self._log,
                            on_run=lambda config: self._start_ai_extract_thread(out_dir, config))

    def _start_ai_extract_thread(self, out_dir, config):
        if not config.get('enabled') or not config.get('fields'):
            self._log(t('warn_need_fields'))
            return
        ai_config = get_active_ai_config(self.settings)
        if not ai_config.get('api_key'):
            self._log(t('warn_need_api_key'))
            return
        self._log(t('log_ai_extract_started'))

        def worker():
            ai_extract.run_extraction(
                out_dir, config['fields'], ai_config['api_key'], provider=ai_config['provider'],
                log_fn=lambda msg: self.msg_queue.put(('log', msg)),
                max_pages=200, export_formats=config['export_formats'])

        threading.Thread(target=worker, daemon=True).start()

    # ---------------- 동작 ----------------
    def _open_preferences(self):
        if getattr(self, '_busy', False):
            return
        PreferencesDialog(self.root, self.settings, on_save=self._on_prefs_saved)

    def _on_prefs_saved(self):
        # 환경설정에서 바꾼 쿠키 설정이 스마트 옵션 창의 토글에도 반영되게 맞춰준다.
        self.use_local_cookies_var.set(bool(self.settings.get('use_local_cookies', False)))
        self._log(t('log_prefs_saved'))

    def _browse_folder(self):
        selected = filedialog.askdirectory(
            initialdir=self.base_path_var.get() if os.path.isdir(self.base_path_var.get() or '') else os.path.expanduser('~'),
            title=t('dialog_browse_folder_title'), parent=self.root)
        if selected:
            self.base_path_var.set(selected)

    def _load_url_file(self):
        selected = filedialog.askopenfilename(title=t('dialog_load_url_file_title'), parent=self.root)
        if not selected:
            return
        try:
            with open(selected, 'r', encoding='utf-8', errors='replace') as f:
                lines = [line.strip() for line in f if line.strip()]
        except Exception as e:
            self._log(t('warn_url_file_failed', e=e))
            return
        if not lines:
            return
        self._set_urls(self._get_urls() + lines)
        self._log(t('log_loaded_urls', n=len(lines)))

    def _log(self, text):
        self.log_text.configure(state='normal')
        self.log_text.insert('end', text + '\n')
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def _clear_log(self):
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.configure(state='disabled')

    def _reset_progress_ui(self):
        self.progress_var.set(0)
        self._max_progress = 0.0
        self.start_button.set_progress(0)
        self._set_status('')
        for lbl in (self.elapsed_stat, self.links_stat, self.files_stat, self.bytes_stat,
                    self.speed_stat, self.errors_stat):
            lbl.configure(text='-')

    def _push_progress_to_ui(self, snapshot):
        done = snapshot.get('links_done', 0)
        total = snapshot.get('links_total', 0)
        pct = (done / total * 100) if total else 0
        self.progress_var.set(pct)
        # HTTrack은 받는 도중에 새 링크를 계속 발견해서 분모(links_total)가 커진다.
        # 그래서 done/total을 그대로 쓰면 36% -> 13%처럼 진행률이 뒤로 가서 사용자가
        # 혼란스럽다. 지금까지 도달한 최대치를 유지해 링이 뒤로 가지 않게 한다.
        # (실제 숫자는 '스캔한 링크' 카드에 그대로 보여주므로 정보는 잃지 않는다.)
        self._max_progress = max(getattr(self, '_max_progress', 0.0), pct)
        self.start_button.set_progress(self._max_progress)
        job_raw = snapshot.get('current_job', '')
        self._set_status(get_job_labels().get(job_raw, job_raw or t('status_running')))
        self.elapsed_stat.configure(text=snapshot.get('elapsed_time', '-'))
        self.links_stat.configure(text=f'{done}/{total}' if total else '-')
        self.files_stat.configure(text=str(snapshot.get('files_written', '-')))
        self.bytes_stat.configure(text=friendly_size(snapshot.get('bytes_saved', '-')))
        self.speed_stat.configure(text=friendly_size(snapshot.get('transfer_rate', '-')))
        self.errors_stat.configure(text=str(snapshot.get('errors', 0)))

    def _on_start_clicked(self):
        p_name = self.project_var.get().strip()
        b_path = self.base_path_var.get().strip()
        urls = self._get_urls()

        if not urls:
            self._log(t('warn_need_url'))
            return
        if not p_name:
            self._log(t('warn_need_project_name'))
            return

        power_mode = self.power_action_var.get()
        if power_mode == 'after_hours':
            power_label = t('power_text_after_hours', hours=self.power_hours_var.get())
        elif power_mode == 'on_complete':
            power_label = t('power_text_on_complete')
        else:
            power_label = t('power_text_none')

        if self.mode_var.get() == 'smart':
            summary = [
                (t('summary_project_name'), p_name),
                (t('summary_save_location'), os.path.join(b_path, p_name)),
                (t('summary_target_urls'), t('url_count', n=len(urls))),
                (t('summary_action'), t('mode_smart')),
                (t('panel_smart_options'), t('summary_smart_value',
                                             pages=self.max_pages_var.get(),
                                             depth=self.follow_depth_var.get())),
                (t('summary_power'), power_label),
            ]
            StartConfirmDialog(self.root, summary,
                               on_confirm=lambda: self._launch_smart_crawl(p_name, b_path, urls))
            return

        if not os.path.exists(HTTRACK_EXE):
            self._log(t('error_engine_missing', path=HTTRACK_EXE))
            return

        # 같은 폴더에 이미 받아둔 게 있으면, 통째로 다시 받기 전에 먼저 물어본다.
        kind = existing_mirror_kind(os.path.join(b_path, p_name))
        if kind and not getattr(self, '_skip_existing_check', False):
            ExistingMirrorDialog(
                self.root, kind,
                on_choose=lambda code: self._confirm_mirror_start(p_name, b_path, urls, code))
            return

        self._confirm_mirror_start(p_name, b_path, urls, None)

    def _confirm_mirror_start(self, p_name, b_path, urls, action_code=None):
        """(기존 미러 확인을 마친 뒤) 최종 요약을 보여주고 시작한다.
        action_code가 오면 '수집 방식'을 그 값으로 맞춰 사용자가 고른 대로 동작하게 한다."""
        if action_code is not None:
            label = next((lbl for c, lbl in self.actions if c == action_code), None)
            if label:
                self.action_var.set(label)

        power_mode = self.power_action_var.get()
        if power_mode == 'after_hours':
            power_label = t('power_text_after_hours', hours=self.power_hours_var.get())
        elif power_mode == 'on_complete':
            power_label = t('power_text_on_complete')
        else:
            power_label = t('power_text_none')

        action_label = self.action_var.get()
        depth = self._effective_depth()
        scope_text = t('scope_unlimited') if depth is None else t('scope_n_levels', depth=depth)
        if self.same_folder_var.get():
            scope_text += f" · {t('label_same_folder')}"
        summary = [
            (t('summary_project_name'), p_name),
            (t('summary_save_location'), os.path.join(b_path, p_name)),
            (t('summary_target_urls'), t('url_count', n=len(urls))),
            (t('summary_action'), action_label),
            (t('summary_scope'), scope_text),
            (t('summary_power'), power_label),
        ]
        StartConfirmDialog(self.root, summary, on_confirm=lambda: self._launch_mirroring(p_name, b_path, urls))

    def _remember_project(self, p_name, b_path, urls, action_code, depth=None):
        """실행 시작 시점에 프로젝트 기록을 남긴다(미러링·스마트 크롤링 공용)."""
        self._current_project_key = (p_name, b_path)
        self.projects = upsert_project(self.projects, {
            'name': p_name, 'base_path': b_path, 'urls': urls,
            'action_code': action_code, 'depth': depth,
            'last_status': 'running',
            'last_run_at': datetime.now().isoformat(),
            'created_at': datetime.now().isoformat(),
        })
        save_projects(self.projects)
        self._refresh_projects_panel()

    def _finish_project_record(self, project_status):
        """실행이 끝났을 때 상태를 갱신하고 미리보기 썸네일을 백그라운드로 찍는다."""
        if self._current_project_key is None:
            return
        name, base_path = self._current_project_key
        for record in self.projects:
            if (record['name'], record['base_path']) == (name, base_path):
                record['last_status'] = project_status
                record['last_run_at'] = datetime.now().isoformat()
                break
        save_projects(self.projects)
        self._refresh_projects_panel()
        if project_status in ('success', 'errors'):
            project_dir = os.path.join(base_path, name)
            threading.Thread(target=self._capture_preview_worker,
                             args=(name, base_path, project_dir), daemon=True).start()

    def _launch_smart_crawl(self, p_name, b_path, urls):
        """스마트 크롤링을 지금 바로 실행한다(예약이 아니라 즉시 실행 경로).
        run_smart_crawl은 동기 함수라 스레드로 돌리고, 진행 상황은 기존 미러링과
        똑같이 큐를 통해 UI로 넘긴다."""
        out_dir = os.path.join(b_path, p_name)
        os.makedirs(out_dir, exist_ok=True)
        self.settings['base_path'] = b_path
        save_settings(self.settings)
        self._remember_project(p_name, b_path, urls, None)

        self._user_stopped = False
        self.start_button.set_running(True)
        self._set_busy(True)
        self.open_folder_btn.set_enabled(False)
        self._clear_log()
        self._reset_progress_ui()
        self._log(t('log_smart_started'))
        self._smart_started_at = time.time()

        job = {
            'urls': urls,
            'save_path': out_dir,
            'smart': {'wait_until': self.wait_until_var.get(),
                      'max_pages': int(self.max_pages_var.get() or 50)},
            'httrack': {'depth': self.follow_depth_var.get()},
            'scope': {'domain_scope': next(
                (code for code, label in self.domain_scope_options
                 if label == self.domain_scope_var.get()), 'host')},
            'use_local_cookies': bool(self.use_local_cookies_var.get()),
        }

        def worker():
            ok = smart_crawl.run_smart_crawl(
                job,
                log_fn=lambda msg: self.msg_queue.put(('log', msg)),
                progress_fn=lambda snap: self.msg_queue.put(('smart_progress', snap)),
                should_stop=lambda: self._user_stopped)
            self.msg_queue.put(('smart_done', ok))

        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()

    def _push_smart_progress(self, snap):
        visited = snap.get('visited', 0)
        max_pages = snap.get('max_pages', 0) or 1
        self.start_button.set_progress(min(100.0, visited / max_pages * 100))
        elapsed = int(time.time() - getattr(self, '_smart_started_at', time.time()))
        self.elapsed_stat.configure(text=f'{elapsed // 60:02d}:{elapsed % 60:02d}')
        self.links_stat.configure(text=f"{visited}/{snap.get('max_pages', '-')}")
        self.files_stat.configure(text=str(visited))
        self.bytes_stat.configure(text=format_bytes(snap.get('bytes_saved', 0)))
        self.speed_stat.configure(text='-')   # 스마트 크롤링은 전송 속도를 따로 재지 않는다
        self.errors_stat.configure(text=str(snap.get('errors', 0)))
        current = snap.get('current_url') or ''
        self._set_status(current[:60] + '…' if len(current) > 60 else (current or t('status_running')))

    def _on_smart_done(self, ok):
        self.start_button.set_running(False)
        self._set_busy(False)
        self._sync_start_button()
        if self._user_stopped:
            self._set_status(t('status_stopped'), emphasis=True)
        else:
            self._set_status(t('status_done') if ok else t('log_smart_failed'), emphasis=True)
        pages = self.files_stat.cget('text')
        self._log(t('log_smart_done', n=pages) if ok else t('log_smart_failed'))
        if ok:
            self.open_folder_btn.set_enabled(True)
        self._finish_project_record('success' if ok else 'errors')
        if self.power_action_var.get() == 'on_complete' and not self._user_stopped:
            self._schedule_shutdown(60, t('reason_on_complete'))

    def _launch_mirroring(self, p_name, b_path, urls):
        out_dir = os.path.join(b_path, p_name)
        os.makedirs(out_dir, exist_ok=True)

        # 마지막으로 사용한 저장 경로를 환경설정에 기록해 다음 실행 때 기본값으로 사용
        self.settings['base_path'] = b_path
        save_settings(self.settings)

        self._user_stopped = False
        if self.power_action_var.get() == 'after_hours':
            try:
                hours = float(self.power_hours_var.get())
            except ValueError:
                hours = 2
            self._schedule_shutdown(hours * 3600, t('reason_after_hours'))

        self.start_button.set_running(True)
        self._set_busy(True)
        self.open_folder_btn.set_enabled(False)
        self._clear_log()
        self._reset_progress_ui()

        self._log(f"[{datetime.now().strftime('%H:%M:%S')}] {t('log_engine_init')}")
        self._log(f"[{datetime.now().strftime('%H:%M:%S')}] {t('log_project_folder', path=out_dir)}")

        action_code = next((code for code, label in self.actions if label == self.action_var.get()), '1')
        depth_for_record = self._effective_depth()

        self._current_project_key = (p_name, b_path)
        record = {
            'name': p_name,
            'base_path': b_path,
            'urls': urls,
            'action_code': action_code,
            'depth': depth_for_record,
            'last_status': 'running',
            'last_run_at': datetime.now().isoformat(),
            'created_at': datetime.now().isoformat(),
        }
        self.projects = upsert_project(self.projects, record)
        save_projects(self.projects)
        self._refresh_projects_panel()

        safety = {'pause': None, 'maxtime_hours': None, 'maxsize_mb': None,
                  'hostcontrol': next((code for code, label in self.hostcontrol_options
                                       if label == self.hostcontrol_var.get()), 'none')}
        if self.pause_enable_var.get():
            try:
                p_min = max(0, int(self.pause_min_var.get()))
                p_max = max(p_min, int(self.pause_max_var.get()))
                safety['pause'] = (p_min, p_max)
            except ValueError:
                pass
        if self.maxtime_enable_var.get():
            try:
                safety['maxtime_hours'] = float(self.maxtime_hours_var.get())
            except ValueError:
                pass
        if self.maxsize_enable_var.get():
            try:
                safety['maxsize_mb'] = int(self.maxsize_mb_var.get())
            except ValueError:
                pass

        domain_scope_code = next(
            (code for code, label in self.domain_scope_options if label == self.domain_scope_var.get()), 'host')
        scope = {'same_folder': self.same_folder_var.get(), 'domain_scope': domain_scope_code}

        cmd = build_httrack_cmd(urls, out_dir, action_code, depth_for_record, self._effective_filters(),
                                 self.settings, safety, scope, log_fn=self._log)

        self._log(f"[{datetime.now().strftime('%H:%M:%S')}] {t('log_command', cmd=' '.join(cmd))}")

        self.progress_state = {'last_update': 0.0}
        self.worker_thread = threading.Thread(target=self._run_subprocess, args=(cmd,), daemon=True)
        self.worker_thread.start()

    def _stop_mirroring(self):
        # 스마트 크롤링은 서브프로세스가 아니라 스레드라서, 플래그를 세우면
        # run_smart_crawl이 다음 페이지로 넘어가기 전에 스스로 멈춘다.
        self._user_stopped = True
        if self.mode_var.get() == 'smart':
            self.msg_queue.put(('log', t('log_user_stopped')))
            return
        if self.current_process and self.current_process.poll() is None:
            self._user_stopped = True
            self.current_process.terminate()
            self.msg_queue.put(('log', f"[{datetime.now().strftime('%H:%M:%S')}] {t('log_user_stopped')}"))

    def _run_subprocess(self, cmd):
        """백그라운드 스레드에서 실행. tkinter 위젯은 직접 건드리지 않고 큐에만 메시지를 넣는다.
        실제 실행/파싱 로직은 run_httrack()/parse_dashboard_line()에 있음 (헤드리스 스케줄러와 공용)."""
        def on_process(proc):
            self.current_process = proc

        def on_log(line):
            self.msg_queue.put(('log', line))

        def on_progress(state):
            self.msg_queue.put(('progress', state))

        def on_done(result, engine_errors):
            self.msg_queue.put(('done', result, engine_errors))

        run_httrack(cmd, on_log, on_progress, on_done, on_process=on_process)

    def _capture_preview_worker(self, name, base_path, project_dir):
        out_path = preview_path_for(name, base_path)
        ok = preview.capture_preview(project_dir, out_path)
        self.msg_queue.put(('preview', name, base_path, out_path if ok else None))

    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                kind = msg[0]
                if kind == 'log':
                    self._log(msg[1])
                elif kind == 'progress':
                    self._push_progress_to_ui(msg[1])
                elif kind == 'done':
                    self._on_job_done(msg[1], msg[2])
                elif kind == 'preview':
                    self._on_preview_captured(msg[1], msg[2], msg[3])
                elif kind == 'smart_progress':
                    self._push_smart_progress(msg[1])
                elif kind == 'smart_done':
                    self._on_smart_done(msg[1])
        except queue.Empty:
            pass
        self.root.after(80, self._poll_queue)

    def _on_preview_captured(self, name, base_path, preview_path_value):
        for record in self.projects:
            if (record['name'], record['base_path']) == (name, base_path):
                record['preview_path'] = preview_path_value
                break
        save_projects(self.projects)
        self._refresh_projects_panel()

    def _on_job_done(self, result, engine_errors):
        ts = datetime.now().strftime('%H:%M:%S')
        # HTTrack은 접속 실패 등으로 실제로는 아무것도 받지 못했어도 종료 코드
        # 자체는 0을 반환하는 경우가 있어, 파싱한 오류 건수도 함께 확인해야 한다.
        if isinstance(result, int) and result == 0 and engine_errors == 0:
            self._log(f"\n[{ts}] {t('log_success')}")
            self.open_folder_btn.set_enabled(True)
            project_status = 'success'
        elif isinstance(result, int) and result == 0 and engine_errors > 0:
            self._log(f"\n[{ts}] {t('log_done_with_errors', n=engine_errors)}")
            self.open_folder_btn.set_enabled(True)
            project_status = 'errors'
        elif isinstance(result, int):
            self._log(f"\n[{ts}] {t('log_done_code', code=result)}")
            self.open_folder_btn.set_enabled(True)
            project_status = 'errors'
        else:
            self._log(f"\n[{ts}] {t('log_fatal_error', result=result)}")
            project_status = 'failed'

        self.start_button.set_running(False)
        self._set_busy(False)
        self._sync_start_button()
        if self._user_stopped:
            self._set_status(t('status_stopped'), emphasis=True)
        elif engine_errors:
            self._set_status(t('status_done_errors', n=engine_errors), emphasis=True)
        else:
            self._set_status(t('status_done'), emphasis=True)

        if self._current_project_key is not None:
            name, base_path = self._current_project_key
            for record in self.projects:
                if (record['name'], record['base_path']) == (name, base_path):
                    record['last_status'] = project_status
                    record['last_run_at'] = datetime.now().isoformat()
                    break
            save_projects(self.projects)
            self._refresh_projects_panel()

            # 뭔가 받아진 경우에만(완전 실패면 미리볼 것도 없음) 백그라운드로
            # 썸네일을 찍는다 - Chrome을 새로 띄우는 작업이라 몇 초 걸리므로
            # UI를 막지 않게 스레드로 돌리고 큐를 통해 결과만 반영한다.
            if project_status in ('success', 'errors'):
                project_dir = os.path.join(base_path, name)
                threading.Thread(target=self._capture_preview_worker,
                                  args=(name, base_path, project_dir), daemon=True).start()

        if self.power_action_var.get() == 'on_complete' and not self._user_stopped:
            self._schedule_shutdown(60, t('reason_on_complete'))

    def _open_result_folder(self):
        out_dir = os.path.join(self.base_path_var.get().strip(), self.project_var.get().strip())
        if os.path.isdir(out_dir):
            os.startfile(out_dir)  # 로컬 데스크톱 앱에서 사용자가 직접 누른 버튼으로만 호출됨
        else:
            self._log(t('warn_folder_not_found'))

    def _on_close(self):
        if self.current_process and self.current_process.poll() is None:
            self.current_process.terminate()
        self.root.destroy()


def main_headless(job_id):
    """예약 크롤링(schtasks)이 지정 시각에 창 없이 실행하는 진입점. GUI(tk.Tk())는 절대 만들지 않는다."""
    jobs_list = jobs_mod.load_jobs(CONFIG_DIR)
    job = jobs_mod.find_job(jobs_list, job_id)
    if job is None:
        return 1

    log_dir = os.path.join(CONFIG_DIR, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f'{job_id}.log')

    def log(msg):
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {msg}\n')

    def save_job_status(status, preview_path_value=None):
        current_jobs = jobs_mod.load_jobs(CONFIG_DIR)
        current = jobs_mod.find_job(current_jobs, job_id)
        if current is not None:
            current['last_status'] = status
            current['last_run_at'] = datetime.now().isoformat()
            current['last_log_path'] = log_path
            if preview_path_value is not None:
                current['preview_path'] = preview_path_value
            jobs_mod.save_jobs(CONFIG_DIR, current_jobs)

    save_job_status('running')
    status = 'success'
    try:
        settings = load_settings()
        if job['mode'] in ('httrack', 'both'):
            httrack_opts = job.get('httrack', {}) or {}
            cmd = build_httrack_cmd(
                job['urls'], job['save_path'], httrack_opts.get('action', '1'),
                httrack_opts.get('depth'), httrack_opts.get('filters', []), settings, log_fn=log)
            log('Running: ' + ' '.join(cmd))
            outcome = {}

            def on_done(rc, engine_errors):
                outcome['rc'] = rc
                outcome['errors'] = engine_errors

            run_httrack(cmd, on_log=log, on_progress=lambda s: None, on_done=on_done)
            rc = outcome.get('rc')
            if not (isinstance(rc, int) and rc == 0 and outcome.get('errors', 0) == 0):
                status = 'errors'

        if job['mode'] in ('smart', 'both'):
            # 브라우저 로그인 사용 여부는 전역 설정이므로 job에 실어서 넘긴다
            # (예전엔 job에 이 키를 넣는 곳이 없어 스마트 크롤링 쿠키 주입이 늘 꺼져 있었다).
            job = dict(job, use_local_cookies=bool(settings.get('use_local_cookies')))
            ok = smart_crawl.run_smart_crawl(job, log)
            if not ok:
                status = 'errors'

        # 크롤링 방식과 무관하게, 저장 폴더 안의 .html 파일들에 대해 동작하는 후처리 단계.
        ai_cfg = job.get('ai_extract') or {}
        if ai_cfg.get('enabled') and ai_cfg.get('fields'):
            ai_config = get_active_ai_config(settings)
            if ai_config.get('api_key'):
                log(t('log_ai_extract_started'))
                max_pages = (job.get('smart', {}) or {}).get('max_pages', 50)
                ai_extract.run_extraction(
                    job['save_path'], ai_cfg['fields'], ai_config['api_key'], provider=ai_config['provider'],
                    log_fn=log, max_pages=max_pages, export_formats=ai_cfg.get('export_formats', ['csv']))
            else:
                log(t('warn_ai_skip_no_key'))
    except Exception as e:
        log(f'FATAL: {e}')
        status = 'error'

    preview_path_value = None
    if status in ('success', 'errors'):
        # 예약 작업의 job_id는 파일 시스템에 안전한 값(uuid)이라 그대로 파일명으로 쓸 수 있다.
        candidate_path = os.path.join(CONFIG_DIR, 'previews', f'{job_id}.png')
        if preview.capture_preview(job['save_path'], candidate_path):
            preview_path_value = candidate_path

    save_job_status(status, preview_path_value)
    return 0


def main():
    root = tk.Tk()
    MirrorXApp(root)
    root.mainloop()


if __name__ == '__main__':
    multiprocessing.freeze_support()  # PyInstaller로 얼린 실행 파일에서 multiprocessing 사용 시 필수
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', help='예약된 헤드리스 크롤링 작업 ID (Windows 작업 스케줄러가 호출)')
    cli_args, _unknown = parser.parse_known_args()
    if cli_args.job:
        sys.exit(main_headless(cli_args.job))
    main()
