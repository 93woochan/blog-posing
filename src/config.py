"""프로젝트 전역 설정. .env 파일에서 값을 읽어옵니다."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# 프로젝트 루트 — frozen exe(PyInstaller)면 exe 위치, 아니면 소스 루트
if getattr(sys, "frozen", False):
    ROOT_DIR = Path(sys.executable).parent
else:
    ROOT_DIR = Path(__file__).resolve().parent.parent

# .env 로드
load_dotenv(ROOT_DIR / ".env")

# ─── 사용자 설정 ────────────────────────────────────────────
BLOG_ID: str = os.getenv("BLOG_ID", "bbtn96")
CATEGORY_NAME: str = os.getenv("CATEGORY_NAME", "맛집/카페")
NAVER_ID: str = os.getenv("NAVER_ID", "")
NAVER_PW: str = os.getenv("NAVER_PW", "")
# CATEGORY_NO 가 지정되면 텍스트 검색 대신 URL로 직접 진입 (가장 안정적)
_cat_no = os.getenv("CATEGORY_NO", "").strip()
CATEGORY_NO: int | None = int(_cat_no) if _cat_no.isdigit() else None
NUM_POSTS: int = int(os.getenv("NUM_POSTS", "10"))
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# ─── 경로 ───────────────────────────────────────────────────
DATA_DIR = ROOT_DIR / "data"
RAW_POSTS_DIR = DATA_DIR / "raw_posts"
STYLE_GUIDE_PATH = DATA_DIR / "style_guide.md"
EXEMPLARS_PATH = DATA_DIR / "exemplars.md"
AUTH_STATE_PATH = DATA_DIR / "auth_state.json"
PHOTOS_DIR = ROOT_DIR / "photos"

# 폴더 자동 생성
for d in (DATA_DIR, RAW_POSTS_DIR, PHOTOS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ─── Gemini 모델 ────────────────────────────────────────────
MODEL_GEMINI = "gemini-2.5-flash"
