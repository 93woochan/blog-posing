# 단계별 실행 가이드

> 위에서부터 차례대로 따라하세요. 각 단계마다 **"이게 보이면 성공"** 표시가 있습니다.

---

## 목차

- [셋업 (최초 1회)](#셋업-최초-1회)
- [Phase A — 스타일 학습](#phase-a--스타일-학습-최초-1회)
- [Phase B — 포스팅](#phase-b--포스팅-매번)
- [디버깅 도구](#디버깅-도구)
- [자주 발생하는 에러](#자주-발생하는-에러)

---

## 셋업 (최초 1회)

### STEP 0. Python 확인

PowerShell을 열고 (`시작` → `powershell` → Enter):

```powershell
python --version
```

**성공:** `Python 3.11.x` 이상이 나오면 OK.

**실패 (Microsoft Store가 열리거나 "찾을 수 없음"):**
1. https://www.python.org/downloads/ 에서 Python 3.11+ 다운로드
2. 설치 시 **"Add python.exe to PATH"** 반드시 체크
3. PowerShell을 새로 열고 다시 확인

> **가상환경(.venv) 비권장:** 이 프로젝트의 폴더 경로가 길어서 `.venv\Scripts\python.exe`가  
> Windows MAX_PATH(260자)를 초과해 라이브러리 설치가 실패합니다.  
> 시스템 Python을 그대로 사용하세요.

---

### STEP 1. 프로젝트 폴더로 이동

```powershell
cd "C:\Users\VICTUS16\AppData\Roaming\Claude\local-agent-mode-sessions\6e40dc28-09ea-4f0d-b7b3-1d8fccba30bc\1543c426-a859-4c3c-918f-6207d3641c81\local_f9f2be8b-5f6d-4711-8e46-160ec4fb64df\outputs\naver-autopost"
```

```powershell
dir
```

**성공:** `README.md`, `requirements.txt`, `src` 폴더 등이 보임.

> 매번 이 긴 경로가 불편하면 폴더를 `C:\Projects\naver-autopost` 같은 짧은 경로로 옮기세요.

---

### STEP 2. 라이브러리 설치

```powershell
pip install -r requirements.txt
```

**성공:** 마지막에 `Successfully installed ...` 가 나옴. 1~3분 걸림.

---

### STEP 3. Playwright 브라우저 다운로드

```powershell
playwright install chromium
```

Chromium(약 200MB) 다운로드. 1~2분 걸림.

**성공:** `Chromium ... downloaded` 메시지.

---

### STEP 4. .env 파일 설정

```powershell
copy .env.example .env
notepad .env
```

아래 항목을 실제 값으로 채우고 저장(Ctrl+S) 후 닫기:

```
ANTHROPIC_API_KEY=sk-ant-...      ← https://console.anthropic.com 에서 발급
NAVER_ID=내아이디
NAVER_PW=내비밀번호
BLOG_ID=내블로그ID                ← 예: punx2-  (https://blog.naver.com/punx2- 의 punx2- 부분)
CATEGORY_NAME=맛집/카페           ← 학습 대상 블로그의 카테고리명 (정확히 일치해야 함)
NUM_POSTS=20
```

**확인:**
```powershell
type .env
```
값이 제대로 들어갔는지 확인.

> **BLOG_ID 찾는 법:** 네이버에서 내 블로그 주소가 `https://blog.naver.com/punx2-` 이면  
> `BLOG_ID=punx2-` 입니다. 학습 대상 블로그(bbtn96 등)가 아닌 **내 블로그** ID를 입력하세요.

---

## Phase A — 스타일 학습 (최초 1회)

### STEP 5. 블로그 글 수집

```powershell
python -m src.crawler
```

**이때 일어나는 일:**
1. Chromium 창이 자동으로 열림
2. `.env`의 `BLOG_ID` 블로그(학습 대상)에 접속
3. `CATEGORY_NAME` 카테고리에서 `NUM_POSTS`개 글 수집
4. `data\raw_posts\` 에 JSON으로 저장

**성공 예시:**
```
[crawler] 블로그: https://blog.naver.com/bbtn96
[crawler] ✓ 목록 20개 확보.
[1/20] 성수 수제버거 맛집 ...
...
[20/20] 망원동 카페 ...
✓ 20개 글을 data/raw_posts/ 에 저장했습니다.
```

---

### STEP 6. 스타일 가이드 생성

```powershell
python -m src.learn
```

Claude가 수집한 글들을 분석해서 두 파일을 만듭니다:
- `data\style_guide.md` — 글쓰기 규칙, 말투, 구조
- `data\exemplars.md` — 대표 예시 글 3~5개

30초~1분 걸립니다.

**성공:**
```
[learn] 글 20편 로드 완료. Claude에 분석 요청 중...
✓ 저장: data\style_guide.md
✓ 저장: data\exemplars.md
```

완료 후 두 파일을 메모장으로 열어 확인하세요. 어색한 부분은 직접 수정해도 됩니다.

```powershell
notepad data\style_guide.md
notepad data\exemplars.md
```

---

## Phase B — 포스팅 (매번)

### STEP 7. 사진 폴더 + info.txt 준비

`photos\` 아래에 `YYYY-MM-DD 가게명` 형식으로 폴더를 만들고 사진을 넣습니다:

```
photos\
└── 2026-05-20 블루보틀성수\
    ├── KakaoTalk_20260520_....jpg
    ├── KakaoTalk_20260520_...._01.jpg
    └── info.txt
```

`info.txt`는 `info_template.txt`를 복사해서 채웁니다. 채울수록 본문 품질이 높아집니다:

```
장소: 블루보틀커피 성수점
위치: 서울 성동구 연무장길 8-12
방문일: 2026-05-20
메뉴: 싱글오리진 드립 8,000원, 라떼 7,500원
한줄평: 커피 퀄리티는 최고, 웨이팅이 걸림
...
```

---

### STEP 8. 본문 JSON 생성

```powershell
python -m src.post "photos\2026-05-20 블루보틀성수"
```

**성공 시 생성 파일:**
- `photos\2026-05-20 블루보틀성수\generated_post.json` — publisher 입력 데이터
- `photos\2026-05-20 블루보틀성수\generated_post.md` — 사람이 읽기 좋은 미리보기

```powershell
notepad "photos\2026-05-20 블루보틀성수\generated_post.md"
```

내용이 마음에 들면 다음 단계로. 수정하고 싶으면 `generated_post.json`을 직접 편집해도 됩니다.

---

### STEP 9. 네이버 자동 포스팅

```powershell
python -m src.publisher "photos\2026-05-20 블루보틀성수"
```

**자동으로 처리되는 것:**
- 네이버 로그인 (저장된 세션 재사용, 세션 만료 시 자동 로그인 시도)
- 글쓰기 페이지 진입
- 제목 + 본문 텍스트 입력 (클립보드 붙여넣기 방식 — 빠름)
- 사진 업로드 (OS 파일 탐색기 창 없이 자동 처리)
- 임시저장 시도

**자동 완료 후 브라우저에서 직접 해야 하는 것:**
1. **카테고리** 선택 (우측 패널)
2. **태그** 입력 — `generated_post.json`의 `"tags"` 배열 참고
3. **발행** 버튼 클릭

모두 완료했으면 콘솔로 돌아와 Enter → 브라우저 닫힘.

**성공 예시:**
```
[publisher] ✓ 저장된 세션으로 자동 로그인되어 있습니다.
[publisher] [1/24] 텍스트 단락 입력
[publisher]   📷 사진 업로드: KakaoTalk_20260520_....jpg
[publisher]     ✓ 파일 선택 완료 (file chooser)
...
[publisher] [24/24] 텍스트 단락 입력
[publisher] 임시저장 시도...
[publisher] ✓ 임시저장 완료. 네이버 앱/PC에서 검토 후 직접 발행해주세요.
브라우저를 확인 후 Enter 를 눌러 종료하세요...
```

---

## 디버깅 도구

문제가 생겼을 때 쓰는 진단 스크립트들입니다.

### SE4 에디터 DOM 구조 분석

```powershell
python -m src.debug_editor
```

글쓰기 페이지의 버튼/input/프레임 구조를 `debug_editor_output.txt`와 `debug_editor_screenshot.png`로 저장합니다. 셀렉터가 바뀌었을 때 확인용.

### 이미지 업로드 패널 분석

```powershell
python -m src.debug_image_panel
```

사진 버튼 클릭 후 패널의 DOM 구조를 `debug_image_panel.txt`와 `debug_image_panel.png`로 저장합니다. 이미지 업로드가 안 될 때 확인용.

---

## 자주 발생하는 에러

### 🔴 사진이 모두 "파일 없음"으로 건너뜀

**원인:** `photos\` 경로가 너무 길어 Windows MAX_PATH(260자) 초과.

**해결:**
1. 프로젝트 폴더를 `C:\Projects\naver-autopost` 같은 짧은 경로로 이동
2. 이동 후 `.env` 경로가 맞는지 확인하고 다시 실행

---

### 🔴 "세션 만료 — data/auth_state.json 삭제 후 재실행" 오류

**원인:** 저장된 네이버 로그인 세션이 만료됨.

**해결:**
```powershell
del data\auth_state.json
python -m src.publisher "photos\폴더명"
```
브라우저가 열리면 직접 로그인 → Enter → 세션 저장.

---

### 🔴 "이미지 툴바 버튼 없음" 또는 사진 업로드 안 됨

**원인:** 네이버 SE4 에디터 업데이트로 셀렉터가 바뀌었을 가능성.

**진단:**
```powershell
python -m src.debug_image_panel
```
`debug_image_panel.txt`의 버튼 목록에서 `data-name='image'` 버튼을 찾아 클래스명 확인. `src\publisher.py`의 `insert_image` 함수 내 `img_btn_sels` 리스트에 추가.

---

### 🔴 "카테고리 '맛집/카페'를 찾지 못했습니다" (크롤러)

**원인:** `.env`의 `CATEGORY_NAME`이 블로그 실제 카테고리명과 다름.

**해결:**
1. 브라우저로 학습 대상 블로그 직접 접속
2. 좌측 카테고리 영역에서 정확한 표기 확인 (공백, 슬래시 방향 포함)
3. `.env`의 `CATEGORY_NAME`을 그 문자열로 수정

---

### 🔴 "ANTHROPIC_API_KEY 가 설정되어 있지 않습니다"

```powershell
type .env
```
`ANTHROPIC_API_KEY=sk-ant-...` 가 있는지 확인. 없으면 STEP 4로 돌아가기.

---

### 🔴 ModuleNotFoundError: No module named 'playwright'

```powershell
pip install -r requirements.txt
```

---

### 🔴 Anthropic API `401 Unauthorized`

API 키 오류. https://console.anthropic.com → API Keys 에서 재확인. `sk-ant-`로 시작해야 함.

### 🔴 Anthropic API `429` 또는 `insufficient_credit`

크레딧 부족. https://console.anthropic.com/settings/billing 에서 충전.

---

## 막혔을 때 알려주실 것

1. PowerShell의 **빨간 글씨 전부** (스크린샷 또는 텍스트 복사)
2. **마지막에 실행한 명령** 한 줄
3. `debug_editor_screenshot.png` 또는 `debug_image_panel.png` (있으면)
4. `photos\폴더명\` 안의 파일 목록

---

## 빠른 참조

```powershell
# 셋업 (최초 1회)
pip install -r requirements.txt
playwright install chromium
copy .env.example .env  # 키/ID 채우기

# Phase A (최초 1회)
python -m src.crawler          # 글 수집
python -m src.learn            # 스타일 가이드 생성

# Phase B (매 포스팅)
python -m src.post    "photos\YYYY-MM-DD 가게명"    # 본문 생성
python -m src.publisher "photos\YYYY-MM-DD 가게명"  # 자동 포스팅
# → 브라우저에서 카테고리/태그 설정 후 발행
```
