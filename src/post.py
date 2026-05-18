"""Phase B — 사진 폴더 + 메모로부터 Gemini가 블로그 본문을 생성.

사용법:
    # 내돈내산 모드 (기본값)
    python -m src.post ./photos/2026-05-15-cafexyz

    # 협찬 모드
    python -m src.post ./photos/2026-05-15-cafexyz --mode sponsored

폴더 구조 예:
    photos/2026-05-15-cafexyz/
    ├── info.txt          ← 가게 정보 메모 (필수)
    ├── IMG_001.jpg
    ├── IMG_002.jpg
    └── ...

info.txt 형식 예:
    카페 이름: 블루보틀 성수
    위치: 서울 성동구 성수동
    방문일: 2026-05-15
    메뉴: 아메리카노 6500원, 크루아상 5500원
    한줄평: 조용한 분위기, 재방문 의사 있음
    동행: 친구 1명

동작:
    1. info.txt + 사진을 Gemini에 전송
    2. style_guide.md + exemplars.md 를 참조 프롬프트로 사용
    3. Gemini가 본문 JSON 생성 → generated_post.json 으로 저장
    4. 이후 publisher.py 로 네이버에 자동 포스팅
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from google import genai
from PIL import Image

from src.config import (
    EXEMPLARS_PATH,
    GEMINI_API_KEY,
    MODEL_GEMINI,
    STYLE_GUIDE_PATH,
)


VALID_MODES = ("self_paid", "sponsored")
INFO_FILENAME = "info.txt"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}  # HEIC 제외 (PIL 미지원)


def parse_info(info_path: Path) -> dict:
    info: dict[str, str] = {}
    if not info_path.exists():
        return info
    for line in info_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            info[k.strip()] = v.strip()
        elif "：" in line:
            k, v = line.split("：", 1)
            info[k.strip()] = v.strip()
    return info


def list_photos(folder: Path) -> list[str]:
    photos = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )
    return [p.name for p in photos]


def generate_post(folder: Path, mode: str) -> dict:
    """Gemini API로 사진 + info.txt → 블로그 본문 JSON 생성."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY 가 .env 에 설정되어 있지 않습니다.")

    info = parse_info(folder / INFO_FILENAME)
    photos = list_photos(folder)

    if not photos:
        raise FileNotFoundError(f"폴더에 사진이 없습니다: {folder}")
    if not STYLE_GUIDE_PATH.exists():
        raise FileNotFoundError(
            f"style_guide.md 가 없습니다. 먼저 Phase A(크롤링 + 학습)를 완료하세요."
        )
    if not EXEMPLARS_PATH.exists():
        raise FileNotFoundError(f"exemplars.md 가 없습니다.")

    style_guide = STYLE_GUIDE_PATH.read_text(encoding="utf-8")
    exemplars = EXEMPLARS_PATH.read_text(encoding="utf-8")
    mode_label = "내돈내산(직접 구매)" if mode == "self_paid" else "협찬(제공받음)"
    info_text = "\n".join(f"{k}: {v}" for k, v in info.items())
    photo_order = "\n".join(f"{i+1}. {p}" for i, p in enumerate(photos))

    prompt = f"""당신은 블로그 글 작성 전문가입니다. 아래 스타일 가이드와 예시를 참고해 블로그 본문을 작성하세요.

## 스타일 가이드
{style_guide}

## 예시 글 (참고용)
{exemplars}

## 이번 포스팅 정보
작성 모드: {mode_label}
{info_text}

## 첨부 사진 순서
{photo_order}

위 사진들을 순서대로 보고, 스타일 가이드에 맞게 블로그 본문을 작성하세요.
사진은 본문 흐름에 자연스럽게 배치하고 각 사진에 짧은 캡션을 달아주세요.

주의사항:
- 절취선, 구분선(─, ━, —, ***, ---), 가로줄은 절대 사용하지 마세요.
- 섹션 제목(## 같은 마크다운)도 사용하지 마세요.
- 자연스러운 문단 흐름으로만 작성하세요.
- 주소(도로명 주소, 지번 주소 등)는 절대 제목에 넣지 마세요. 주소는 본문에만 포함하세요.
- 제목은 가게/장소 이름과 분위기·특징·감성 키워드만 담아야 합니다.

반드시 아래 JSON 형식으로만 출력하세요 (다른 텍스트 없이):
{{
  "title": "블로그 제목 (주소·번지 절대 포함 금지)",
  "address": "실제 도로명 주소 (없으면 빈 문자열)",
  "tags": ["태그1", "태그2", "태그3"],
  "body": [
    {{"type": "text", "content": "텍스트 내용"}},
    {{"type": "image", "filename": "IMG_001.jpg", "caption": "사진 설명"}},
    {{"type": "text", "content": "다음 텍스트"}},
    ...
  ]
}}"""

    print(f"[post] 사진 {len(photos)}장 로드 중...")
    parts: list = [prompt]
    loaded = 0
    for photo_name in photos:
        photo_path = folder / photo_name
        try:
            img = Image.open(photo_path)
            img.load()  # 파일 핸들 즉시 닫기 위해
            parts.append(img)
            loaded += 1
        except Exception as e:
            print(f"  ⚠️ 사진 로드 실패 (건너뜀): {photo_name} — {e}")

    print(f"[post] Gemini에 요청 중... (사진 {loaded}장)")
    client = genai.Client(api_key=GEMINI_API_KEY)

    import time
    for attempt in range(1, 4):
        try:
            response = client.models.generate_content(model=MODEL_GEMINI, contents=parts)
            break
        except Exception as e:
            if attempt == 3 or "503" not in str(e):
                raise
            print(f"  서버 과부하, {15}초 후 재시도... ({attempt}/3)")
            time.sleep(15)

    text = response.text.strip()

    # 마크다운 코드블록 제거
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    post = json.loads(text)

    # address 필드 처리: 제목에서 강제 제거 + 본문 하단에 추가
    import re as _re
    address = post.get("address", "").strip()

    # 제목에서 주소 제거 (address 필드 값 + 일반 주소 패턴 모두 제거)
    _title = post.get("title", "")
    if address and address in _title:
        _title = _title.replace(address, "")
    # | 구분자 기준으로 주소처럼 보이는 파트 추가 제거
    _addr_re = _re.compile(
        r'\d+[-]\d+'
        r'|\S+[길로가]\s*\d+'
        r'|\d+층'
        r'|[가-힣]+구\s+[가-힣]+[길로가]'
        r'|서울\s*\S+구'
    )
    _parts = _re.split(r'\s*[|｜]\s*', _title)
    _clean = [p.strip() for p in _parts if p.strip() and not _addr_re.search(p)]
    post["title"] = " | ".join(_clean).strip(" |·,") if _clean else _title.strip()

    # 본문 하단에 주소 추가 (이미 있으면 스킵)
    if address:
        body = post.get("body", [])
        already_in_body = any(
            address in b.get("content", "")
            for b in body if b.get("type") == "text"
        )
        if not already_in_body:
            body.append({"type": "text", "content": f"📍 {address}"})

    # 장소 검색어 추가 (맛집/카페 등 위치 기반 포스팅)
    place_name = (
        info.get("카페/음식점 이름")
        or info.get("카페 이름")
        or info.get("음식점 이름")
        or info.get("가게 이름")
        or ""
    )
    location = info.get("위치", "")
    if place_name:
        post["place_search"] = f"{place_name} {location}".strip()

    # 절취선/구분선 후처리 — 모델이 무시해도 강제 제거
    import re
    divider_pattern = re.compile(
        r"^[\s]*[-─━=*~_·•|▬]{3,}[\s]*$|"      # --- === *** ─── 등 단독 줄
        r"^[\s]*[─━―—─=\-_]{3,}[\s]*$|"         # 유니코드 가로선 / 대시 단독 줄
        r"^[\s]*([-─━=*~_·•|] *){3,}[\s]*$",    # "- - -" 공백 섞인 반복 패턴
        re.MULTILINE,
    )
    for block in post.get("body", []):
        if block.get("type") == "text":
            cleaned = divider_pattern.sub("", block["content"])
            # 연속 빈 줄 2개 이상 → 1개로
            cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
            block["content"] = cleaned

    return post


