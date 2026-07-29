"""색상 팔레트, 폰트, 글자 크기 - 화면의 '보이는 값'을 한곳에 모아둔 곳.

색을 바꾸고 싶으면 여기만 고치면 앱 전체에 반영된다.

폰트를 왜 딕셔너리(FONTS)로 두는가:
    resolve_fonts()는 앱이 켜진 뒤에야(설치된 폰트 목록을 조회할 수 있게 된 뒤에야)
    실제 폰트 이름을 확정한다. 이걸 만약 FONT_UI 같은 '변수 이름'으로 두면,
    다른 파일에서 `from theme import FONT_UI` 로 가져가는 순간 그 시점의 값이
    복사돼 버려서 나중에 바뀐 값이 반영되지 않는다.
    딕셔너리는 참조를 공유하므로 FONTS['ui'] 는 항상 최신 값을 읽는다.
    (파일을 쪼갤 때 이 부분에서 실제로 문제가 났던 적이 있어 이렇게 바꿨다.)

사용법:
    from theme import BG, FG, TYPE_BODY, FONTS
    tk.Label(parent, bg=BG, fg=FG, font=(FONTS['ui'], TYPE_BODY))
"""

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

FONTS = {
    'ui': 'Malgun Gothic',                    # 본문 (resolve_fonts가 더 나은 것으로 교체)
    'display': 'Segoe UI Variable Display',   # 로고/큰 숫자
    'mono': 'Consolas',                       # 로그 창
}


def resolve_fonts():
    """설치된 폰트 중 가장 보기 좋은 것을 골라 전역 폰트 이름을 확정한다.
    families()는 Tk 루트가 있어야 조회되므로 앱 시작 시점에 한 번 호출한다.
    본문용은 한글/영문을 한 벌로 예쁘게 처리하는 Noto Sans KR을 우선하고,
    로고처럼 영문만 쓰는 곳은 Segoe UI Variable Display를 우선한다."""
    import tkinter.font as tkfont
    try:
        available = set(tkfont.families())
    except Exception:
        return

    def pick(candidates, fallback):
        return next((name for name in candidates if name in available), fallback)

    FONTS['ui'] = pick(['Noto Sans KR', 'Segoe UI Variable Text', 'Segoe UI'], FONTS['ui'])
    FONTS['display'] = pick(['Segoe UI Variable Display', 'Segoe UI', 'Noto Sans KR'], FONTS['ui'])
    FONTS['mono'] = pick(['Cascadia Mono', 'Consolas'], FONTS['mono'])

# Windows 11 타입 램프(Segoe UI Variable 기준 실측값) - 이 앱 전역에서 이 크기만 사용한다.
# 한 단계씩만 차이 나는 하나의 스케일로 통일한다. 화면 어디서든 이 상수만 쓰고
# 숫자를 직접 적지 않아야 크기 밸런스가 흐트러지지 않는다.
# 한글은 같은 pt에서도 라틴 문자보다 작아 보여서, 캡션을 11 -> 12로 올렸다.
# (11px 한글 설명은 실제로 읽기 부담스럽다는 피드백)
TYPE_CAPTION = 12       # 캡션/보조 설명
TYPE_BODY = 14          # 본문 기본 (라벨, 버튼)
TYPE_INPUT = 15         # 입력창/드롭다운 - 실제로 타이핑·선택하는 곳이라 한 단계 크게
TYPE_BODY_LARGE = 17    # 강조된 본문 (지표 값 등)
TYPE_SUBTITLE = 19      # 패널/다이얼로그 제목
TYPE_TITLE = 26         # 화면 최상위 제목

