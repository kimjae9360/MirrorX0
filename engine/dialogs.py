"""설정/실행/추출 관련 창(다이얼로그)들을 모아둔 곳.

main.py가 3700줄을 넘어가면서 한 파일에서 앱 로직과 화면을 같이 보기가
어려워져 분리했다. 여기 있는 클래스들은 앱 상태를 직접 갖지 않고,
필요한 값은 생성할 때 넘겨받는다(app 또는 settings) - 그래서 main.py를
import하지 않아도 되고, 순환 import가 생기지 않는다.
"""
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
import threading
import queue

import jobs as jobs_mod
import scheduler_win
import click_select
import clean_organize
import ollama_setup
import ai_extract
import ai_scope
import data_refine

from theme import *  # noqa: F401,F403
from i18n import (
    LANG_DISPLAY, set_language, t, get_actions, get_job_labels,
    get_robots_options, get_filter_groups,
)
from storage import DEFAULT_SETTINGS, load_settings, save_settings, get_active_ai_config, ai_ready
from httrack_engine import BASE_FILTER_RULES, existing_mirror_kind
from webutil import normalize_url, _fetch_sample_html_from_url
from widgets import (
    make_scrollable, combo_width,
    SegmentedControl, RoundedCard, RoundedButton, ToggleSwitch,
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
        self._parent = parent
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
        # 전문가 설정을 잘못 건드려도(값을 몰라도) 되돌릴 수 있게, 왼쪽에 따로
        # 둔다(저장/취소와 헷갈리지 않도록 시각적으로 분리).
        RoundedButton(btn_row, t('btn_reset_defaults'), command=self._reset_to_defaults,
                      variant='ghost').pack(side='left')

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
        current_provider = settings.get('ai_provider', 'ollama')
        self.ai_provider_var = tk.StringVar(value=next(
            (label for code, label in self._provider_options if code == current_provider),
            self._provider_options[0][1]))
        self._row(sec7, '🧠', t('label_ai_provider'), t('caption_ai_provider'),
                  lambda p: ttk.Combobox(p, textvariable=self.ai_provider_var, state='readonly',
                                         values=[label for _, label in self._provider_options],
                                         width=combo_width([l for _, l in self._provider_options])).pack())

        tradeoff_box = tk.Frame(sec7, bg=ACCENT_SOFT)
        tradeoff_box.pack(fill='x', pady=(0, 12))
        tk.Label(tradeoff_box, text=t('caption_ollama_tradeoff'), bg=ACCENT_SOFT, fg=FG,
                 font=(FONTS['ui'], TYPE_CAPTION), wraplength=480, justify='left', padx=12, pady=10).pack(anchor='w')

        # Ollama는 무료지만 별도 설치가 필요해서, 안 되어 있으면 "왜 안 되는지"
        # 모른 채 막히기 쉽다. 상태를 자동으로 감지해 알려주고, 실제 설치/실행/
        # 모델 받기는 사용자가 버튼을 눌렀을 때만 시작한다(몰래 받지 않는다).
        self._ollama_row = tk.Frame(sec7, bg=PANEL)
        self._ollama_row.pack(fill='x', pady=(0, 12))
        self._ollama_status_var = tk.StringVar(value=t('ollama_status_checking'))
        tk.Label(self._ollama_row, textvariable=self._ollama_status_var, bg=PANEL, fg=FG_MUTED,
                 font=(FONTS['ui'], TYPE_CAPTION), wraplength=380, justify='left').pack(side='left')
        self._ollama_btn = RoundedButton(self._ollama_row, t('btn_ollama_check'),
                                         command=self._on_ollama_action,
                                         variant='neutral', page_bg=PANEL, padx=12, pady=7)
        self._ollama_btn.pack(side='right')
        self._ollama_action = None
        self._ollama_queue = queue.Queue()
        self.after(80, self._refresh_ollama_status)

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

    def _refresh_ollama_status(self):
        """Ollama 상태를 확인해 안내 문구와 버튼을 그 상태에 맞게 바꾼다.
        상태 확인에 서버 응답 대기가 있어 스레드로 돌린다. 결과는 반드시 큐로
        넘긴다 - 스레드에서 tkinter의 after()를 직접 부르면
        'main thread is not in main loop'로 죽는다(앱의 다른 곳에서 쓰는
        msg_queue 패턴과 같은 이유)."""
        def worker():
            try:
                status, models = ollama_setup.get_status()
            except Exception:
                status, models = ollama_setup.NOT_INSTALLED, []
            self._ollama_queue.put(('status', status, models))

        threading.Thread(target=worker, daemon=True).start()
        self._poll_ollama_queue()

    def _poll_ollama_queue(self):
        """큐에 쌓인 결과를 UI 스레드에서 꺼내 반영한다."""
        if not self._ollama_row.winfo_exists():
            return
        pending = True
        try:
            while True:
                msg = self._ollama_queue.get_nowait()
                if msg[0] == 'status':
                    self._apply_ollama_status(msg[1], msg[2])
                    pending = False
                elif msg[0] == 'log':
                    self._ollama_status_var.set(msg[1])
        except queue.Empty:
            pass
        if pending:
            self.after(150, self._poll_ollama_queue)

    def _apply_ollama_status(self, status, models):
        if not self._ollama_row.winfo_exists():
            return
        mapping = {
            ollama_setup.NOT_INSTALLED: ('ollama_status_not_installed', 'btn_ollama_install', 'install'),
            ollama_setup.NOT_RUNNING: ('ollama_status_not_running', 'btn_ollama_start', 'start'),
            ollama_setup.NO_MODEL: ('ollama_status_no_model', 'btn_ollama_pull', 'pull'),
            ollama_setup.READY: ('ollama_status_ready', 'btn_ollama_check', 'check'),
        }
        status_key, btn_key, action = mapping.get(
            status, ('ollama_status_not_installed', 'btn_ollama_install', 'install'))
        text = t(status_key, model=models[0]) if status == ollama_setup.READY and models \
            else t(status_key)
        self._ollama_status_var.set(text)
        self._ollama_btn.set_text(t(btn_key))
        self._ollama_btn.set_enabled(True)
        self._ollama_action = action

    def _on_ollama_action(self):
        """설치/실행/모델 받기 - 어느 것이든 사용자가 이 버튼을 눌렀을 때만 시작한다."""
        action = self._ollama_action
        if action == 'check' or action is None:
            self._ollama_status_var.set(t('ollama_status_checking'))
            self._refresh_ollama_status()
            return

        self._ollama_btn.set_enabled(False)
        self._ollama_status_var.set(t('ollama_status_working'))

        # 스레드에서 UI를 직접 건드리지 않고 큐로만 넘긴다.
        def log(msg):
            self._ollama_queue.put(('log', msg))

        def worker():
            if action == 'install':
                ollama_setup.install(log_fn=log)
                ollama_setup.start_server(log_fn=log)
            elif action == 'start':
                ollama_setup.start_server(log_fn=log)
            elif action == 'pull':
                ollama_setup.pull_model(log_fn=log)
            # 끝난 뒤 상태를 다시 확인한다. 여기서도 after()를 부르면 안 되므로
            # 상태 조회까지 이 스레드에서 마치고 결과만 큐로 넘긴다.
            try:
                status, models = ollama_setup.get_status()
            except Exception:
                status, models = ollama_setup.NOT_INSTALLED, []
            self._ollama_queue.put(('status', status, models))

        threading.Thread(target=worker, daemon=True).start()
        self._poll_ollama_queue()

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
            (code for code, label in self._provider_options if label == self.ai_provider_var.get()), 'ollama')
        self.settings['ai_provider'] = provider_code
        self.settings['anthropic_api_key'] = self.anthropic_key_var.get().strip()
        self.settings['openai_api_key'] = self.openai_key_var.get().strip()
        self.settings['gemini_api_key'] = self.gemini_key_var.get().strip()
        self.settings['use_local_cookies'] = bool(self.use_local_cookies_var.get())
        save_settings(self.settings)
        self.on_save()
        self.destroy()

    def _reset_to_defaults(self):
        # API 키까지 포함해서 전부 지워지는 되돌릴 수 없는 작업이라, 실수로
        # 누르는 걸 막기 위해 반드시 한 번 더 확인받는다.
        if not messagebox.askyesno(t('confirm_reset_title'), t('confirm_reset_body'), parent=self):
            return
        save_settings(dict(DEFAULT_SETTINGS))
        self.on_save()
        self.destroy()
        PreferencesDialog(self._parent, load_settings(), on_save=self.on_save, mode=self.mode)


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
    SCHEDULE_OPTIONS = [('once', 'schedule_type_once'), ('hourly', 'schedule_type_hourly'),
                        ('daily', 'schedule_type_daily'), ('weekly', 'schedule_type_weekly')]
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

        interval_row = ttk.Frame(outer)
        interval_row.pack(fill='x', pady=(0, 12))
        ttk.Label(interval_row, text=t('label_schedule_interval'), style='MutedRoot.TLabel').pack(side='left')
        self.interval_var = tk.StringVar(value=str(schedule.get('interval', 1) or 1))
        ttk.Spinbox(interval_row, from_=1, to=23, textvariable=self.interval_var, width=4).pack(
            side='left', padx=(10, 0))

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
        try:
            interval_value = max(1, min(23, int(self.interval_var.get())))
        except (TypeError, ValueError):
            interval_value = 1

        schedule = {'type': sched_type, 'at': at_value, 'date': date_value, 'weekdays': weekdays,
                    'interval': interval_value}
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
        self.sqlite_var = tk.BooleanVar(value='sqlite' in existing_formats)
        ttk.Checkbutton(export_row, text='CSV', variable=self.csv_var).pack(side='left', padx=(10, 0))
        ttk.Checkbutton(export_row, text='JSON', variable=self.json_var).pack(side='left', padx=(10, 0))
        ttk.Checkbutton(export_row, text='Excel', variable=self.xlsx_var).pack(side='left', padx=(10, 0))
        ttk.Checkbutton(export_row, text='SQLite DB', variable=self.sqlite_var).pack(side='left', padx=(10, 0))

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
        if not ai_ready(ai_config):
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
        if self.sqlite_var.get():
            formats.append('sqlite')
        fields = [{'name': nv.get().strip(), 'label': lv.get().strip(), 'type': tv.get()}
                  for nv, lv, tv, _ in self.field_rows if nv.get().strip()]
        return {
            'enabled': self.enabled_var.get(),
            'instruction': self.instruction_text.get('1.0', 'end').strip(),
            'fields': fields,
            'export_formats': formats or ['csv'],
        }


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

        # AI를 실제로 부르기 전에 몇 번 호출될지 미리 보여준다 - 반복 패턴 감지는
        # AI 없이 구조만 보는 것이라 이 계산 자체는 공짜이고, 짐작이 아니라
        # 실제 추출과 똑같은 파일을 보고 낸 정확한 숫자다.
        try:
            estimate = ai_extract.estimate_extraction_calls(out_dir)
        except Exception:
            estimate = None
        if estimate and estimate['files']:
            cost_box = tk.Frame(outer, bg=ACCENT_SOFT)
            cost_box.pack(fill='x', pady=(10, 0))
            tk.Label(cost_box, text=t('caption_extract_estimate', calls=estimate['estimated_calls'],
                                      files=estimate['files'], rows=estimate['estimated_rows']),
                     bg=ACCENT_SOFT, fg=FG, font=(FONTS['ui'], TYPE_CAPTION), wraplength=460,
                     justify='left', padx=12, pady=10).pack(anchor='w')

        btn_frame = ttk.Frame(outer)
        btn_frame.pack(fill='x', pady=(16, 0))
        RoundedButton(btn_frame, t('btn_run_extraction'), command=self._run, variant='accent').pack(
            side='right', padx=(6, 0))
        RoundedButton(btn_frame, t('btn_cancel'), command=self.destroy, variant='ghost').pack(side='right')

    def _run(self):
        config = self.ai_panel.get_config()
        self.destroy()
        self.on_run(config)


