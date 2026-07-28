# MirrorX0

웹사이트를 통째로 받아 오프라인에서 그대로 열어볼 수 있게 만드는 윈도우 데스크톱 앱입니다.
검증된 HTTrack 엔진 위에, 실제 브라우저로 렌더링하는 **스마트 크롤링**과
**AI 기능**을 얹었습니다.

## 두 가지 수집 방식

| | 사이트 미러링 | 스마트 크롤링 |
|---|---|---|
| 엔진 | HTTrack | Playwright (실제 Chrome) |
| 잘하는 것 | 사이트 전체를 빠르고 빠짐없이 | 자바스크립트로 그려지는 화면 |
| 결과물 | 링크까지 치환된 완전한 오프라인 사본 | 렌더링된 HTML |
| 속도 | 빠름 (다중 연결) | 느림 (페이지마다 브라우저) |

서로 약점을 메우는 관계라, 정적 사이트는 미러링이 유리하고
React/Vue 같은 SPA는 스마트 크롤링이 필요합니다.

## AI 기능

- **다운로드 범위 규칙 제안** — "레시피만 받고 장바구니는 빼줘" 같은 문장을
  HTTrack 필터 규칙으로 바꿔줍니다. 사이트 크기와 무관하게 API 호출 1회만 씁니다.
- **데이터 추출** — 받아온 페이지에서 원하는 항목만 뽑아 CSV/JSON/엑셀로 저장합니다.
  페이지마다 같은 컬럼이 나오도록 스키마를 강제합니다.
- Anthropic / OpenAI / Google Gemini 중 골라 쓸 수 있고, **API 키는 사용자 본인 것**을
  이 컴퓨터에만 저장합니다.

## 설치

```bash
python -m venv engine\venv
engine\venv\Scripts\pip install -r requirements.txt
engine\venv\Scripts\playwright install chromium   # 스마트 크롤링을 쓸 때만
```

## 실행

```bash
engine\venv\Scripts\pythonw engine\main.py
```

예약 작업이 호출하는 헤드리스 실행:

```bash
engine\venv\Scripts\python engine\main.py --job <작업ID>
```

## 폴더 구조

```
engine/
  main.py            앱 진입점, 화면 조립, HTTrack 실행/진행률 처리
  smart_crawl.py     Playwright 기반 스마트 크롤링
  ai_extract.py      AI 데이터 추출 (3개 프로바이더 공통 인터페이스)
  ai_scope.py        AI 다운로드 범위 규칙 제안
  jobs.py            예약 작업 저장/불러오기
  scheduler_win.py   Windows 작업 스케줄러 등록 (앱이 꺼져 있어도 실행)
  preview.py         완료된 사이트의 썸네일 캡처
  httrack/           HTTrack 엔진 (GPLv3, THIRD-PARTY-NOTICES.md 참고)
  venv/              가상환경 (git에 포함하지 않음)
```

설정과 기록은 코드 폴더가 아니라 `%APPDATA%\MirrorX\`에 저장됩니다
(`settings.json`, `projects.json`, `jobs.json`).

## 라이선스

MirrorX0가 함께 배포하는 HTTrack은 **GPLv3**입니다.
의무 이행 방법과 소스 위치는 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)에 정리해 두었습니다.
