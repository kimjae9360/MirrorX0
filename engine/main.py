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
from tkinter import ttk, filedialog, scrolledtext, messagebox
from datetime import datetime

import jobs as jobs_mod
import scheduler_win
import smart_crawl
import pagination_extract
import click_select
import clean_organize
import ollama_setup
import ai_extract
import ai_scope
import data_refine
import preview


# 환경설정 저장 위치 (실행 파일 위치와 무관하게 항상 쓰기 가능한 사용자 폴더 사용)
CONFIG_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'MirrorX')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'settings.json')


# 화면 문구와 언어 전환은 i18n.py로 분리했다 (문구만 800줄이 넘어서
# main.py에 두면 코드가 묻힌다). t()/STRINGS 등은 그대로 쓸 수 있다.
from i18n import (
    LANG_DISPLAY, STRINGS, set_language, t,
    get_actions, get_robots_options, get_filter_groups, get_job_labels,
)


# 색상/폰트/글자크기는 theme.py로 분리했다. 폰트는 실행 중에 확정되므로
# 이름이 아니라 FONTS 딕셔너리로 공유한다(자세한 이유는 theme.py 첫머리 참고).
from theme import *  # noqa: F403  (색상/크기 상수 일괄 로드)
from theme import FONTS, resolve_fonts

# 설정/프로젝트 파일 입출력은 storage.py로 분리했다.
import storage
from storage import (  # noqa: F401
    CONFIG_DIR, CONFIG_FILE, load_settings, save_settings,
    get_active_ai_config, ai_ready, PROJECTS_FILE, load_projects, save_projects,
    DEFAULT_SETTINGS,
    preview_path_for, upsert_project,
)
storage.init_defaults(DEFAULT_SETTINGS)

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
        canvas.create_text(x_center, baseline + 12, text=labels[i], font=(FONTS['ui'], 9), fill=FG_MUTED)


def draw_donut_chart(canvas, success, errors, width, height):
    """성공/오류 비율을 도넛(링) 형태로 그린다."""
    canvas.delete('all')
    total = success + errors
    cx, cy = width / 2, height / 2
    r = min(width, height) / 2 - 10
    if total <= 0:
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=BORDER, width=14)
        canvas.create_text(cx, cy, text='-', font=(FONTS['ui'], TYPE_BODY_LARGE, 'bold'), fill=FG_MUTED)
        return
    success_angle = 360 * success / total
    if success_angle > 0:
        canvas.create_arc(cx - r, cy - r, cx + r, cy + r, start=90, extent=-success_angle,
                           style='arc', outline=SUCCESS, width=14)
    if success_angle < 360:
        canvas.create_arc(cx - r, cy - r, cx + r, cy + r, start=90 - success_angle, extent=-(360 - success_angle),
                           style='arc', outline=CRITICAL, width=14)
    pct = int(round(100 * success / total))
    canvas.create_text(cx, cy, text=f'{pct}%', font=(FONTS['ui'], TYPE_TITLE, 'bold'), fill=FG)


# 화면 부품(둥근 카드/버튼/토글/원형 시작 버튼 등)은 widgets.py로 분리했다.
from webutil import normalize_url, _fetch_sample_html_from_url  # noqa: F401
# 창(다이얼로그)들은 dialogs.py로 분리했다. 기존 참조가 그대로 동작하도록 재export한다.
from dialogs import (  # noqa: F401
    PreferencesDialog, ExistingMirrorDialog, StartConfirmDialog, ScheduleJobDialog,
    AIExtractPanel, AIExtractRunDialog, PaginationExtractDialog, ClickToSelectDialog,
    DataToolsDialog, AIRefineDialog, AIScopeRulesDialog, OptionsDialog,
)
from widgets import (  # noqa: F401
    make_scrollable, combo_width, display_width, _rounded_rect_points, lerp_color,
    draw_vertical_gradient, draw_soft_shadow,
    BrandHeader, SegmentedControl, CircularStartButton,
    RoundedCard, RoundedButton, ToggleSwitch,
)




























# ---------------- HTTrack 실행 엔진 (GUI/헤드리스 공용) ----------------
# GUI(스레드+큐)와 헤드리스 예약 작업(스케줄러) 양쪽에서 그대로 재사용할 수 있도록
# Tkinter에 의존하지 않는 순수 함수로 분리해둔다.

# HTTrack 명령 조립/실행/진행률 파싱은 httrack_engine.py로 분리했다.
from httrack_engine import (  # noqa: F401
    HTTRACK_EXE, ACTION_FLAGS, DEFAULT_FILTERS, BASE_FILTER_RULES,
    existing_mirror_kind, cookie_domains_for, export_local_cookies,
    build_httrack_cmd, parse_dashboard_line, run_httrack,
)