class PaginationExtractDialog(tk.Toplevel):
    """다음 페이지로 계속 이어지는 목록형 사이트(상품 목록, 게시판 등)를 시작
    주소 하나만으로 바로 추출한다. 사이트 전체를 먼저 미러링할 필요가 없다 -
    AI 추출(이미 받아둔 폴더 대상)과 달리, 이건 그 자체로 하나의 독립된
    데이터 수집 액션이라 별도 진입점으로 둔다."""

    def __init__(self, parent, settings, log_fn, on_run):
        super().__init__(parent)
        self.title(t('dialog_pagination_title'))
        self.configure(bg=BG)
        self.geometry('520x680')
        self.minsize(460, 460)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.settings = settings
        self.on_run = on_run

        outer = make_scrollable(self)
        outer.configure(padding=20)
        ttk.Label(outer, text=t('dialog_pagination_title'), style='Title2.TLabel').pack(anchor='w', pady=(0, 6))
        ttk.Label(outer, text=t('caption_pagination_intro'), style='Caption.TLabel',
                  wraplength=460, justify='left').pack(anchor='w', pady=(0, 10))

        ttk.Label(outer, text=t('label_pagination_start_url'), style='MutedRoot.TLabel').pack(anchor='w')
        self.url_var = tk.StringVar()
        ttk.Entry(outer, textvariable=self.url_var).pack(fill='x', pady=(4, 12), ipady=3)

        def get_sample():
            url = normalize_url(self.url_var.get())
            return _fetch_sample_html_from_url(url) if url else None

        self.ai_panel = AIExtractPanel(
            outer, get_ai_config=lambda: get_active_ai_config(self.settings),
            log_fn=log_fn, get_sample_html=get_sample)
        self.ai_panel.enabled_var.set(True)
        self.ai_panel._on_toggle()

        max_row = ttk.Frame(outer)
        max_row.pack(fill='x', pady=(6, 4))
        ttk.Label(max_row, text=t('label_pagination_max_pages'), style='MutedRoot.TLabel').pack(side='left')
        self.max_pages_var = tk.StringVar(value='20')
        ttk.Spinbox(max_row, from_=1, to=200, textvariable=self.max_pages_var, width=6).pack(
            side='left', padx=(10, 0))

        self.use_cookies_var = tk.BooleanVar(value=bool(settings.get('use_local_cookies')))
        ttk.Checkbutton(outer, text=t('label_use_local_cookies'), variable=self.use_cookies_var).pack(
            anchor='w', pady=(8, 12))

        btn_frame = ttk.Frame(outer)
        btn_frame.pack(fill='x', pady=(16, 0))
        RoundedButton(btn_frame, t('btn_run_extraction'), command=self._run, variant='accent').pack(
            side='right', padx=(6, 0))
        RoundedButton(btn_frame, t('btn_cancel'), command=self.destroy, variant='ghost').pack(side='right')

    def _run(self):
        url = normalize_url(self.url_var.get())
        if not url:
            self.ai_panel.log_fn(t('warn_pagination_need_url'))
            return
        config = self.ai_panel.get_config()
        if not config.get('fields'):
            self.ai_panel.log_fn(t('warn_need_fields'))
            return
        try:
            max_pages = max(1, min(200, int(self.max_pages_var.get())))
        except (TypeError, ValueError):
            max_pages = 20
        self.destroy()
        self.on_run(url, config, max_pages, self.use_cookies_var.get())


