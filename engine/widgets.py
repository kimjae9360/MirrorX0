"""직접 그려서 만든 화면 부품들.

Tkinter/ttk에는 '둥근 모서리'라는 개념이 아예 없다. 그래서 세련된 모양이
필요한 것들은 전부 Canvas 위에 도형을 직접 그려서 흉내 낸다.
(둥근 사각형 = 꼭짓점을 여러 개 찍은 다각형 + smooth=True)

들어 있는 것:
    make_scrollable      내용이 길어지면 스크롤되는 영역을 만든다
    RoundedCard          둥근 흰 카드. 내용은 반드시 .body 안에 넣는다
    RoundedButton        둥근 버튼 (accent/danger/neutral/ghost 네 가지 모양)
    ToggleSwitch         켜기/끄기 알약 스위치
    SegmentedControl     '사이트 미러링 | 스마트 크롤링' 같은 2분할 선택기
    CircularStartButton  가운데 원형 시작 버튼 (테두리가 진행률에 따라 차오름)
    BrandHeader          맨 위 MirrorX0 로고 띠
    lerp_color 등        그라데이션/그림자를 흉내 내기 위한 색 계산 도우미

여기 있는 부품은 앱 로직을 전혀 모른다. 값을 받아 그리기만 한다.
"""
import tkinter as tk
from tkinter import ttk

from i18n import t
from theme import *  # noqa: F403  (색상/글자크기 상수)
from theme import FONTS


def display_width(text):
    """글자가 화면에서 차지하는 '칸 수'를 센다.
    한글·한자·일본어는 영문 알파벳 두 개만큼 넓으므로 2로 센다."""
    return sum(2 if ord(ch) > 0x1100 else 1 for ch in text)


def combo_width(values, extra=3, minimum=10, maximum=42):
    """드롭다운 폭을 '가장 긴 항목'에 맞춰 계산한다.

    ttk.Combobox의 width는 픽셀이 아니라 문자 수라서, 숫자를 손으로 박아두면
    언어를 바꿨을 때 잘린다. 실제로 영어에서 'Ignore and collect everything'(29칸)이
    width=16에 걸려 잘리는 문제가 있었다. 그래서 항목에서 계산해 쓴다."""
    longest = max((display_width(v) for v in values), default=minimum)
    return max(minimum, min(maximum, longest + extra))


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
                                 font=(FONTS['display'], 30, 'bold'))
        bounds = self.bbox(first)
        self.create_text(bounds[2], cy, text='X0', anchor='w', fill=ACCENT,
                         font=(FONTS['display'], 30, 'bold'))
        self.create_text(x2 - 28, cy, text=self.subtitle_text, anchor='e',
                         fill=FG_MUTED, font=(FONTS['ui'], TYPE_BODY))


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
                             font=(FONTS['ui'], TYPE_BODY, weight))


class CircularStartButton(tk.Canvas):
    """ExpressVPN의 원형 전원 버튼을 참고한 메인 동작 버튼.
    바깥 링이 다운로드 진행률에 따라 초록으로 차오르고, 안쪽 원은 오렌지
    그라데이션으로 채워진다. 창 크기에 맞춰 set_size()로 지름을 조절할 수 있다."""

    RING_WIDTH_RATIO = 0.075
    GLOW_RATIO = 0.17       # 캔버스 바깥쪽에서 글로우(빛번짐)가 차지하는 비율

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
            # LED처럼 또렷하게 빛나 보이도록 번짐을 진하게 준다.
            # 실행 중에는 한 단계 더 밝게 해서 '지금 돌아가는 중'이 눈에 띄게 한다.
            if self._running:
                peak = 0.95 if self._hover else 0.82
            else:
                peak = 0.78 if self._hover else 0.55
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
                             font=(FONTS['ui'], max(20, int(s * 0.20)), 'bold'))
            self.create_text(cx, cy + s * 0.145, text=t('btn_stop'), fill=CRITICAL,
                             font=(FONTS['ui'], max(11, int(s * 0.078)), 'bold'))
        else:
            glyph_color = FG_MUTED if not self._enabled else ON_ACCENT
            self.create_text(cx, cy - s * 0.055, text='⏻', fill=glyph_color,
                             font=(FONTS['ui'], max(20, int(s * 0.20))))
            self.create_text(cx, cy + s * 0.135, text=t('btn_start'), fill=glyph_color,
                             font=(FONTS['ui'], max(11, int(s * 0.075)), 'bold'))


class RoundedCard(tk.Frame):
    """카드처럼 보이는 둥근 모서리 컨테이너 (Windows 지오메트리 가이드의 8px
    규칙). Tkinter/ttk가 모서리 둥글리기를 기본 지원하지 않아서, Canvas에
    직접 둥근 사각형을 그리고 그 위에 실제 콘텐츠를 담을 프레임(.body)을
    얹는 방식으로 흉내 낸다 - make_scrollable()의 캔버스+임베드 프레임
    패턴과 같은 원리. 실제 콘텐츠는 반드시 .body 안에 넣어야 한다."""

    def __init__(self, parent, page_bg=None, card_bg=None, border=None, radius=14, padding=14, expand=False,
                 body_style='Panel.TFrame', inset=None, shadow=False):
        page_bg = page_bg if page_bg is not None else BG
        card_bg = card_bg if card_bg is not None else PANEL
        border = border if border is not None else BORDER
        super().__init__(parent, bg=page_bg)
        self.radius = radius
        self.shadow = shadow
        self.page_bg = page_bg
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
        if self.shadow:
            # 카드가 배경 위에 살짝 떠 있어 보이게 아주 옅은 그림자를 깐다.
            # 그림자로 새로 생긴 도형에만 태그를 단다 - 예전엔 'all'에 태그를
            # 덮어써서 본문 창까지 'card_bg'가 되었고, 다음 렌더링의
            # delete('card_bg')가 카드 내용을 지워 프로그램이 죽었다.
            before = set(self.canvas.find_all())
            draw_soft_shadow(self.canvas, 3, 2, w - 3, h - 5, self.radius,
                             self.page_bg, depth=4, spread=1.1)
            for item in self.canvas.find_all():
                if item not in before:
                    self.canvas.addtag_withtag('card_bg', item)
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
        self.font = font or (FONTS['ui'], TYPE_BODY, 'bold')
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
