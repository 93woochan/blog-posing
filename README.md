# naver-autopost

특정 블로그의 맛집/카페 카테고리 글 스타일을 1회 학습하고,
이후 사진 폴더 + 메모만 넣으면 그 스타일대로 본문을 자동 생성해 네이버 블로그에 포스팅하는 파이프라인.

---

## 전체 흐름

```
Phase A (최초 1회)           Phase B (매번)
─────────────────────        ──────────────────────────────────────────
학습 대상 블로그 크롤링  →   photos/날짜-가게명/  폴더 만들기
      ↓                           ↓  (사진 + info.txt)
 스타일 가이드 생성       →   python -m src.post (본문 JSON 생성)
                                   ↓
                           python -m src.publisher (브라우저 자동 포스팅)
                                   ↓
                           임시저장 → 브라우저에서 태그/발행 직접 처리
```

---

## 환경

- Windows 11
- Python 3.11 이상 (시스템 PATH에 등록된 것 사용 — 가상환경 비권장, 아래 참고)
- Anthropic API 키 ([console.anthropic.com](https://console.anthropic.com/)에서 발급)

> **가상환경(.venv) 주의**: 이 프로젝트 폴더 경로가 260자 근처면  
> `.venv\Scripts\python.exe`가 MAX_PATH를 초과해 `playwright`, `anthropic` 설치가 실패합니다.  
> 그냥 시스템 Python(`python`)을 직접 사용하세요.

---

## 초기 셋업 (Windows 11, PowerShell)

```powershell
# 1. 프로젝트 폴더로 이동
cd "C:\경로\naver-autopost"

# 2. 라이브러리 설치 (시스템 Python 사용)
pip install -r requirements.txt

# 3. Playwright 브라우저 다운로드 (Chromium, 약 200MB)
playwright install chromium

# 4. .env 파일 생성
copy .env.example .env
notepad .env   # 아래 항목 채우기
```

`.env` 필수 항목:
```
ANTHROPIC_API_KEY=sk-ant-...   # Anthropic 콘솔에서 발급
NAVER_ID=내아이디              # 네이버 로그인 ID
NAVER_PW=내비밀번호            # 네이버 비밀번호
BLOG_ID=내블로그ID             # 포스팅할 내 블로그 ID (URL의 punx2- 같은 부분)
CATEGORY_NAME=맛집/카페        # 학습할/포스팅할 카테고리명 (블로그에 표시된 그대로)
NUM_POSTS=20                   # Phase A에서 수집할 글 개수
```

---

## Phase A — 스타일 학습 (최초 1회)

```powershell
# 1단계: 학습 대상 블로그 글 수집
python -m src.crawler

# 2단계: 수집한 글로 스타일 가이드 생성
python -m src.learn
```

완료 후 `data\style_guide.md`, `data\exemplars.md` 생성.  
내용을 직접 열어 확인하고, 어색하면 수정해도 됩니다.

---

## Phase B — 실제 포스팅

### 1. 사진 폴더 준비

```
photos/
└── 2026-05-17 보어드앤헝그리 성수/   ← "YYYY-MM-DD 가게명" 형식
    ├── KakaoTalk_20260517_....jpg     ← 사진들
    ├── KakaoTalk_20260517_...._01.jpg
    └── info.txt                       ← 장소/메뉴/한줄평 메모
```

`info.txt` 형식은 `info_template.txt` 참고. 채울수록 글 품질이 높아집니다.

### 2. 본문 JSON 생성

```powershell
python -m src.post "photos\2026-05-17 보어드앤헝그리 성수"
```

`generated_post.json`과 `generated_post.md`(미리보기)가 폴더 안에 생성됩니다.  
`generated_post.md`를 열어서 내용 확인 후 진행하세요.

### 3. 네이버 자동 포스팅

```powershell
python -m src.publisher "photos\2026-05-17 보어드앤헝그리 성수"
```

- Chromium 창이 열리고 자동으로 로그인 → 글쓰기 페이지 진입
- 제목 입력 → 텍스트/사진 교차 삽입 (사진은 OS 창 없이 자동 업로드)
- 임시저장 후 "브라우저를 확인 후 Enter" 대기

**브라우저에서 직접 해야 하는 것:**
1. 카테고리 선택
2. 태그 입력 (자동 입력 미지원 — `generated_post.json`의 `"tags"` 참고)
3. 발행 버튼 클릭

완료 후 콘솔에서 Enter → 브라우저 닫힘.

---

## 폴더 구조

```
naver-autopost/
├── README.md                  ← 이 파일
├── HOWTO.md                   ← 단계별 상세 가이드 (막히면 여기)
├── requirements.txt
├── .env                       ← API 키, 블로그 ID 등 (git 제외)
├── .env.example               ← .env 템플릿
├── info_template.txt          ← photos/폴더/info.txt 작성 예시
├── data/
│   ├── raw_posts/             ← Phase A 크롤링 결과 (JSON)
│   ├── style_guide.md         ← Phase A 산출물: 스타일 규칙
│   ├── exemplars.md           ← Phase A 산출물: 대표 예시 글
│   └── auth_state.json        ← 네이버 세션 (최초 로그인 후 자동 생성)
├── src/
│   ├── config.py              ← .env 값 로드, 경로 상수
│   ├── crawler.py             ← Phase A: 블로그 글 수집
│   ├── learn.py               ← Phase A: 스타일 가이드 생성
│   ├── post.py                ← Phase B: 본문 JSON 생성 (진입점)
│   ├── publisher.py           ← Phase B: Playwright 자동 포스팅
│   ├── debug_editor.py        ← 진단: SE4 에디터 DOM 구조 분석
│   └── debug_image_panel.py   ← 진단: 이미지 업로드 패널 구조 분석
└── photos/
    └── YYYY-MM-DD 가게명/
        ├── *.jpg
        ├── info.txt
        ├── generated_post.json   ← post.py 출력
        └── generated_post.md     ← post.py 출력 (미리보기)
```

---

## 알려진 제한사항

| 항목 | 상태 |
|------|------|
| 사진 자동 업로드 | 정상 동작 (OS 창 미표시) |
| 텍스트/사진 교차 삽입 | 정상 동작 |
| 임시저장 자동 클릭 | 대부분 정상 (실패 시 브라우저에서 직접) |
| 태그 자동 입력 | 미지원 — SE4 발행 패널 내부에 위치, 수동 입력 필요 |
| 카테고리 자동 선택 | 부분 지원 — 스킨마다 다를 수 있음 |
| 2FA / 캡차 로그인 | 미지원 — 최초 1회 직접 로그인 후 세션 재사용 |

---

## 진행 상황

- [x] Phase A: 크롤러
- [x] Phase A: 스타일 가이드 생성기
- [x] Phase B: 사진 분석 + 본문 생성 (`post.py`)
- [x] Phase B: Playwright 자동 포스팅 (`publisher.py`)
  - [x] 세션 로그인 재사용
  - [x] SE4 제목 입력 (클립보드 붙여넣기)
  - [x] 텍스트 블록 입력 (클립보드 붙여넣기)
  - [x] 사진 업로드 (file chooser intercept, OS 창 없음)
  - [x] 임시저장
  - [ ] 태그 자동 입력 (미구현)