class ClickToSelectDialog(tk.Toplevel):
    """실제 웹페이지 화면에서 마우스로 항목 하나를 가리키고 클릭하면, 그것과
    구조적으로 같은 종류인 형제 요소를 전부 찾아 표로 뽑는다(Listly의
    '클릭해서 고르기' 참고). 자동 패턴 감지(AI 추출의 반복 항목 자동 감지)가
    헷갈려하는 애매한 구조에서, 사용자가 직접 예시를 짚어 정확히 잡아주는
    수동 경로다."""

    def __init__(self, parent, settings, log_fn, on_extract):
        super().__init__(parent)
        self.title(t('dialog_click_select_title'))
        self.configure(bg=BG)
        self.geometry('520x700')
        self.minsize(460, 480)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.settings = settings
        self.log_fn = log_fn
        self.on_extract = on_extract
        self._picked = None
        self._queue = queue.Queue()

        outer = make_scrollable(self)
        outer.configure(padding=20)
        ttk.Label(outer, text=t('dialog_click_select_title'), style='Title2.TLabel').pack(anchor='w', pady=(0, 6))
        ttk.Label(outer, text=t('caption_click_select_intro'), style='Caption.TLabel',
                  wraplength=460, justify='left').pack(anchor='w', pady=(0, 10))

        ttk.Label(outer, text=t('label_click_select_url'), style='MutedRoot.TLabel').pack(anchor='w')
        self.url_var = tk.StringVar()
        ttk.Entry(outer, textvariable=self.url_var).pack(fill='x', pady=(4, 8), ipady=3)

        self.use_cookies_var = tk.BooleanVar(value=bool(settings.get('use_local_cookies')))
        ttk.Checkbutton(outer, text=t('label_use_local_cookies'), variable=self.use_cookies_var).pack(
            anchor='w', pady=(0, 10))

        self.pick_btn = RoundedButton(outer, t('btn_open_browser_pick'), command=self._start_pick,
                                     variant='neutral', page_bg=PANEL)
        self.pick_btn.pack(anchor='w')

        self.status_var = tk.StringVar(value='')
        ttk.Label(outer, textvariable=self.status_var, style='Caption.TLabel', wraplength=460,
                  justify='left').pack(anchor='w', pady=(6, 10))

        # 항목을 고르기 전에는 필드 정의 영역/실행 버튼을 숨겨둔다 - 고른 뒤에야 채워 넣는다.
        self.fields_area = ttk.Frame(outer, style='Panel.TFrame')
        self.btn_frame = ttk.Frame(outer)
        RoundedButton(self.btn_frame, t('btn_cancel'), command=self.destroy, variant='ghost').pack(side='right')

        self.after(150, self._poll)

    def _start_pick(self):
        url = normalize_url(self.url_var.get())
        if not url:
            self.log_fn(t('warn_pagination_need_url'))
            return
        self.pick_btn.set_enabled(False)
        self.status_var.set(t('status_click_select_waiting'))
        use_cookies = self.use_cookies_var.get()

        def worker():
            try:
                result = click_select.pick_element_and_collect(url, use_local_cookies=use_cookies)
                self._queue.put(('picked', result))
            except Exception as e:
                self._queue.put(('error', str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _poll(self):
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == 'picked':
                    self._on_picked(payload)
                elif kind == 'error':
                    self.pick_btn.set_enabled(True)
                    self.status_var.set('')
                    self.log_fn(t('warn_click_select_failed', e=payload))
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(150, self._poll)

    def _on_picked(self, result):
        self._picked = result
        self.pick_btn.set_enabled(True)
        self.status_var.set(t('status_click_select_picked', n=len(result['items_html']),
                              selector=result['selector']))

        if not hasattr(self, 'ai_panel'):
            self.fields_area.pack(fill='x', pady=(0, 8))
            self.ai_panel = AIExtractPanel(
                self.fields_area, get_ai_config=lambda: get_active_ai_config(self.settings),
                log_fn=self.log_fn, get_sample_html=lambda: self._picked['items_html'][0])
            self.ai_panel.enabled_var.set(True)
            self.ai_panel._on_toggle()

            self.btn_frame.pack(fill='x', pady=(16, 0))
            RoundedButton(self.btn_frame, t('btn_run_extraction'), command=self._run, variant='accent').pack(
                side='right', padx=(6, 0))

    def _run(self):
        if not self._picked:
            return
        config = self.ai_panel.get_config()
        if not config.get('fields'):
            self.log_fn(t('warn_need_fields'))
            return
        items_html = self._picked['items_html']
        self.destroy()
        self.on_extract(items_html, config)


class DataToolsDialog(tk.Toplevel):
    """AI 추출/페이지네이션 추출/클릭해서 고르기/정리된 사본 만들기 - 4가지
    데이터 도구를 하나의 진입점으로 모은다. 각각 작은 아이콘 버튼으로 흩어
    놓으면 뭐가 뭔지, 언제 쓰는 건지 알기 어렵다는 피드백을 반영 - 여기서는
    각 도구가 무엇이고 언제 쓰는지 한 줄 설명과 함께 고르게 한다."""

    def __init__(self, parent, has_project, on_pick):
        super().__init__(parent)
        self.title(t('dialog_data_tools_title'))
        self.configure(bg=BG)
        self.geometry('580x560')
        self.minsize(480, 420)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.on_pick = on_pick

        outer = make_scrollable(self)
        outer.configure(padding=20)
        ttk.Label(outer, text=t('dialog_data_tools_title'), style='Title2.TLabel').pack(anchor='w', pady=(0, 4))
        ttk.Label(outer, text=t('caption_data_tools_intro'), style='Caption.TLabel',
                  wraplength=500, justify='left').pack(anchor='w', pady=(0, 14))

        tools = [
            ('ai_extract', '🤖', t('btn_ai_extract'), t('desc_ai_extract'), has_project),
            ('pagination', '📑', t('btn_pagination_extract'), t('desc_pagination_extract'), True),
            ('click_select', '🖱', t('btn_click_select'), t('desc_click_select'), True),
            ('clean_organize', '🧹', t('btn_clean_organize'), t('desc_clean_organize'), has_project),
        ]
        for key, icon, title, desc, enabled in tools:
            self._tool_row(outer, key, icon, title, desc, enabled)

    def _tool_row(self, parent, key, icon, title, desc, enabled):
        card = RoundedCard(parent, radius=12, padding=12)
        card.pack(fill='x', pady=(0, 10))
        row = ttk.Frame(card.body, style='Panel.TFrame')
        row.pack(fill='x')
        tk.Label(row, text=icon, bg=PANEL, fg=ACCENT, font=(FONTS['ui'], 20)).pack(side='left', padx=(0, 12))
        text_col = ttk.Frame(row, style='Panel.TFrame')
        text_col.pack(side='left', fill='x', expand=True)
        ttk.Label(text_col, text=title, style='RowTitle.TLabel').pack(anchor='w')
        ttk.Label(text_col, text=desc, style='Caption.TLabel', wraplength=340, justify='left').pack(anchor='w')
        if not enabled:
            tk.Label(text_col, text=t('caption_tool_needs_project'), bg=PANEL, fg=CRITICAL,
                     font=(FONTS['ui'], TYPE_CAPTION)).pack(anchor='w', pady=(4, 0))
        btn = RoundedButton(row, t('btn_use_tool'), command=lambda: self._pick(key),
                             variant='accent' if enabled else 'ghost')
        btn.pack(side='right')
        btn.set_enabled(enabled)

    def _pick(self, key):
        self.destroy()
        self.on_pick(key)


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
        if not ai_ready(ai_config):
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
        if not ai_ready(ai_config):
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


class OptionsDialog(tk.Toplevel):
    """메인 화면의 설정 요약 행을 눌렀을 때, 그 그룹 하나만 편집하는 작은 창.
    ExpressVPN이 'Selected Location  >' 같은 행을 누르면 그 설정만 보여주는
    방식을 그대로 따른다 - 모든 설정을 환경설정에 몰아넣지 않고, 지금 값이
    메인 화면에 보이고 누르면 바로 고칠 수 있게 하기 위함."""

    TITLES = {'method': 'panel_method', 'scope': 'panel_scope', 'files': 'panel_files',
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

        {'method': self._build_method, 'scope': self._build_scope, 'files': self._build_files,
         'safety': self._build_safety, 'power': self._build_power,
         'smart': self._build_smart}[group](body)

        self.protocol('WM_DELETE_WINDOW', self._close)

    def _close(self):
        self.app._refresh_option_summaries()
        self.destroy()

    # ---------------- 받는 방식 ----------------
    def _build_method(self, parent):
        """'미러링 vs 스마트'를 다운로드의 한 옵션으로 고르게 한다.
        예전엔 화면 맨 위 큰 토글이었는데, 이름에 '크롤링'이 들어가 있어
        데이터 추출 기능으로 오해받았다. 결과물은 둘 다 '파일'이므로
        여기서 '어떻게 받을지'로만 고르게 하는 편이 헷갈리지 않는다."""
        app = self.app

        def on_pick():
            app._on_mode_changed()

        for value, title_key, desc_key in (
                ('mirror', 'method_fast_title', 'method_fast_desc'),
                ('smart', 'method_browser_title', 'method_browser_desc')):
            row = ttk.Frame(parent, style='Panel.TFrame')
            row.pack(fill='x', pady=(0, 10))
            ttk.Radiobutton(row, text=t(title_key), value=value, variable=app.mode_var,
                            command=on_pick).pack(anchor='w')
            ttk.Label(row, text=t(desc_key), style='Caption.TLabel',
                      wraplength=560).pack(anchor='w', padx=(22, 0))

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
        # 규칙 문법(+*/foo/* -*/bar/*)을 모르는 사람도 자연어로 목표만 말하면
        # AI가 규칙을 만들어 이 칸에 넣어준다. 입력칸 바로 옆에 둬야 "이 칸을
        # 채우는 도우미"라는 게 드러난다.
        rules_row = ttk.Frame(parent, style='Panel.TFrame')
        rules_row.pack(fill='x')
        ttk.Entry(rules_row, textvariable=app.custom_filters_var).pack(
            side='left', fill='x', expand=True, ipady=3)
        RoundedButton(rules_row, f"✨ {t('btn_ai_scope_rules')}",
                      command=lambda: app._open_scope_rules_dialog(self),
                      variant='ghost', page_bg=PANEL, padx=12, pady=7).pack(side='left', padx=(8, 0))
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
    # 얼마나 받을지 프리셋 - (키, 제목 문자열키, 설명 문자열키, 최대페이지, 깊이).
    # 대부분의 사람은 '페이지 수'와 '깊이'를 따로 정하고 싶은 게 아니라
    # "이 페이지만" 또는 "사이트 전체"처럼 말하고 싶어 한다.
    SMART_PRESETS = (
        ('page', 'preset_page_title', 'preset_page_desc', '1', '1'),
        ('light', 'preset_light_title', 'preset_light_desc', '50', '2'),
        ('full', 'preset_full_title', 'preset_full_desc', '500', '5'),
    )

    # 화면에 보일 이름 <-> Playwright 내부 값. 'networkidle' 같은 raw 값을
    # 그대로 보여주면 무슨 뜻인지 알 수 없어서 사람 말로 바꿔 보여준다.
    WAIT_UNTIL_OPTIONS = (
        ('networkidle', 'wait_label_networkidle'),
        ('load', 'wait_label_load'),
        ('domcontentloaded', 'wait_label_domcontentloaded'),
    )

    def _build_smart(self, parent):
        app = self.app

        # --- 1단계: 얼마나 받을지 (대부분 여기서 끝난다) ---
        ttk.Label(parent, text=t('label_smart_preset'), style='RowTitle.TLabel').pack(anchor='w')
        ttk.Label(parent, text=t('caption_smart_preset'), style='Caption.TLabel',
                  wraplength=580).pack(anchor='w', pady=(2, 8))

        current = next((key for key, _tk, _dk, pages, depth in self.SMART_PRESETS
                        if app.max_pages_var.get() == pages and app.follow_depth_var.get() == depth),
                       'custom')
        self._preset_var = tk.StringVar(value=current)

        for key, title_key, desc_key, pages, depth in self.SMART_PRESETS:
            row = ttk.Frame(parent, style='Panel.TFrame')
            row.pack(fill='x', pady=2)
            ttk.Radiobutton(row, text=t(title_key), value=key, variable=self._preset_var,
                            command=lambda p=pages, d=depth: _apply_preset(p, d)).pack(anchor='w')
            ttk.Label(row, text=t(desc_key), style='Caption.TLabel',
                      wraplength=560).pack(anchor='w', padx=(22, 0))

        ttk.Radiobutton(parent, text=t('preset_custom_title'), value='custom',
                        variable=self._preset_var,
                        command=lambda: _sync_advanced()).pack(anchor='w', pady=(2, 0))

        def _apply_preset(pages, depth):
            app.max_pages_var.set(pages)
            app.follow_depth_var.set(depth)
            _sync_advanced()

        # --- 2단계: 직접 설정 (고른 사람에게만 보인다) ---
        advanced = ttk.Frame(parent, style='Panel.TFrame')

        def _sync_advanced():
            if self._preset_var.get() == 'custom':
                advanced.pack(fill='x', pady=(10, 0))
            else:
                advanced.pack_forget()

        def spin_row(label_key, caption_key, variable, from_, to):
            ttk.Label(advanced, text=t(label_key), style='RowTitle.TLabel').pack(anchor='w', pady=(10, 0))
            ttk.Spinbox(advanced, from_=from_, to=to, textvariable=variable, width=10).pack(
                anchor='w', pady=(4, 0))
            ttk.Label(advanced, text=t(caption_key), style='Caption.TLabel',
                      wraplength=580).pack(anchor='w', pady=(2, 0))

        spin_row('label_max_pages', 'caption_max_pages', app.max_pages_var, 1, 5000)
        spin_row('label_follow_depth', 'caption_follow_depth', app.follow_depth_var, 1, 20)

        ttk.Label(advanced, text=t('label_wait_until'), style='RowTitle.TLabel').pack(anchor='w', pady=(14, 0))
        # 표시용 이름으로 고르고, 실제 값(app.wait_until_var)은 뒤에서 맞춰준다.
        wait_labels = [t(lk) for _v, lk in self.WAIT_UNTIL_OPTIONS]
        wait_display_var = tk.StringVar(value=next(
            (t(lk) for v, lk in self.WAIT_UNTIL_OPTIONS if v == app.wait_until_var.get()), wait_labels[0]))
        ttk.Combobox(advanced, textvariable=wait_display_var, state='readonly',
                     values=wait_labels).pack(fill='x', pady=(4, 0), ipady=2)
        wait_caption_var = tk.StringVar()

        def _sync_wait(*_a):
            value = next((v for v, lk in self.WAIT_UNTIL_OPTIONS if t(lk) == wait_display_var.get()),
                         'networkidle')
            app.wait_until_var.set(value)
            wait_caption_var.set(t(f'caption_wait_until_{value}'))
        wait_display_var.trace_add('write', _sync_wait)
        _sync_wait()
        ttk.Label(advanced, textvariable=wait_caption_var, style='Caption.TLabel',
                  wraplength=580).pack(anchor='w', pady=(2, 0))

        # 어디까지 따라갈지(도메인/폴더 범위) - 사이트 미러링의 '수집 범위' 다이얼로그와
        # 같은 변수를 쓴다.
        ttk.Label(advanced, text=t('label_domain_scope'), style='RowTitle.TLabel').pack(anchor='w', pady=(16, 0))
        ttk.Combobox(advanced, textvariable=app.domain_scope_var, state='readonly',
                     values=[label for _, label in app.domain_scope_options],
                     width=combo_width([l for _, l in app.domain_scope_options])).pack(
            fill='x', pady=(4, 0), ipady=2)
        ttk.Label(advanced, text=t('caption_domain_scope'), style='Caption.TLabel',
                  wraplength=580).pack(anchor='w', pady=(2, 0))

        ttk.Checkbutton(advanced, text=t('label_same_folder'),
                        variable=app.same_folder_var).pack(anchor='w', pady=(14, 0))
        ttk.Label(advanced, text=t('caption_same_folder'), style='Caption.TLabel',
                  wraplength=580).pack(anchor='w', pady=(2, 0))

        _sync_advanced()

        # 요청 사이 텀 - 차단당하지 않으려면 중요해서 프리셋과 무관하게 항상 보여준다.
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
