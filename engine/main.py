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
import data_refine
import preview


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
    get_active_ai_config, PROJECTS_FILE, load_projects, save_projects,
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
from widgets import (  # noqa: F401
    make_scrollable, combo_width, display_width, _rounded_rect_points, lerp_color,
    draw_vertical_gradient, draw_soft_shadow,
    BrandHeader, SegmentedControl, CircularStartButton,
    RoundedCard, RoundedButton, ToggleSwitch,
)


class PreferencesDialog(tk.Toplevel):
    """ExpressVPN류 앱의 "아이콘 + 굵은 제목 + 회색 설명 + 우측 컨트롤(토글/드롭다운/입력)"
    행 패턴 + 행 사이 구분선으로 구성. pack 기반이라 grid 행 번호를 손으로 맞추다
    생기는 겹침 버그를 원천적으로 피한다."""

    def __init__(self, parent, settings, on_save, mode='mirror'):
        # mode='smart'면 HTTrack 전용 설정(연결/속도/정책/네트워크/고급)은 아예
        # 안 만든다 - Playwright 기반 스마트 크롤링은 그 값들을 하나도 읽지 않으므로
        # 보여줘 봐야 "바꿔도 아무 효과 없는 설정"이 될 뿐이다.
        self.mode = mode
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

        # 설정을 두 층으로 나눈다. 19개를 한 줄로 늘어놓으면 초보자는 무엇을
        # 건드려야 할지 알 수 없다. 실제로 자주 쓰는 건 언어/로그인/AI 셋뿐이라
        # 그것만 위에 펼쳐 두고 나머지는 '전문가 설정'으로 접어 둔다.
        basic_zone = ttk.Frame(outer)
        basic_zone.pack(fill='x')

        self._expert_zone = ttk.Frame(outer)
        self._expert_open = False
        if self.mode != 'smart':
            self._expert_btn = RoundedButton(outer, f"▸  {t('expert_show')}",
                                             command=self._toggle_expert, variant='ghost')
            self._expert_btn.pack(anchor='w', pady=(4, 10))
        else:
            # 스마트 크롤링은 이 설정들을 하나도 읽지 않는다(Playwright는 연결 수/
            # robots 정책/프록시 같은 HTTrack 전용 값과 무관하다). 그래서 버튼조차
            # 안 만들고, 왜 없는지만 짧게 알려준다.
            ttk.Label(outer, text=t('caption_expert_hidden_smart'), style='Sub.TLabel',
                      wraplength=520, justify='left').pack(anchor='w', pady=(0, 10))

        # --- 기본: 언어 / 브라우저 로그인 ---
        sec_basic = self._section(basic_zone, t('section_basic'))
        current_lang = settings.get('language', 'en')
        self.lang_var = tk.StringVar(value=LANG_DISPLAY.get(current_lang, LANG_DISPLAY['en']))
        self._row(sec_basic, '🌐', t('label_language'), t('caption_language'),
                  lambda p: ttk.Combobox(p, textvariable=self.lang_var, state='readonly',
                                         values=[LANG_DISPLAY['en'], LANG_DISPLAY['ko']],
                                         width=combo_width(list(LANG_DISPLAY.values()))).pack())

        self.use_local_cookies_var = tk.BooleanVar(value=bool(settings.get('use_local_cookies', False)))
        self._row(sec_basic, '🍪', t('label_use_local_cookies'), t('caption_use_local_cookies'),
                  lambda p: ToggleSwitch(p, variable=self.use_local_cookies_var, page_bg=PANEL).pack())

        if self.mode != 'smart':
            # --- 연결 ---
            sec1 = self._section(self._expert_zone, t('section_connection'))
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
            sec2 = self._section(self._expert_zone, t('section_speed_time'))
            self.timeout_var = tk.StringVar(value=str(settings['timeout']))
            self._row(sec2, '⏱', t('label_timeout'), t('caption_timeout'),
                      lambda p: ttk.Spinbox(p, from_=5, to=600, increment=5, textvariable=self.timeout_var,
                                            width=8).pack())
            self.rate_var = tk.StringVar(value=str(settings['max_rate']))
            self._row(sec2, '🚀', t('label_max_rate'), t('caption_max_rate'),
                      lambda p: ttk.Spinbox(p, from_=0, to=100_000_000, increment=1000, textvariable=self.rate_var,
                                            width=12).pack())

            # --- 정책 ---
            sec3 = self._section(self._expert_zone, t('section_policy'))
            robots_options = get_robots_options()
            self.robots_var = tk.StringVar(value=next(
                (label for code, label in robots_options if code == str(settings['robots'])), robots_options[2][1]))
            self._row(sec3, '🤖', t('label_robots'), t('caption_robots'),
                      lambda p: ttk.Combobox(p, textvariable=self.robots_var, state='readonly',
                                             values=[label for _, label in robots_options],
                                             width=combo_width([l for _, l in robots_options])).pack())

            self.external_var = tk.BooleanVar(value=bool(settings.get('external_links', False)))
            self._row(sec3, '🔗', t('label_external_links'), t('caption_external_links'),
                      lambda p: ToggleSwitch(p, variable=self.external_var, page_bg=PANEL).pack())

            # --- 네트워크 ---
            sec4 = self._section(self._expert_zone, t('section_network'))
            self.proxy_var = tk.StringVar(value=settings['proxy'])
            self._row(sec4, '🛰', t('label_proxy'), t('caption_proxy'),
                      lambda p: ttk.Entry(p, textvariable=self.proxy_var, width=32).pack(ipady=3))

            # --- 고급 ---
            sec6 = self._section(self._expert_zone, t('section_advanced'))
            self.referer_var = tk.StringVar(value=settings.get('referer', ''))
            self._row(sec6, '🔗', t('label_referer'), t('caption_referer'),
                      lambda p: ttk.Entry(p, textvariable=self.referer_var).pack(fill='x', ipady=3), full_width=True)

            self.lang_header_var = tk.StringVar(value=settings.get('lang_header', ''))
            self._row(sec6, '🗣', t('label_lang_header'), t('caption_lang_header'),
                      lambda p: ttk.Entry(p, textvariable=self.lang_header_var, width=26).pack(ipady=3))

            self.custom_headers_text = tk.Text(sec6, height=3, bg=PANEL_LIGHT, fg=FG, insertbackground=FG,
                                                relief='flat', font=(FONTS['mono'], 10), highlightthickness=1,
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
                      lambda p: ttk.Combobox(p, textvariable=self.link_format_var, state='readonly',
                                             values=[label for _, label in link_format_options],
                                             width=combo_width([l for _, l in link_format_options])).pack())

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
        sec7 = self._section(basic_zone, t('section_ai'))
        self._provider_options = [(p, ai_extract.PROVIDER_DISPLAY_NAMES[p]) for p in ai_extract.PROVIDERS]
        current_provider = settings.get('ai_provider', 'anthropic')
        self.ai_provider_var = tk.StringVar(value=next(
            (label for code, label in self._provider_options if code == current_provider),
            self._provider_options[0][1]))
        self._row(sec7, '🧠', t('label_ai_provider'), t('caption_ai_provider'),
                  lambda p: ttk.Combobox(p, textvariable=self.ai_provider_var, state='readonly',
                                         values=[label for _, label in self._provider_options],
                                         width=combo_width([l for _, l in self._provider_options])).pack())

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

    def _toggle_expert(self):
        """전문가 설정을 펼치거나 접는다."""
        self._expert_open = not self._expert_open
        if self._expert_open:
            self._expert_zone.pack(fill='x')
            self._expert_btn.set_text(f"▾  {t('expert_hide')}")
        else:
            self._expert_zone.pack_forget()
            self._expert_btn.set_text(f"▸  {t('expert_show')}")

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
        tk.Label(title_row, text=icon, bg=PANEL, fg=FG_MUTED, font=(FONTS['ui'], TYPE_BODY_LARGE)).pack(
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
        # 스마트 모드에서는 이 값들을 애초에 만들지 않았으므로, 기존에 저장돼 있던
        # 값을 그대로 둔다 (건드리지 않은 설정을 실수로 지우면 안 되기 때문).
        if self.mode != 'smart':
            robots_options = get_robots_options()
            robots_code = next((code for code, label in robots_options if label == self.robots_var.get()), '2')
            link_format_code = next(
                (code for code, label in self._link_format_options if label == self.link_format_var.get()),
                'relative')
            self.settings['user_agent'] = self.ua_var.get().strip()
            self.settings['connections'] = int(self.conn_var.get() or DEFAULT_SETTINGS['connections'])
            self.settings['retries'] = int(self.retry_var.get() or DEFAULT_SETTINGS['retries'])
            self.settings['timeout'] = int(self.timeout_var.get() or DEFAULT_SETTINGS['timeout'])
            self.settings['max_rate'] = int(self.rate_var.get() or 0)
            self.settings['robots'] = robots_code
            self.settings['external_links'] = bool(self.external_var.get())
            self.settings['proxy'] = self.proxy_var.get().strip()
            self.settings['referer'] = self.referer_var.get().strip()
            self.settings['lang_header'] = self.lang_header_var.get().strip()
            self.settings['custom_headers'] = self.custom_headers_text.get('1.0', 'end').strip()
            self.settings['cookies_file'] = self.cookies_file_var.get().strip()
            self.settings['link_format'] = link_format_code
            self.settings['near_files'] = bool(self.near_files_var.get())
            self.settings['conn_per_sec'] = int(self.conn_per_sec_var.get() or 0)
            self.settings['warc'] = bool(self.warc_var.get())
            self.settings['search_index'] = bool(self.search_index_var.get())

        lang_code = next((code for code, name in LANG_DISPLAY.items() if name == self.lang_var.get()), 'en')
        self.settings['language'] = lang_code
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
                     font=(FONTS['ui'], TYPE_BODY, 'bold')).pack(anchor='w')
            tk.Label(card.body, text=desc, bg=PANEL, fg=FG_MUTED, font=(FONTS['ui'], TYPE_CAPTION),
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
                                  relief='flat', font=(FONTS['mono'], 10), highlightthickness=1,
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
                 font=(FONTS['ui'], TYPE_CAPTION), wraplength=480, justify='left', padx=12, pady=10).pack(anchor='w')

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
                                         relief='flat', font=(FONTS['mono'], 10), highlightthickness=1,
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
        ttk.Combobox(row, textvariable=type_var, state='readonly', values=self.TYPE_OPTIONS,
                     width=combo_width(self.TYPE_OPTIONS)).pack(
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


class AIRefineDialog(tk.Toplevel):
    """AI 추출로 뽑아낸 표를 자연어로 다듬는다. AIScopeRulesDialog와 같은
    '제안받기 -> 미리보기 -> 적용' 흐름이라 배운 적 없어도 낯설지 않다.

    AI는 코드를 짜지 않는다. data_refine의 정해진 안전한 연산(열 삭제/이동/
    결측치 채우기/중복 제거/필터/정렬) 중에서 고르기만 하고, 실제 계산은
    이 앱이 정확하게 수행한다 - 그래서 적용 전에 '몇 행이 몇 행으로, 어떤
    열이 생기고 없어지는지'를 코드 없이 그대로 보여줄 수 있다."""

    def __init__(self, parent, records, out_dir, settings, log_fn):
        super().__init__(parent)
        self.title(t('dialog_refine_title'))
        self.configure(bg=BG)
        self.geometry('560x520')
        self.minsize(460, 420)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.records = records
        self.out_dir = out_dir
        self.settings = settings
        self.log_fn = log_fn
        self._pending_records = None

        outer = make_scrollable(self)
        outer.configure(padding=20)
        ttk.Label(outer, text=t('dialog_refine_title'), style='Title2.TLabel').pack(anchor='w', pady=(0, 4))
        ttk.Label(outer, text=t('caption_refine_intro', n=len(records)), style='Sub.TLabel',
                  wraplength=500, justify='left').pack(anchor='w', pady=(0, 12))

        ttk.Label(outer, text=t('label_refine_instruction'), style='MutedRoot.TLabel').pack(anchor='w')
        self.instruction_text = tk.Text(outer, height=2, bg=PANEL_LIGHT, fg=FG, insertbackground=FG,
                                        relief='flat', font=(FONTS['mono'], 10), highlightthickness=1,
                                        highlightbackground=BORDER, highlightcolor=ACCENT, padx=6, pady=4)
        self.instruction_text.pack(fill='x', pady=(4, 2))
        ttk.Label(outer, text=t('caption_refine_examples'), style='Caption.TLabel',
                  wraplength=500, justify='left').pack(anchor='w')

        RoundedButton(outer, t('btn_propose_refine'), command=self._on_propose, variant='neutral').pack(
            anchor='w', pady=(10, 0))

        preview_box = tk.Frame(outer, bg=PANEL_LIGHT, highlightbackground=BORDER, highlightthickness=1)
        preview_box.pack(fill='x', pady=(14, 0))
        self.preview_var = tk.StringVar(value='')
        tk.Label(preview_box, textvariable=self.preview_var, bg=PANEL_LIGHT, fg=FG,
                 font=(FONTS['ui'], TYPE_CAPTION), wraplength=480, justify='left', padx=12, pady=10).pack(anchor='w')

        btn_frame = ttk.Frame(outer)
        btn_frame.pack(fill='x', pady=(16, 0))
        self.apply_btn = RoundedButton(btn_frame, t('btn_apply_refine'), command=self._on_apply, variant='accent')
        self.apply_btn.set_enabled(False)
        self.apply_btn.pack(side='right', padx=(6, 0))
        RoundedButton(btn_frame, t('btn_skip'), command=self.destroy, variant='ghost').pack(side='right')

    def _on_propose(self):
        instruction = self.instruction_text.get('1.0', 'end').strip()
        if not instruction:
            self.log_fn(t('warn_refine_need_instruction'))
            return
        ai_config = get_active_ai_config(self.settings)
        if not ai_config.get('api_key'):
            self.log_fn(t('warn_need_api_key'))
            return
        try:
            plan = data_refine.propose_refine_plan(
                instruction, self.records, ai_config['api_key'], provider=ai_config['provider'])
        except Exception as e:
            self.log_fn(t('warn_refine_failed', e=e))
            return

        operations = plan.get('operations', [])
        new_records, warnings = data_refine.apply_refine_plan(self.records, operations)
        summary = data_refine.summarize_change(self.records, new_records)
        self._pending_records = new_records

        lines = [plan.get('explanation', '').strip() or t('preview_refine_none')]
        lines.append(t('preview_refine_summary', rows_before=summary['rows_before'], rows_after=summary['rows_after']))
        if summary['columns_added']:
            lines.append(t('preview_columns_added', cols=', '.join(summary['columns_added'])))
        if summary['columns_removed']:
            lines.append(t('preview_columns_removed', cols=', '.join(summary['columns_removed'])))
        if warnings:
            lines.append(t('preview_refine_warnings', warnings='; '.join(warnings)))
        self.preview_var.set('\n'.join(lines))
        self.apply_btn.set_enabled(bool(operations))

    def _on_apply(self):
        if not self._pending_records:
            return
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        saved = ai_extract.export_records(self._pending_records, self.out_dir, f'refined_{timestamp}', ['csv', 'json'])
        self.log_fn(t('log_refine_applied', n=len(saved)))
        self.destroy()


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
                                  relief='flat', font=(FONTS['mono'], 10), highlightthickness=1,
                                  highlightbackground=BORDER, highlightcolor=ACCENT, padx=6, pady=4)
        self.goal_text.pack(fill='x', pady=(4, 2))
        ttk.Label(outer, text=t('caption_scope_goal'), style='Caption.TLabel').pack(anchor='w')

        caption_box = tk.Frame(outer, bg=ACCENT_SOFT)
        caption_box.pack(fill='x', pady=(10, 10))
        tk.Label(caption_box, text=t('caption_scope_cost'), bg=ACCENT_SOFT, fg=FG,
                 font=(FONTS['ui'], TYPE_CAPTION), wraplength=480, justify='left', padx=12, pady=10).pack(anchor='w')

        RoundedButton(outer, t('btn_get_scope_rules'), command=self._on_get_rules, variant='neutral').pack(anchor='w')

        ttk.Label(outer, text=t('label_proposed_rules'), style='MutedRoot.TLabel').pack(anchor='w', pady=(14, 2))
        self.rules_text = tk.Text(outer, height=6, bg=PANEL_LIGHT, fg=FG, insertbackground=FG,
                                   relief='flat', font=(FONTS['mono'], 10), highlightthickness=1,
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

# HTTrack 명령 조립/실행/진행률 파싱은 httrack_engine.py로 분리했다.
from httrack_engine import (  # noqa: F401
    HTTRACK_EXE, ACTION_FLAGS, DEFAULT_FILTERS, BASE_FILTER_RULES,
    existing_mirror_kind, cookie_domains_for, export_local_cookies,
    build_httrack_cmd, parse_dashboard_line, run_httrack,
)

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
                 font=(FONTS['ui'], TYPE_CAPTION), wraplength=560, justify='left',
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
                 font=(FONTS['mono'], 9), wraplength=580, justify='left', anchor='w').pack(
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
        # 고른 값에 맞는 설명으로 매번 바뀐다 - 예전엔 무엇을 골라도 설명이
        # 'networkidle' 얘기만 해서, 다른 값을 골랐을 때 뭘 뜻하는지 알 수 없었다.
        wait_caption_var = tk.StringVar()

        def _sync_wait_caption(*_a):
            wait_caption_var.set(t(f"caption_wait_until_{app.wait_until_var.get()}"))
        app.wait_until_var.trace_add('write', _sync_wait_caption)
        _sync_wait_caption()
        ttk.Label(parent, textvariable=wait_caption_var, style='Caption.TLabel',
                  wraplength=580).pack(anchor='w', pady=(2, 0))

        # 어디까지 따라갈지(도메인/폴더 범위) - 사이트 미러링의 '수집 범위' 다이얼로그와
        # 같은 변수를 쓴다. 예전엔 이 값이 스마트 모드에서는 손댈 곳이 없어서
        # 미러링 쪽 화면에 가야만 바꿀 수 있었다.
        ttk.Label(parent, text=t('label_domain_scope'), style='RowTitle.TLabel').pack(anchor='w', pady=(16, 0))
        ttk.Combobox(parent, textvariable=app.domain_scope_var, state='readonly',
                     values=[label for _, label in app.domain_scope_options],
                     width=combo_width([l for _, l in app.domain_scope_options])).pack(
            fill='x', pady=(4, 0), ipady=2)
        ttk.Label(parent, text=t('caption_domain_scope'), style='Caption.TLabel',
                  wraplength=580).pack(anchor='w', pady=(2, 0))

        ttk.Checkbutton(parent, text=t('label_same_folder'),
                        variable=app.same_folder_var).pack(anchor='w', pady=(14, 0))
        ttk.Label(parent, text=t('caption_same_folder'), style='Caption.TLabel',
                  wraplength=580).pack(anchor='w', pady=(2, 0))

        # 요청 사이 텀 - HTTrack 쪽 안전장치에는 있는데 스마트 크롤링엔 없던 것.
        ttk.Checkbutton(parent, text=t('label_smart_pause_enable'),
                        variable=app.smart_pause_enable_var,
                        command=lambda: _sync_pause_row()).pack(anchor='w', pady=(16, 0))
        pause_row = ttk.Frame(parent, style='Panel.TFrame')
        ttk.Label(pause_row, text=t('safety_pause_between'), style='Muted.TLabel').pack(side='left')
        ttk.Spinbox(pause_row, from_=0, to=300, textvariable=app.smart_pause_min_var, width=6).pack(
            side='left', padx=(8, 4))
        ttk.Label(pause_row, text=t('safety_pause_and'), style='Muted.TLabel').pack(side='left')
        ttk.Spinbox(pause_row, from_=0, to=300, textvariable=app.smart_pause_max_var, width=6).pack(
            side='left', padx=(4, 4))
        ttk.Label(pause_row, text=t('safety_pause_unit'), style='Muted.TLabel').pack(side='left')

        def _sync_pause_row():
            if app.smart_pause_enable_var.get():
                pause_row.pack(anchor='w', pady=(6, 0))
            else:
                pause_row.pack_forget()
        _sync_pause_row()
        ttk.Label(parent, text=t('caption_smart_pause'), style='Caption.TLabel',
                  wraplength=580).pack(anchor='w', pady=(4, 0))

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
                 font=(FONTS['ui'], TYPE_CAPTION), wraplength=560, justify='left',
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
        self.follow_depth_var = tk.StringVar(value='1')
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
                 font=(FONTS['ui'], TYPE_CAPTION), wraplength=380, justify='center').pack(pady=(0, 10))

        self.start_button = CircularStartButton(center, command=self._on_power_clicked, size=180)
        self.start_button.pack()
        self.job_var = tk.StringVar()
        # height=1로 한 줄을 미리 잡아둔다. 상태 문구가 나타났다 사라질 때
        # 아래 내용이 위아래로 밀리지 않게 하기 위함.
        self._status_label = tk.Label(center, textvariable=self.job_var, bg=BG, fg=FG_MUTED,
                                      height=1, font=(FONTS['ui'], TYPE_BODY, 'bold'))
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

        # 받아온 결과에서 AI로 데이터를 뽑아내는 진입점. '결과 폴더 열기'와 똑같은
        # 시점(작업이 끝나 폴더가 생겼을 때)에만 눌리게 한다.
        self.ai_extract_btn = RoundedButton(head, f"🤖 {t('btn_ai_extract')}", command=self._open_ai_extract_dialog,
                                            variant='ghost', page_bg=PANEL, padx=13, pady=7)
        self.ai_extract_btn.set_enabled(False)
        self.ai_extract_btn.pack(side='right', padx=(0, 8))

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
        OptionsDialog(self.root, self, group)

    def _save_use_local_cookies(self):
        self.settings['use_local_cookies'] = bool(self.use_local_cookies_var.get())
        save_settings(self.settings)

    def _refresh_option_summaries(self):
        """메인 화면의 요약 행에 지금 설정된 값을 사람이 읽는 문장으로 채운다."""
        if not hasattr(self, '_summary_vars'):
            return
        if 'smart' in self._summary_vars:
            text = t('summary_smart_value', pages=self.max_pages_var.get(), depth=self.follow_depth_var.get())
            pause = self._effective_smart_pause()
            if pause:
                text += f' · {pause[0]}~{pause[1]}s'
            self._summary_vars['smart'].set(text)
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
                      bg=PANEL, fg=FG_MUTED, font=(FONTS['ui'], TYPE_CAPTION)).pack(anchor='w')
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
        if not ai_config.get('api_key'):
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
        self.ai_extract_btn.set_enabled(False)
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
            self.ai_extract_btn.set_enabled(True)
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
        self.ai_extract_btn.set_enabled(False)
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
            self.ai_extract_btn.set_enabled(True)
            project_status = 'success'
        elif isinstance(result, int) and result == 0 and engine_errors > 0:
            self._log(f"\n[{ts}] {t('log_done_with_errors', n=engine_errors)}")
            self.open_folder_btn.set_enabled(True)
            self.ai_extract_btn.set_enabled(True)
            project_status = 'errors'
        elif isinstance(result, int):
            self._log(f"\n[{ts}] {t('log_done_code', code=result)}")
            self.open_folder_btn.set_enabled(True)
            self.ai_extract_btn.set_enabled(True)
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