def main() -> int:
    parser = argparse.ArgumentParser(
        description="사진 폴더에서 Gemini로 네이버 블로그 본문 생성"
    )
    parser.add_argument("folder", help="사진과 info.txt 가 있는 폴더 경로")
    parser.add_argument(
        "--mode",
        choices=VALID_MODES,
        default="self_paid",
        help="작성 모드 (기본: self_paid). 협찬은 sponsored.",
    )
    args = parser.parse_args()

    folder = Path(args.folder).resolve()
    if not folder.exists() or not folder.is_dir():
        print(f"❌ 폴더가 존재하지 않습니다: {folder}")
        return 1

    info_path = folder / INFO_FILENAME
    if not info_path.exists():
        print(f"⚠️  {INFO_FILENAME} 가 없습니다. 다음 형식으로 만들어주세요:")
        print()
        print("    카페 이름: (가게 이름)")
        print("    위치: (지역/주소)")
        print("    방문일: YYYY-MM-DD")
        print("    메뉴: 메뉴1 가격, 메뉴2 가격")
        print("    한줄평: (전반적 인상)")
        print()
        return 1

    try:
        post = generate_post(folder, args.mode)
    except (FileNotFoundError, RuntimeError) as e:
        print(f"❌ {e}")
        return 1
    except json.JSONDecodeError as e:
        print(f"❌ Gemini 응답 파싱 실패: {e}")
        print("   응답이 JSON 형식이 아닙니다. 다시 시도해보세요.")
        return 1

    out_path = folder / "generated_post.json"
    out_path.write_text(
        json.dumps(post, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"✓ 본문 생성 완료: {out_path}")
    print()
    print(f"  제목: {post.get('title', '')}")
    print(f"  태그: {', '.join(post.get('tags', []))}")
    print(f"  블록: {len(post.get('body', []))}개")
    print()
    print("다음 단계: publish.bat 실행 또는")
    print(f"  python -m src.publisher \"{folder}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
