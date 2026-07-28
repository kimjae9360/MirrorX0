# 제3자 소프트웨어 고지 (Third-Party Notices)

MirrorX0는 아래 오픈소스 소프트웨어를 함께 배포하거나 사용합니다.

---

## HTTrack Website Copier

MirrorX0의 **사이트 미러링** 기능은 HTTrack 엔진이 담당합니다.
`engine/httrack/httrack.exe`를 별도 프로세스로 실행하는 방식으로 사용합니다.

| 항목 | 내용 |
|---|---|
| 저작권 | Copyright (C) 1998-2017 Xavier Roche and other contributors |
| 라이선스 | **GNU General Public License v3 (GPLv3)** |
| 공식 사이트 | https://www.httrack.com/ |
| 소스코드 | https://github.com/xroche/httrack |
| 동봉된 라이선스 전문 | `engine/httrack/copying` |
| 동봉된 소스코드 | `engine/httrack/src/`, `engine/httrack/src_win/` |

### GPLv3 의무 이행 방법

GPLv3는 "출처만 밝히면 되는" 허용형 라이선스가 아니라 **카피레프트** 라이선스입니다.
HTTrack 바이너리를 함께 배포할 때는 아래를 지켜야 합니다. MirrorX0는 다음과 같이 이행합니다.

1. **라이선스 전문 동봉** — `engine/httrack/copying`에 GPLv3 전문을 그대로 포함합니다.
2. **대응 소스코드 제공** — `engine/httrack/src/`, `engine/httrack/src_win/`에 배포되는
   바이너리에 대응하는 소스를 함께 포함합니다. 원본은 위 GitHub 주소에서도 받을 수 있습니다.
3. **수정 사실 명시** — MirrorX0는 HTTrack의 소스를 **수정하지 않았습니다.**
   공식 배포판 그대로를 명령행 인자만 조합해 실행합니다.

### MirrorX0 자체 코드와의 관계

MirrorX0는 HTTrack을 라이브러리로 링크하지 않고 **별도 프로세스로 실행**합니다
(`subprocess`로 `httrack.exe`를 호출하고 표준 출력을 읽습니다).
이런 형태는 일반적으로 서로 독립된 프로그램으로 보아, MirrorX0 자체 코드까지
GPL이 강제되지는 않는 것으로 해석됩니다. 다만 함께 배포하는 `httrack.exe`에는
위 의무가 그대로 적용됩니다.

> 이 문서는 법률 자문이 아닙니다. 상업적 배포나 재배포를 계획한다면 전문가 확인을 권합니다.

---

## 그 밖에 사용하는 패키지

아래는 함께 배포하지 않고, 사용자가 `requirements.txt`로 직접 설치하는 의존성입니다.

| 패키지 | 용도 | 라이선스 |
|---|---|---|
| Playwright | 스마트 크롤링 (실제 브라우저 렌더링) | Apache-2.0 |
| BeautifulSoup4 | HTML 파싱 | MIT |
| lxml | HTML 파서 백엔드 | BSD |
| anthropic / openai / google-genai | AI 기능 (사용자가 고른 것만) | MIT / Apache-2.0 |
| openpyxl | AI 추출 결과 엑셀 저장 | MIT |
| browser-cookie3 | 로컬 브라우저 로그인 재사용 | LGPL-3.0 |
| PyInstaller | exe 빌드 (실행에는 불필요) | GPL-2.0 with exception |