class MirrorXApp:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        self._current_lang = self.settings.get('language', 'en')
        set_language(self._current_lang)
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

        base_font = (FONTS['ui'], TYPE_BODY)
        style.configure('.', background=BG, foreground=FG, fieldbackground=PANEL_LIGHT, font=base_font)
        style.configure('TFrame', background=BG)
        style.configure('Panel.TFrame', background=PANEL)
        style.configure('PanelLight.TFrame', background=PANEL_LIGHT)
        style.configure('Stat.TFrame', background=STAT_BG)
        style.configure('TLabel', background=BG, foreground=FG, font=base_font)
        style.configure('Panel.TLabel', background=PANEL, foreground=FG, font=base_font)
        style.configure('Muted.TLabel', background=PANEL, foreground=FG_MUTED, font=base_font)
        style.configure('MutedRoot.TLabel', background=BG, foreground=FG_MUTED, font=base_font)
        style.configure('Header.TLabel', background=PANEL, foreground=FG, font=(FONTS['ui'], TYPE_SUBTITLE, 'bold'))
        style.configure('RowTitle.TLabel', background=PANEL, foreground=FG, font=(FONTS['ui'], TYPE_BODY, 'bold'))
        style.configure('Title.TLabel', background=BG, foreground=ACCENT, font=(FONTS['ui'], TYPE_TITLE, 'bold'))
        style.configure('Title2.TLabel', background=BG, foreground=FG, font=(FONTS['ui'], TYPE_SUBTITLE, 'bold'))
        style.configure('Sub.TLabel', background=BG, foreground=FG_MUTED, font=(FONTS['ui'], TYPE_CAPTION))
        style.configure('Caption.TLabel', background=PANEL, foreground=FG_MUTED, font=(FONTS['ui'], TYPE_CAPTION))
        style.configure('Badge.TLabel', background=ACCENT_SOFT, foreground=ACCENT,
                         font=(FONTS['ui'], TYPE_CAPTION, 'bold'), padding=(9, 4))

        style.configure('TCheckbutton', background=PANEL, foreground=FG, font=base_font)
        style.map('TCheckbutton', background=[('active', PANEL)])
        style.configure('TRadiobutton', background=PANEL, foreground=FG, font=base_font)
        style.map('TRadiobutton', background=[('active', PANEL)])

        # 실제로 타이핑하는 입력창은 본문보다 한 단계 크게 - 작으면 읽기 불편하다.
        field_font = (FONTS['ui'], TYPE_INPUT)
        # 입력칸 색 규칙: 흰색 = 지금 입력할 수 있음 / 회색 = 잠김(작업 중).
        # 거의 모든 프로그램에서 '회색으로 채워진 칸'은 비활성을 뜻하기 때문에,
        # 입력 가능한 칸을 회색으로 두면 정반대 신호를 준다. 대신 흰 배경에
        # 테두리로 칸의 경계를 보여주고, 커서가 들어가면 테두리를 강조색으로 바꾼다.
        style.configure('TEntry', fieldbackground=PANEL, foreground=FG, insertcolor=FG,
                         bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, font=field_font,
                         padding=6)
        style.map('TEntry',
                  fieldbackground=[('disabled', PANEL_LIGHT), ('readonly', PANEL_LIGHT)],
                  foreground=[('disabled', FG_MUTED), ('readonly', FG_MUTED)],
                  bordercolor=[('focus', ACCENT)], lightcolor=[('focus', ACCENT)],
                  darkcolor=[('focus', ACCENT)])

        style.configure('TCombobox', fieldbackground=PANEL, foreground=FG, arrowcolor=FG_MUTED,
                         bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                         font=field_font, padding=5)
        # 드롭다운은 state='readonly'로 쓰므로(직접 타이핑 못 하게) readonly도 '입력 가능'
        # 취급해야 한다. 진짜 잠긴 상태는 disabled 하나뿐이다.
        style.map('TCombobox',
                  fieldbackground=[('disabled', PANEL_LIGHT), ('readonly', PANEL)],
                  foreground=[('disabled', FG_MUTED), ('readonly', FG)],
                  arrowcolor=[('disabled', BORDER)],
                  bordercolor=[('focus', ACCENT)])

        style.configure('TSpinbox', fieldbackground=PANEL, foreground=FG, arrowsize=14,
                         bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, font=field_font)
        style.map('TSpinbox',
                  fieldbackground=[('disabled', PANEL_LIGHT)],
                  foreground=[('disabled', FG_MUTED)],
                  arrowcolor=[('disabled', BORDER)],
                  bordercolor=[('focus', ACCENT)])

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
                         font=(FONTS['ui'], TYPE_BODY, 'bold'), borderwidth=0)
        style.map('Accent.TButton', background=[('active', ACCENT_HOVER), ('disabled', '#E7E1D4')])
        style.configure('Danger.TButton', background=RED, foreground=ON_DANGER, padding=(18, 10),
                         font=(FONTS['ui'], TYPE_BODY, 'bold'), borderwidth=0)
        style.map('Danger.TButton', background=[('active', '#A82317')])

        style.configure('Horizontal.TProgressbar', background=ACCENT, troughcolor=PANEL_LIGHT,
                         bordercolor=PANEL, lightcolor=ACCENT, darkcolor=ACCENT, thickness=10)
        style.configure('TScale', background=PANEL, troughcolor=PANEL_LIGHT)

        # 탭 (Notebook) - 지금 보고 있는 탭이 뚜렷이 커지고 색도 분명히 달라지도록
        style.configure('TNotebook', background=BG, borderwidth=0, tabmargins=(0, 8, 0, 0))
        style.configure('TNotebook.Tab', background=TAB_INACTIVE, foreground=FG_MUTED,
                         font=(FONTS['ui'], TYPE_BODY), padding=(18, 9), borderwidth=0)
        style.map('TNotebook.Tab',
                  background=[('selected', BG)],
                  foreground=[('selected', ACCENT)],
                  font=[('selected', (FONTS['ui'], TYPE_BODY_LARGE, 'bold'))],
                  padding=[('selected', (26, 14))])

    def _build_ui(self):
        self.root.title('MirrorX0')
        # 좌측 내비게이션(260px)이 생긴 만큼 창도 그만큼 넓게 잡는다.
        self.root.geometry('1560x900')
        self.root.minsize(1240, 740)

        # 스크롤 없이 한 화면에 다 들어가는 구조. grid의 weight로 창을 줄이면
        # 각 영역이 같이 줄어들고(원형 버튼까지), minsize가 하한을 지켜준다.
        #   0행 브랜드 배너 / 1행 히어로(통계 · 원형 시작버튼 · 통계) / 2행 하단(설정 | 로그)
        # 예약 작업은 별도 사이드바가 아니라, 설정 카드 하단의 요약 행(스마트
        # 크롤링 옵션·완료 후 동작과 같은 자리)으로 둔다 - 지금 하려는 작업의
        # 설정값들과 나란히 있는 편이 "이게 왜 여기 있는지" 더 잘 와닿는다.
        root_frame = tk.Frame(self.root, bg=BG)
        root_frame.pack(fill='both', expand=True)
        root_frame.grid_columnconfigure(0, weight=0)
        root_frame.grid_columnconfigure(1, weight=1)
        root_frame.grid_rowconfigure(2, weight=1)
        self._root_frame = root_frame

        header = BrandHeader(root_frame, t('app_subtitle'))
        header.grid(row=0, column=0, columnspan=2, sticky='ew')

        # 이 앱이 하는 일은 크게 둘 - '사이트를 통째로 받기'와 '데이터를 뽑기'.
        # 둘은 결과물이 아예 달라서(파일 폴더 vs 표), 화면 안에서 토글로 섞기보다
        # 좌측에 늘 보이는 두 갈래로 두는 편이 헷갈리지 않는다.
        # 내비게이션이 이 값을 읽으므로 히어로보다 먼저 만들어 둔다.
        self.intent_var = tk.StringVar(value='save')
        nav = tk.Frame(root_frame, bg=PANEL, width=self.NAV_WIDTH_OPEN)
        nav.grid(row=1, column=0, rowspan=2, sticky='ns')
        nav.grid_propagate(False)
        self._build_nav(nav)

        self._build_hero(root_frame)

        bottom = tk.Frame(root_frame, bg=BG)
        bottom.grid(row=2, column=1, sticky='nsew', padx=26, pady=(4, 20))
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
                 font=(FONTS['ui'], TYPE_CAPTION, 'bold'), padx=14, pady=9).pack(side='left')
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
        # 깊이 1은 '링크를 아예 안 따라감'이라, 최대 50페이지로 둬도 실제로는
        # 시작 주소 한 장만 받혀서 "1/50"이 나왔다(사용자가 실제로 겪음).
        # 권장 프리셋('이 사이트 조금' = 50페이지·2단계)과 기본값을 맞춘다.
        self.follow_depth_var = tk.StringVar(value='2')
        self.wait_until_var = tk.StringVar(value='networkidle')
        # 요청 사이 텀 - HTTrack 쪽 안전장치에는 있는데 스마트 크롤링에는 없던 것.
        # 기본은 꺼둔다(끄면 예전과 동일하게 동작 - 기존 사용자 흐름을 안 건드림).
        self.smart_pause_enable_var = tk.BooleanVar(value=False)
        self.smart_pause_min_var = tk.StringVar(value='1')
        self.smart_pause_max_var = tk.StringVar(value='3')

        # 완료 후 동작
        self.power_action_var = tk.StringVar(value='none')
        self.power_hours_var = tk.StringVar(value='2')
        self.power_caption_var = tk.StringVar(value=t('power_caption_none'))

        self._refresh_filter_preview()

    def _open_schedule_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title(t('panel_schedule_list'))
        dialog.configure(bg=BG)
        dialog.geometry('820x640')
        dialog.minsize(640, 420)
        dialog.transient(self.root)
        outer = make_scrollable(dialog)
        outer.configure(padding=20)
        self._build_schedule_tab(outer)

    # 데이터 추출 도구 - (키, 아이콘, 제목 문자열키, 설명 문자열키).
    # 메인 화면의 '데이터로 뽑기'와 데이터 도구 창이 같은 목록을 쓰도록 한곳에 둔다.
    DATA_CARD_WIDTH = 520

    _DATA_TOOLS = (
        ('ai_extract', '🤖', 'btn_ai_extract', 'desc_ai_extract'),
        ('pagination', '📑', 'btn_pagination_extract', 'desc_pagination_extract'),
        ('click_select', '🖱', 'btn_click_select', 'desc_click_select'),
        ('clean_organize', '🧹', 'btn_clean_organize', 'desc_clean_organize'),
    )

    # 좌측 내비게이션 - (intent 값, 아이콘, 제목 문자열키, 설명 문자열키)
    _NAV_ITEMS = (
        ('save', '📥', 'nav_download', 'nav_download_desc'),
        ('data', '🔍', 'nav_crawl', 'nav_crawl_desc'),
    )

    NAV_WIDTH_OPEN = 260
    NAV_WIDTH_CLOSED = 76

    def _build_nav(self, parent):
        """좌측 내비게이션. 이 앱의 두 갈래(사이트 다운로드 / 크롤링)를 늘
        보이게 두되, 화면이 좁을 때를 위해 아이콘만 남기고 접을 수 있다.
        접힘 상태는 설정에 저장해서 다음 실행에도 유지한다."""
        self._nav_frame = parent
        self._nav_collapsed = bool(self.settings.get('nav_collapsed', False))

        toggle = tk.Frame(parent, bg=PANEL, cursor='hand2')
        toggle.pack(fill='x', pady=(10, 0))
        self._nav_toggle_lbl = tk.Label(toggle, text='«', bg=PANEL, fg=FG_MUTED,
                                        font=(FONTS['ui'], TYPE_BODY_LARGE, 'bold'))
        self._nav_toggle_lbl.pack(anchor='e', padx=14)
        for w in (toggle, self._nav_toggle_lbl):
            w.bind('<Button-1>', lambda _e: self._toggle_nav())

        self._nav_buttons = {}
        for key, icon, title_key, desc_key in self._NAV_ITEMS:
            item = tk.Frame(parent, bg=PANEL, cursor='hand2')
            item.pack(fill='x', pady=(16, 0), padx=12)
            head = tk.Frame(item, bg=PANEL)
            head.pack(fill='x')
            icon_lbl = tk.Label(head, text=icon, bg=PANEL, fg=FG,
                                font=(FONTS['ui'], TYPE_BODY_LARGE))
            icon_lbl.pack(side='left', padx=(12, 10), pady=(12, 0))
            title_lbl = tk.Label(head, text=t(title_key), bg=PANEL, fg=FG,
                                 font=(FONTS['ui'], TYPE_BODY, 'bold'))
            title_lbl.pack(side='left', pady=(12, 0))
            desc_lbl = tk.Label(item, text=t(desc_key), bg=PANEL, fg=FG_MUTED,
                                font=(FONTS['ui'], TYPE_CAPTION), wraplength=self.NAV_WIDTH_OPEN - 48,
                                justify='left', anchor='w')
            desc_lbl.pack(fill='x', padx=(12, 12), pady=(4, 12))
            self._nav_buttons[key] = (item, head, icon_lbl, title_lbl, desc_lbl)
            for w in (item, head, icon_lbl, title_lbl, desc_lbl):
                w.bind('<Button-1>', lambda _e, k=key: self._on_nav_clicked(k))
        self._apply_nav_collapsed()
        self._sync_nav_selection()

    def _toggle_nav(self):
        self._nav_collapsed = not self._nav_collapsed
        self.settings['nav_collapsed'] = self._nav_collapsed
        save_settings(self.settings)
        self._apply_nav_collapsed()

    def _apply_nav_collapsed(self):
        """접힘 상태에 맞춰 폭을 바꾸고 글자를 숨기거나 되살린다.
        아이콘은 접혀도 남겨서 어디를 누르는지 알 수 있게 한다."""
        collapsed = self._nav_collapsed
        self._nav_frame.configure(width=self.NAV_WIDTH_CLOSED if collapsed else self.NAV_WIDTH_OPEN)
        self._nav_toggle_lbl.configure(text='»' if collapsed else '«')
        for _key, (_item, _head, _icon, title_lbl, desc_lbl) in self._nav_buttons.items():
            if collapsed:
                title_lbl.pack_forget()
                desc_lbl.pack_forget()
            else:
                title_lbl.pack(side='left', pady=(8, 0))
                desc_lbl.pack(fill='x', padx=(8, 8), pady=(2, 8))

    def _on_nav_clicked(self, key):
        if getattr(self, '_busy', False):
            return
        self.intent_var.set(key)
        self._on_intent_changed()

    def _sync_nav_selection(self):
        """지금 고른 항목만 눈에 띄게 표시한다(배경색 + 글자색)."""
        if not hasattr(self, '_nav_buttons'):
            return
        current = self.intent_var.get()
        for key, widgets in self._nav_buttons.items():
            selected = (key == current)
            bg = ACCENT_SOFT if selected else PANEL
            for w in widgets:
                w.configure(bg=bg)
            widgets[3].configure(fg=ACCENT if selected else FG)

    def _build_hero(self, parent):
        """원형 시작 버튼을 가운데 두고 좌우로 실시간 지표 카드를 배치한다."""
        hero = tk.Frame(parent, bg=BG)
        hero.grid(row=1, column=1, sticky='ew', padx=26, pady=(10, 4))
        # 지표 카드 열은 내용 폭만 차지하게 두고(weight=0), 남는 폭은 전부 가운데가
        # 가져간다 - 그래야 카드가 쓸데없이 길어지지 않고 버튼 주변에 여백이 생긴다.
        hero.grid_columnconfigure(0, weight=0, uniform='hero')
        hero.grid_columnconfigure(1, weight=1)
        hero.grid_columnconfigure(2, weight=0, uniform='hero')

        left_stats = tk.Frame(hero, bg=BG)
        self._left_stats = left_stats
        left_stats.grid(row=0, column=0, sticky='n')
        center = tk.Frame(hero, bg=BG)
        center.grid(row=0, column=1, padx=48)
        right_stats = tk.Frame(hero, bg=BG)
        self._right_stats = right_stats
        right_stats.grid(row=0, column=2, sticky='n')

        self.elapsed_stat = self._stat_card(left_stats, '⏱', t('stat_elapsed'))
        self.links_stat, self._links_caption = self._stat_card(left_stats, '🔗', t('stat_links'),
                                                               with_caption=True)
        self.files_stat = self._stat_card(left_stats, '📄', t('stat_files'))
        self.bytes_stat = self._stat_card(right_stats, '💾', t('stat_bytes'))
        self.speed_stat = self._stat_card(right_stats, '⚡', t('stat_speed'))
        self.errors_stat = self._stat_card(right_stats, '⚠', t('stat_errors'))

        # 목적(다운로드/크롤링)은 좌측 내비게이션이 정하고, 여기는 고른 쪽의
        # 내용만 보여준다. 화면 안에 토글을 겹겹이 두면 오히려 헷갈린다는
        # 피드백을 반영해 세그먼트 컨트롤을 걷어냈다.
        self._intent_caption_var = tk.StringVar(value=t('caption_intent_save'))
        tk.Label(center, textvariable=self._intent_caption_var, bg=BG, fg=FG_MUTED,
                 font=(FONTS['ui'], TYPE_CAPTION), wraplength=420, justify='center').pack(pady=(0, 10))

        # --- (A) 사이트 다운로드 ---
        self._save_zone = tk.Frame(center, bg=BG)
        self._save_zone.pack()

        # '미러링 vs 스마트'는 이제 이 화면의 큰 분기가 아니라 '받는 방식'이라는
        # 다운로드 옵션이다(설정 요약 행에서 고른다). 여기서는 지금 고른 방식이
        # 무엇인지 한 줄로만 알려준다.
        self.mode_var = tk.StringVar(value='mirror')
        self._mode_caption_var = tk.StringVar(value=t('caption_mode_mirror'))
        tk.Label(self._save_zone, textvariable=self._mode_caption_var, bg=BG, fg=FG_MUTED,
                 font=(FONTS['ui'], TYPE_CAPTION), wraplength=380, justify='center').pack(pady=(0, 10))

        self.start_button = CircularStartButton(self._save_zone, command=self._on_power_clicked, size=180)
        self.start_button.pack()
        self.job_var = tk.StringVar()
        # height=1로 한 줄을 미리 잡아둔다. 상태 문구가 나타났다 사라질 때
        # 아래 내용이 위아래로 밀리지 않게 하기 위함.
        self._status_label = tk.Label(self._save_zone, textvariable=self.job_var, bg=BG, fg=FG_MUTED,
                                      height=1, font=(FONTS['ui'], TYPE_BODY, 'bold'))
        self._status_label.pack(pady=(12, 0))
        # 기존 진행률 로직과의 호환용 - 실제 표시는 원형 버튼의 링이 담당한다.
        self.progress_var = tk.DoubleVar(value=0)

        # --- (B) 데이터로 뽑기 - 목적을 이걸로 고르면 도구가 바로 보인다 ---
        # 폭을 고정해야 카드 4장의 오른쪽 끝이 맞는다. 예전엔 카드마다 내용에
        # 맞춰 폭이 달라져서 버튼이 카드 배경 밖으로 삐져나왔다.
        self._data_zone = tk.Frame(center, bg=BG)
        # 높이는 내용에 맞게 늘어나야 하므로 pack_propagate를 끄면 안 된다
        # (끄면 높이가 1px로 얼어붙어 카드가 통째로 안 보인다 - 실제로 겪음).
        # 대신 높이 0짜리 막대로 최소 폭만 잡아준다.
        tk.Frame(self._data_zone, bg=BG, width=self.DATA_CARD_WIDTH, height=0).pack()
        for key, icon, title_key, desc_key in self._DATA_TOOLS:
            # 버튼을 따로 두지 않고 카드 전체를 누르게 한다 - 행마다 주황 버튼이
            # 있으면 넷 다 강조되어 오히려 아무것도 강조되지 않는다.
            row = RoundedCard(self._data_zone, radius=14, padding=16)
            row.pack(fill='x', pady=5)
            inner = ttk.Frame(row.body, style='Panel.TFrame')
            inner.pack(fill='x')
            icon_lbl = tk.Label(inner, text=icon, bg=PANEL, fg=ACCENT,
                                font=(FONTS['ui'], TYPE_TITLE))
            icon_lbl.pack(side='left', padx=(0, 14))
            chev = tk.Label(inner, text='›', bg=PANEL, fg=FG_MUTED,
                            font=(FONTS['ui'], TYPE_TITLE))
            chev.pack(side='right', padx=(8, 0))
            col = ttk.Frame(inner, style='Panel.TFrame')
            col.pack(side='left', fill='x', expand=True)
            title_lbl = ttk.Label(col, text=t(title_key), style='RowTitle.TLabel')
            title_lbl.pack(anchor='w')
            desc_lbl = ttk.Label(col, text=t(desc_key), style='Caption.TLabel',
                                 wraplength=self.DATA_CARD_WIDTH - 120, justify='left')
            desc_lbl.pack(anchor='w', pady=(2, 0))
            for w in (row, row.canvas, inner, col, icon_lbl, chev, title_lbl, desc_lbl):
                w.bind('<Button-1>', lambda _e, k=key: self._on_data_tool_picked(k))
                try:
                    w.configure(cursor='hand2')
                except tk.TclError:
                    pass

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
                 font=(FONTS['ui'], TYPE_CAPTION)).pack(side='left', padx=(0, 9))
        col = ttk.Frame(row, style='Stat.TFrame')
        col.pack(side='left', fill='x', expand=True)
        caption_lbl = tk.Label(col, text=caption, bg=STAT_BG, fg=FG_MUTED,
                               font=(FONTS['ui'], TYPE_CAPTION), width=11, anchor='w')
        caption_lbl.pack(anchor='w', fill='x')
        # width를 글자 수로 고정해 둔다. 값이 '-' ↔ '386/411'처럼 바뀔 때마다 라벨의
        # 요청 크기가 달라지면 카드가 매번 다시 레이아웃되면서 눈에 띄게 들썩인다.
        value = tk.Label(col, text='-', bg=STAT_BG, fg=FG, font=(FONTS['ui'], TYPE_INPUT, 'bold'),
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
        self._project_title_var = tk.StringVar(value=t('panel_project'))
        ttk.Label(head, textvariable=self._project_title_var, style='Header.TLabel').pack(side='left')
        prefs_btn = RoundedButton(head, f"⚙  {t('nav_preferences')}", command=self._open_preferences,
                                  variant='ghost', page_bg=PANEL, padx=14, pady=7)
        prefs_btn.pack(side='right')
        self._lockable.append(prefs_btn)

        # 라벨과 입력칸을 한 상자로 묶어둔다. 크롤링 화면에서 숨겼다가 되살릴 때
        # 낱개로 다루면 'before' 기준이 사라져 복원이 실패한다(실제로 겪음).
        self._url_box = ttk.Frame(body, style='Panel.TFrame')
        self._url_box.pack(fill='x')
        ttk.Label(self._url_box, text=t('label_urls'), style='Muted.TLabel').pack(anchor='w')
        url_row = ttk.Frame(self._url_box, style='Panel.TFrame')
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
        self._fields_frame = fields
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
        # 예약(스케줄러)은 스마트 크롤링 모드에만 둔다 - 이름이 '스마트 스케줄러'인데
        # 사이트 미러링 탭에도 보이면 어느 쪽 기능인지 헷갈린다.
        'mirror': (('method', '⚡', 'panel_method'),
                   ('scope', '🎯', 'panel_scope'), ('files', '📦', 'panel_files'),
                   ('safety', '🛡', 'panel_safety'), ('power', '⏻', 'panel_power')),
        'smart': (('method', '⚡', 'panel_method'),
                  ('smart', '🧠', 'panel_smart_options'), ('power', '⏻', 'panel_power'),
                  ('schedule', '🗓', 'panel_schedule_list')),
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
        # 크롤링 화면에서는 수집 방식 자체가 안 보여야 하므로 여기서 되살리지 않는다.
        if smart or self.intent_var.get() == 'data':
            self._action_col.grid_remove()
        else:
            self._action_col.grid()
        self._mode_caption_var.set(t('caption_mode_smart') if smart else t('caption_mode_mirror'))
        self._rebuild_options_area()
        self._sync_stat_captions()

    def _on_intent_changed(self, _value=None):
        """목적(파일로 저장 / 데이터로 뽑기)에 따라 가운데 영역과 옵션 행을 바꾼다.
        크롤링 설정(수집 범위·안전장치 등)은 '저장'일 때만 의미가 있어서,
        '데이터로 뽑기'를 고르면 그 행들은 감춘다 - 고른 목적에 맞는 것만 보이게."""
        if getattr(self, '_busy', False):
            # 작업 중에는 화면이 바뀌면 혼란스러우므로 되돌린다.
            self.intent_var.set('save')
            return
        data_mode = self.intent_var.get() == 'data'
        self._intent_caption_var.set(t('caption_intent_data') if data_mode else t('caption_intent_save'))
        if data_mode:
            self._save_zone.pack_forget()
            self._data_zone.pack(fill='x')
            self._options_area.pack_forget()
            # 크롤링에서는 '받을 주소'와 '수집 방식'이 쓰이지 않는다 - 주소는 각
            # 도구가 자기 창에서 따로 받고, 수집 방식은 HTTrack 전용 값이다.
            # 남는 건 '어느 폴더의 데이터를 다룰지'(이름 + 저장 위치)뿐이다.
            self._url_box.pack_forget()
            self._action_col.grid_remove()
            # 지표 카드는 '얼마나 받았는지'를 보여주는 다운로드용 값이라
            # 데이터 추출 화면에서는 늘 '-'로 남아 자리만 차지한다.
            self._left_stats.grid_remove()
            self._right_stats.grid_remove()
            self._project_title_var.set(t('panel_project_data'))
        else:
            self._data_zone.pack_forget()
            self._save_zone.pack()
            self._options_area.pack(fill='x')
            self._url_box.pack(fill='x', before=self._fields_frame)
            if self.mode_var.get() != 'smart':
                self._action_col.grid()
            self._left_stats.grid()
            self._right_stats.grid()
            self._project_title_var.set(t('panel_project'))
        self._sync_nav_selection()
        self._sync_start_button()

    def _option_row(self, parent, group, icon, title, value_var):
        # inset을 작게 줘서 행 높이를 촘촘하게 유지한다(네 행이 스크롤 없이 다 들어가야 함).
        card = RoundedCard(parent, page_bg=PANEL, card_bg=PANEL_LIGHT, radius=11, inset=4,
                           padding=(11, 6), body_style='PanelLight.TFrame')
        inner = card.body
        tk.Label(inner, text=icon, bg=PANEL_LIGHT, fg=FG_MUTED,
                 font=(FONTS['ui'], TYPE_CAPTION)).pack(side='left', padx=(0, 9))
        tk.Label(inner, text='›', bg=PANEL_LIGHT, fg=FG_MUTED,
                 font=(FONTS['ui'], TYPE_BODY_LARGE, 'bold')).pack(side='right', padx=(6, 2))
        col = ttk.Frame(inner, style='PanelLight.TFrame')
        col.pack(side='left', fill='x', expand=True)
        tk.Label(col, text=title, bg=PANEL_LIGHT, fg=FG_MUTED,
                 font=(FONTS['ui'], TYPE_CAPTION)).pack(anchor='w')
        # 값이 길어도 잘리지 않게 한 줄로 유지하되, 폭이 모자라면 말줄임 대신 그대로 두고
        # 카드가 늘어나도록 한다(잘림 방지가 우선).
        tk.Label(col, textvariable=value_var, bg=PANEL_LIGHT, fg=FG, anchor='w',
                 font=(FONTS['ui'], TYPE_BODY, 'bold')).pack(anchor='w', fill='x')

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

        # AI 추출/페이지네이션 추출/클릭해서 고르기/정리된 사본 만들기 - 4개를 각각
        # 작은 아이콘 버튼으로 늘어놓으면 뭐가 뭔지, 언제 쓰는 건지 알기 어렵다.
        # 하나의 진입점으로 모으고, 다이얼로그 안에서 각각 설명과 함께 고르게 한다.

        # height는 '요청 크기'일 뿐이고 실제로는 남는 공간을 채운다. 기본값(24줄)을 두면
        # 창의 최소 높이가 불필요하게 커지므로 작게 잡아둔다.
        self.log_text = scrolledtext.ScrolledText(
            body, bg='#16151A', fg='#8FE3A6', insertbackground='#8FE3A6',
            font=(FONTS['mono'], 10), relief='flat', state='disabled', wrap='word',
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
        if group == 'schedule':
            # 예약 작업은 지금 폼의 값이 아니라 별도로 등록해둔 작업 목록이라,
            # OptionsDialog가 아니라 그 목록을 보여주는 창을 연다.
            self._open_schedule_dialog()
            return
        OptionsDialog(self.root, self, group)

    def _save_use_local_cookies(self):
        self.settings['use_local_cookies'] = bool(self.use_local_cookies_var.get())
        save_settings(self.settings)

    def _refresh_option_summaries(self):
        """메인 화면의 요약 행에 지금 설정된 값을 사람이 읽는 문장으로 채운다."""
        if not hasattr(self, '_summary_vars'):
            return
        if 'method' in self._summary_vars:
            self._summary_vars['method'].set(
                t('method_browser_title') if self.mode_var.get() == 'smart' else t('method_fast_title'))
        if 'smart' in self._summary_vars:
            text = t('summary_smart_value', pages=self.max_pages_var.get(), depth=self.follow_depth_var.get())
            pause = self._effective_smart_pause()
            if pause:
                text += f' · {pause[0]}~{pause[1]}s'
            self._summary_vars['smart'].set(text)
        if 'scope' not in self._summary_vars:
            # 스마트 모드에서는 미러링 전용 요약 행이 없으므로 여기서 끝낸다.
            self._set_power_summary()
            self._set_schedule_summary()
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
        self._set_schedule_summary()

    def _set_power_summary(self):
        mode = self.power_action_var.get()
        if mode == 'after_hours':
            power_text = t('power_text_after_hours', hours=self.power_hours_var.get())
        elif mode == 'on_complete':
            power_text = t('power_text_on_complete')
        else:
            power_text = t('power_text_none')
        self._summary_vars['power'].set(power_text)

    def _set_schedule_summary(self):
        if 'schedule' not in self._summary_vars:
            return
        n = len(self.jobs)
        self._summary_vars['schedule'].set(t('summary_schedule_value', n=n) if n else t('summary_schedule_none'))

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
        return [normalize_url(u) for u in raw.split() if u.strip()]

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
        # 예약 작업 다이얼로그는 열 때마다 새로 만들고 닫으면 그대로 없어지므로,
        # 닫혀 있는 동안(=창 밖에서 작업이 저장/삭제됐을 때) 옛 프레임을 건드리지
        # 않도록 존재 여부를 확인한다.
        if not hasattr(self, 'jobs_list_frame') or not self.jobs_list_frame.winfo_exists():
            return
        for child in self.jobs_list_frame.winfo_children():
            child.destroy()

        if not self.jobs:
            tk.Label(self.jobs_list_frame, text=t('label_no_jobs'),
                      bg=PANEL, fg=FG_MUTED, font=(FONTS['ui'], TYPE_CAPTION)).pack(anchor='w')
            return

        status_labels = {
            'never_run': t('job_status_never_run'), 'running': t('job_status_running'),
            'success': t('job_status_success'), 'errors': t('job_status_errors'),
            'error': t('job_status_error'),
        }
        mode_labels = {'httrack': t('job_mode_httrack'), 'smart': t('job_mode_smart'), 'both': t('job_mode_both')}
        schedule_labels = {'once': t('schedule_type_once'), 'hourly': t('schedule_type_hourly'),
                            'daily': t('schedule_type_daily'), 'weekly': t('schedule_type_weekly')}
        for job in self.jobs:
            row = tk.Frame(self.jobs_list_frame, bg=BG, highlightbackground=BORDER, highlightthickness=1)
            row.pack(fill='x', pady=3)
            info = tk.Frame(row, bg=BG)
            info.pack(side='left', fill='x', expand=True, padx=10, pady=6)
            tk.Label(info, text=job['name'], bg=BG, fg=FG, font=(FONTS['ui'], TYPE_BODY_LARGE, 'bold')).pack(anchor='w')
            schedule = job.get('schedule', {})
            schedule_text = f"{schedule_labels.get(schedule.get('type'), '')} {schedule.get('at', '')}"
            status_text = status_labels.get(job.get('last_status', 'never_run'), job.get('last_status', ''))
            subtitle = f"{mode_labels.get(job.get('mode'), '')} · {schedule_text} · {status_text}"
            tk.Label(info, text=subtitle, bg=BG, fg=FG_MUTED, font=(FONTS['ui'], TYPE_CAPTION)).pack(anchor='w')

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
        self._set_schedule_summary()
        self._log(t('log_job_saved'))

    def _delete_job(self, job):
        scheduler_win.unregister_task(job.get('scheduler_task_name'))
        self.jobs = jobs_mod.remove_job(self.jobs, job['id'])
        jobs_mod.save_jobs(CONFIG_DIR, self.jobs)
        self._refresh_jobs_panel()
        self._set_schedule_summary()
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

    def _effective_smart_pause(self):
        """스마트 크롤링/페이지네이션 추출에 넘길 (최소초, 최대초) 또는 None(꺼짐)."""
        if not self.smart_pause_enable_var.get():
            return None
        try:
            p_min = max(0, int(self.smart_pause_min_var.get()))
            p_max = max(p_min, int(self.smart_pause_max_var.get()))
            return (p_min, p_max)
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
                      bg=PANEL, fg=FG_MUTED, font=(FONTS['ui'], TYPE_CAPTION)).pack(anchor='w')
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
            tk.Label(info, text=record['name'], bg=BG, fg=FG, font=(FONTS['ui'], TYPE_BODY_LARGE, 'bold')).pack(anchor='w')
            status_text = status_labels.get(record.get('last_status', 'never'), record.get('last_status', ''))
            subtitle = f"{t('proj_url_count', n=len(record.get('urls', [])))} · {status_text} · {record.get('base_path', '')}"
            tk.Label(info, text=subtitle, bg=BG, fg=FG_MUTED, font=(FONTS['ui'], TYPE_CAPTION)).pack(anchor='w')

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

    def _open_scope_rules_dialog(self, parent=None):
        """'추가 규칙' 칸을 자연어로 채워주는 AI 도우미를 연다.
        parent를 옵션 창으로 주면 그 창 위에 뜬다(옵션 창이 grab_set으로
        입력을 잡고 있어서, 루트를 부모로 주면 새 창을 조작할 수 없다)."""
        urls = self._get_urls()
        if not urls:
            self._log(t('warn_scope_need_url'))
            return
        AIScopeRulesDialog(parent or self.root, urls, self.settings, log_fn=self._log,
                            on_apply=self._apply_scope_rules)

    def _apply_scope_rules(self, rules_text):
        self.custom_filters_var.set(rules_text)
        self._refresh_option_summaries()
        self._log(t('log_scope_rules_applied'))

    def _open_data_tools_dialog(self):
        out_dir = os.path.join(self.base_path_var.get().strip(), self.project_var.get().strip())
        has_project = os.path.isdir(out_dir)
        DataToolsDialog(self.root, has_project, on_pick=self._on_data_tool_picked)

    def _on_data_tool_picked(self, key):
        if key == 'ai_extract':
            self._open_ai_extract_dialog()
        elif key == 'pagination':
            self._open_pagination_dialog()
        elif key == 'click_select':
            self._open_click_select_dialog()
        elif key == 'clean_organize':
            self._open_clean_organize()

    def _open_ai_extract_dialog(self, record=None):
        # 버튼 하나로 '방금 끝난 작업의 결과 폴더'를 대상으로 삼는다 -
        # '결과 폴더 열기'와 똑같은 방식으로 경로를 구한다.
        if record is not None:
            out_dir = os.path.join(record['base_path'], record['name'])
        else:
            out_dir = os.path.join(self.base_path_var.get().strip(), self.project_var.get().strip())
        if not os.path.isdir(out_dir):
            self._log(t('warn_folder_not_found'))
            return
        AIExtractRunDialog(self.root, out_dir, self.settings, log_fn=self._log,
                            on_run=lambda config: self._start_ai_extract_thread(out_dir, config))

    def _start_ai_extract_thread(self, out_dir, config):
        if not config.get('enabled') or not config.get('fields'):
            self._log(t('warn_need_fields'))
            return
        ai_config = get_active_ai_config(self.settings)
        if not ai_ready(ai_config):
            self._log(t('warn_need_api_key'))
            return
        self._log(t('log_ai_extract_started'))

        def worker():
            records, saved_paths = ai_extract.run_extraction(
                out_dir, config['fields'], ai_config['api_key'], provider=ai_config['provider'],
                log_fn=lambda msg: self.msg_queue.put(('log', msg)),
                max_pages=200, export_formats=config['export_formats'])
            # 뽑아낸 표를 자연어로 다듬는 다음 단계를 곧바로 이어서 제안한다
            # (버튼을 새로 찾아 누를 필요 없이, 방금 나온 결과 위에서 바로).
            if records:
                self.msg_queue.put(('ai_extract_done', records, out_dir))

        threading.Thread(target=worker, daemon=True).start()

    def _on_ai_extract_done(self, records, out_dir):
        self._log(t('log_ai_extract_offer_refine', n=len(records)))
        AIRefineDialog(self.root, records, out_dir, self.settings, log_fn=self._log)

    def _open_clean_organize(self):
        # 버튼 하나로 '방금 끝난 작업의 결과 폴더'를 대상으로 삼는다 - AI 추출과
        # 똑같은 방식으로 경로를 구한다. 원본은 절대 건드리지 않고 정리된 사본을
        # 새 폴더에 만드는 것뿐이라 확인 창 없이 바로 실행한다.
        out_dir = os.path.join(self.base_path_var.get().strip(), self.project_var.get().strip())
        if not os.path.isdir(out_dir):
            self._log(t('warn_folder_not_found'))
            return
        self._log(t('log_clean_organize_started'))

        def worker():
            try:
                result_dir = clean_organize.organize_folder(
                    out_dir, log_fn=lambda msg: self.msg_queue.put(('log', msg)))
                self.msg_queue.put(('clean_organize_done', result_dir))
            except Exception as e:
                self.msg_queue.put(('log', t('warn_clean_organize_failed', e=e)))
                self.msg_queue.put(('clean_organize_done', None))

        threading.Thread(target=worker, daemon=True).start()

    def _on_clean_organize_done(self, result_dir):
        if result_dir:
            self._log(t('log_clean_organize_done', path=result_dir))

    def _open_pagination_dialog(self):
        PaginationExtractDialog(self.root, self.settings, log_fn=self._log,
                                 on_run=self._start_pagination_thread)

    def _start_pagination_thread(self, url, config, max_pages, use_cookies):
        ai_config = get_active_ai_config(self.settings)
        if not ai_ready(ai_config):
            self._log(t('warn_need_api_key'))
            return
        self._log(t('log_pagination_started'))
        out_dir = os.path.join(CONFIG_DIR, 'pagination_extracts', datetime.now().strftime('%Y%m%d_%H%M%S'))

        def worker():
            try:
                rows = pagination_extract.extract_paginated_list(
                    url, config['fields'], ai_config['api_key'],
                    log_fn=lambda msg: self.msg_queue.put(('log', msg)),
                    provider=ai_config['provider'], max_pages=max_pages,
                    use_local_cookies=use_cookies, pause=(1, 2))
            except Exception as e:
                self.msg_queue.put(('log', f'[페이지네이션] {e}'))
                return
            if not rows:
                self.msg_queue.put(('log', t('log_pagination_no_rows')))
                return
            os.makedirs(out_dir, exist_ok=True)
            saved_paths = ai_extract.export_records(rows, out_dir, 'pagination_extract', config['export_formats'])
            self.msg_queue.put(('log', f'[페이지네이션] {len(rows)}개 행 저장: '
                                        f'{", ".join(saved_paths) if saved_paths else "없음"}'))
            self.msg_queue.put(('ai_extract_done', rows, out_dir))

        threading.Thread(target=worker, daemon=True).start()

    def _open_click_select_dialog(self):
        ClickToSelectDialog(self.root, self.settings, log_fn=self._log,
                             on_extract=self._start_click_select_thread)

    def _start_click_select_thread(self, items_html, config):
        ai_config = get_active_ai_config(self.settings)
        if not ai_ready(ai_config):
            self._log(t('warn_need_api_key'))
            return
        self._log(t('log_click_select_started'))
        out_dir = os.path.join(CONFIG_DIR, 'click_select_extracts', datetime.now().strftime('%Y%m%d_%H%M%S'))

        def worker():
            try:
                rows = ai_extract.extract_list_fields(
                    items_html, config['fields'], ai_config['api_key'], provider=ai_config['provider'])
            except Exception as e:
                self.msg_queue.put(('log', f'[클릭해서 고르기] {e}'))
                return
            if not rows:
                self.msg_queue.put(('log', t('log_click_select_no_rows')))
                return
            os.makedirs(out_dir, exist_ok=True)
            saved_paths = ai_extract.export_records(rows, out_dir, 'click_select_extract', config['export_formats'])
            self.msg_queue.put(('log', f'[클릭해서 고르기] {len(rows)}개 행 저장: '
                                        f'{", ".join(saved_paths) if saved_paths else "없음"}'))
            self.msg_queue.put(('ai_extract_done', rows, out_dir))

        threading.Thread(target=worker, daemon=True).start()

    # ---------------- 동작 ----------------
    def _open_preferences(self):
        if getattr(self, '_busy', False):
            return
        # 스마트 크롤링 모드일 때는 HTTrack 전용 설정(연결/속도/정책/네트워크/고급)을
        # 아예 안 보여준다 - Playwright는 그 값들을 하나도 읽지 않아서 보여줘 봐야
        # 헷갈리기만 한다.
        PreferencesDialog(self.root, self.settings, on_save=self._on_prefs_saved, mode=self.mode_var.get())

    def _on_prefs_saved(self):
        # 환경설정에서 바꾼 쿠키 설정이 스마트 옵션 창의 토글에도 반영되게 맞춰준다.
        self.use_local_cookies_var.set(bool(self.settings.get('use_local_cookies', False)))

        # 언어를 바꿨으면 실제로 화면 글자까지 바꿔준다. 예전에는 설정 파일에만
        # 저장되고 set_language()를 다시 부르지 않아서, 언어를 바꿔도 아무 일도
        # 일어나지 않았다(재시작 안내조차 없었다).
        new_lang = self.settings.get('language', 'en')
        if new_lang != getattr(self, '_current_lang', None):
            set_language(new_lang)
            self._current_lang = new_lang
            self._rebuild_ui_for_language()

        self._log(t('log_prefs_saved'))

    def _rebuild_ui_for_language(self):
        """화면을 통째로 다시 그린다. 위젯의 글자는 만들 때 t()로 한 번 박히기
        때문에, 언어가 바뀌면 다시 만드는 것 말고는 반영할 방법이 없다.
        사용자가 입력해둔 값(주소·이름·저장위치)과 지금 보고 있던 화면은
        그대로 유지한다 - 언어만 바꿨는데 하던 일이 날아가면 안 되므로."""
        if getattr(self, '_busy', False):
            # 작업 중에 화면을 뜯어내면 진행 상황 위젯이 사라져 위험하다.
            self._log(t('log_prefs_saved'))
            return
        keep = {
            'urls': self.urls_var.get(),
            'project': self.project_var.get(),
            'base_path': self.base_path_var.get(),
            'mode': self.mode_var.get(),
            'intent': self.intent_var.get(),
        }
        log_text = self.log_text.get('1.0', 'end')

        self._root_frame.destroy()
        self._build_ui()

        self.urls_var.set(keep['urls'])
        self.project_var.set(keep['project'])
        self.base_path_var.set(keep['base_path'])
        self.mode_var.set(keep['mode'])
        self._on_mode_changed()
        self.intent_var.set(keep['intent'])
        self._on_intent_changed()
        if log_text.strip():
            self.log_text.configure(state='normal')
            self.log_text.insert('end', log_text.strip() + '\n')
            self.log_text.configure(state='disabled')
            self.log_text.see('end')

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
                      'max_pages': int(self.max_pages_var.get() or 50),
                      'pause': self._effective_smart_pause()},
            'httrack': {'depth': self.follow_depth_var.get()},
            'scope': {'domain_scope': next(
                (code for code, label in self.domain_scope_options
                 if label == self.domain_scope_var.get()), 'host'),
                      'same_folder': bool(self.same_folder_var.get())},
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
            self._log(t('log_data_tools_hint'))
        self._finish_project_record('success' if ok else 'errors')
        if self.power_action_var.get() == 'on_complete' and not self._user_stopped:
            self._schedule_shutdown(60, t('reason_on_complete'))

    def _launch_mirroring(self, p_name, b_path, urls):
        out_dir = os.path.join(b_path, p_name)
        os.makedirs(out_dir, exist_ok=True)

        # HTTrack은 우리가 통제할 수 없는 블랙박스 서브프로세스라 실행 도중
        # 디스크 여유 공간을 계속 확인해줄 수 없다 - 시작 전에만 확인한다.
        free_mb, disk_status = storage.check_disk_space(out_dir)
        if disk_status == 'critical':
            self._log(t('warn_disk_critical', free=int(free_mb)))
            return
        elif disk_status == 'warn':
            self._log(t('warn_disk_low', free=int(free_mb)))

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
                elif kind == 'ai_extract_done':
                    self._on_ai_extract_done(msg[1], msg[2])
                elif kind == 'clean_organize_done':
                    self._on_clean_organize_done(msg[1])
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
            self._log(t('log_data_tools_hint'))
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
            free_mb, disk_status = storage.check_disk_space(job['save_path'])
            if disk_status == 'critical':
                log(t('warn_disk_critical', free=int(free_mb)))
                status = 'errors'
            else:
                if disk_status == 'warn':
                    log(t('warn_disk_low', free=int(free_mb)))

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
            if ai_ready(ai_config):
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
