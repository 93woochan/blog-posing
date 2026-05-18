"""Phase A 2단계 — 수집한 글을 Claude에 보내 스타일 가이드 + 대표 예시를 추출.

실행:
    python -m src.learn

전제:
    먼저 `python -m src.crawler`로 data/raw_posts/*.json 가 생성되어 있어야 함.

산출물:
    data/style_guide.md   ← 스타일 규칙 (도입부, 본문 구조, 어휘, 이모지, 마무리 등)
    data/exemplars.md     ← Claude가 고른 대표 글 3~5개 본문
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from anthropic import Anthropic

from src.config import (
    ANTHROPIC_API_KEY,
    EXEMPLARS_PATH,
    MODEL_SONNET,
    RAW_POSTS_DIR,
    STYLE_GUIDE_PATH,
)


SYSTEM_PROMPT = """\
당신은 한 블로거의 글쓰기 스타일을 분석해 다른 작성자(또는 AI)가 \
정확히 모방할 수 있도록 규칙으로 정리하는 전문가입니다.
규칙은 구체적이고 행동 가능해야 하며, 모호한 표현("자연스럽게", "적절히")은 피하세요.
가능한 한 실제 표현 예시를 인용해 보여주세요.
"""

USER_TEMPLATE = """\
아래는 한 블로거가 작성한 '맛집/카페' 카테고리 글 {n}편의 원문입니다.

각 글은 다음 형식으로 구분됩니다:
─── POST {{i}} ─────────────────────────
제목: ...
태그: ...
본문:
(본문 텍스트)
────────────────────────────────────────

수행할 작업:

1) **STYLE_GUIDE**: 이 블로거의 글쓰기 스타일을 다음 항목별로 추출하세요.
   각 항목은 행동 가능한 규칙 + 실제 예시 인용으로 구성합니다.
   - 도입부 패턴 (몇 문장, 무엇으로 시작하는지)
   - 본문 구조 (사진/문단 흐름의 전형적 순서)
   - 문장 길이와 어조 (존댓말/반말, 평균 문장 길이, 자주 쓰는 어미)
   - 사진 캡션 스타일
   - 메뉴/가격 표기 방식
   - 이모지 사용 (어떤 것을, 얼마나)
   - 자주 등장하는 어휘/표현 톱 10
   - 마무리 패턴 (재방문 의사, 평점 등)
   - 태그 작성 규칙 (개수, 형태)
   - 피해야 할 표현 (이 블로거가 절대 안 쓰는 톤)

2) **EXEMPLARS**: 위 글들 중 이 블로거의 스타일을 가장 잘 보여주는 \
대표 글 3~5편을 골라 그 본문을 그대로 인용하세요.
   각 글은 `## Exemplar N — 제목` 헤더와 함께 본문 전체를 포함합니다.

출력 형식 (정확히 이 마커를 사용):

<<<STYLE_GUIDE_START>>>
# 우찬 블로그 — 맛집/카페 스타일 가이드

## 도입부
- ...

## 본문 구조
- ...

(이하 모든 항목)
<<<STYLE_GUIDE_END>>>

<<<EXEMPLARS_START>>>
## Exemplar 1 — (제목)
(본문)

## Exemplar 2 — (제목)
(본문)

...
<<<EXEMPLARS_END>>>

────────── 원문 시작 ──────────

{posts}
"""


def load_posts() -> list[dict]:
    files = sorted(RAW_POSTS_DIR.glob("*.json"))
    posts: list[dict] = []
    for f in files:
        try:
            posts.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"⚠️  {f.name} 읽기 실패: {e}")
    return posts


def format_posts(posts: list[dict]) -> str:
    chunks: list[str] = []
    for i, p in enumerate(posts, 1):
        chunks.append(
            f"─── POST {i} ─────────────────────────\n"
            f"제목: {p.get('title', '')}\n"
            f"태그: {', '.join(p.get('tags', []))}\n"
            f"본문:\n{p.get('body', '').strip()}\n"
        )
    return "\n".join(chunks)


def extract_section(text: str, start_marker: str, end_marker: str) -> str:
    """마커 사이의 내용을 추출. 못 찾으면 빈 문자열."""
    try:
        s = text.index(start_marker) + len(start_marker)
        e = text.index(end_marker, s)
        return text[s:e].strip()
    except ValueError:
        return ""


def main() -> int:
    if not ANTHROPIC_API_KEY:
        print("❌ ANTHROPIC_API_KEY 가 .env 에 설정되어 있지 않습니다.")
        return 1

    posts = load_posts()
    if not posts:
        print(f"❌ {RAW_POSTS_DIR} 에 글이 없습니다. 먼저 `python -m src.crawler` 를 실행하세요.")
        return 1

    print(f"[learn] 글 {len(posts)}편 로드 완료. Claude에 분석 요청 중...")

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    user_msg = USER_TEMPLATE.format(n=len(posts), posts=format_posts(posts))

    response = client.messages.create(
        model=MODEL_SONNET,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    text = "".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )

    style_guide = extract_section(text, "<<<STYLE_GUIDE_START>>>", "<<<STYLE_GUIDE_END>>>")
    exemplars = extract_section(text, "<<<EXEMPLARS_START>>>", "<<<EXEMPLARS_END>>>")

    if not style_guide or not exemplars:
        # 마커가 누락된 경우 원본을 디버그용으로 저장
        Path("data/_raw_learn_output.txt").write_text(text, encoding="utf-8")
        print("⚠️  응답에서 마커를 찾지 못했습니다. data/_raw_learn_output.txt 확인.")
        return 1

    STYLE_GUIDE_PATH.write_text(style_guide + "\n", encoding="utf-8")
    EXEMPLARS_PATH.write_text(exemplars + "\n", encoding="utf-8")

    print(f"✓ 저장: {STYLE_GUIDE_PATH}")
    print(f"✓ 저장: {EXEMPLARS_PATH}")
    print()
    print("두 파일을 한 번 읽어보시고, 어색하거나 빠진 규칙이 있으면 직접 수정하세요.")
    print("Phase B(포스팅 파이프라인)는 이 두 파일을 그대로 참조합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
