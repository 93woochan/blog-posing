"""Phase B — 사진 폴더 + 메모로부터 블로그 본문을 생성.

사용법:
    # 내돈내산 모드 (기본값)
    python -m src.post ./photos/2026-05-15-cafexyz

    # 협찬 모드
    python -m src.post ./photos/2026-05-15-cafexyz --mode sponsored

폴더 구조 예:
    photos/2026-05-15-cafexyz/
    ├── info.txt          ← 카페 정보 메모 (필수)
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

동작 (현재 - Cowork 협업 모드):
    1. info.txt + 사진 파일 목록 + 모드 정보를 읽음
    2. 생성용 입력 패키지(JSON)를 ./generation_request.json 으로 저장
    3. Cowork에서 Claude에게 "이 폴더로 본문 만들어줘" 요청하면 Claude가
       style_guide.md + exemplars.md + 사진을 보고 본문 작성

향후 (자동 모드):
    Anthropic API를 이용해 Claude가 직접 본문을 생성하고 결과를 출력.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.config import EXEMPLARS_PATH, STYLE_GUIDE_PATH


VALID_MODES = ("self_paid", "sponsored")
INFO_FILENAME = "info.txt"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}


def parse_info(info_path: Path) -> dict:
    """info.txt 를 key: value 형식으로 파싱."""
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
        elif "：" in line:  # 전각 콜론
            k, v = line.split("：", 1)
            info[k.strip()] = v.strip()
    return info


def list_photos(folder: Path) -> list[str]:
    """폴더 내 이미지 파일을 정렬해 상대경로 리스트로 반환."""
    photos = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )
    return [p.name for p in photos]


def build_request(folder: Path, mode: str) -> dict:
    """Cowork 모드용 생성 요청 패키지를 만든다."""
    info = parse_info(folder / INFO_FILENAME)
    photos = list_photos(folder)

    if not STYLE_GUIDE_PATH.exists():
        raise FileNotFoundError(
            f"style_guide.md 가 없습니다 ({STYLE_GUIDE_PATH}). "
            "먼저 Phase A(크롤링 + 학습)를 완료하세요."
        )
    if not EXEMPLARS_PATH.exists():
        raise FileNotFoundError(
            f"exemplars.md 가 없습니다 ({EXEMPLARS_PATH})."
        )

    return {
        "mode": mode,
        "folder": str(folder.resolve()),
        "info": info,
        "photos": photos,
        "style_guide_path": str(STYLE_GUIDE_PATH.resolve()),
        "exemplars_path": str(EXEMPLARS_PATH.resolve()),
        "instructions": (
            "Claude는 다음을 수행한다:\n"
            "  1. style_guide_path 의 가이드를 시스템 프롬프트로 적용.\n"
            "  2. exemplars_path 의 예시 글을 참조 톤으로 사용.\n"
            "  3. mode 값에 따라 sponsored 또는 self_paid 모드 규칙 적용.\n"
            "  4. info 의 가게 정보(이름/위치/메뉴/한줄평/동행)를 본문에 자연스럽게 녹임.\n"
            "  5. photos 파일들을 본문 흐름에 맞게 배치하고, 사진별 간단 캡션 자동 생성.\n"
            "  6. 출력은 다음 JSON 형식:\n"
            "     { \"title\": \"...\", \"tags\": [...], \"body\": [ "
            "{\"type\":\"text\",\"content\":\"...\"}, "
            "{\"type\":\"image\",\"filename\":\"IMG_001.jpg\",\"caption\":\"...\"}, "
            "... ] }\n"
            "  7. 사람 검토 후 OK 받으면 Playwright로 네이버에 임시저장."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="사진 폴더로부터 네이버 블로그 본문 생성 요청 패키지 만들기"
    )
    parser.add_argument("folder", help="사진과 info.txt 가 있는 폴더 경로")
    parser.add_argument(
        "--mode",
        choices=VALID_MODES,
        default="self_paid",
        help="작성 모드 (기본: self_paid). 협찬은 sponsored.",
    )
    parser.add_argument(
        "--out",
        default="generation_request.json",
        help="생성 요청 패키지를 저장할 파일명 (기본: generation_request.json)",
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
        request = build_request(folder, args.mode)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return 1

    out_path = folder / args.out
    out_path.write_text(
        json.dumps(request, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"✓ 생성 요청 패키지 저장: {out_path}")
    print()
    print("─" * 60)
    print(f"  모드:      {request['mode']}")
    print(f"  사진:      {len(request['photos'])}장")
    print(f"  info:      {len(request['info'])}개 항목")
    print("─" * 60)
    print()
    print("다음 단계: Cowork(이 채팅)에 돌아와서 아래처럼 말씀해주세요:")
    print()
    print(f"   \"{folder} 폴더로 블로그 본문 만들어줘\"")
    print()
    print("그러면 Claude가 style_guide + exemplars + 사진을 보고")
    print("본문을 생성하고, OK 받으면 네이버에 임시저장합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
