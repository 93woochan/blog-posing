"""Phase B 3단계 — 네이버 블로그에 자동 포스팅 (Playwright).

사용법:
    # 임시저장 모드 (기본, 안전)
    python -m src.publisher "./photos/2026-05-16-인스파이어 호라이즌 라운지"

    # 즉시 발행 모드 (위험, 임시저장 후 검토 권장)
    python -m src.publisher "./photos/..." --publish

전제:
    1. 폴더에 generated_post.json 이 있어야 함
       (먼저 Claude에게 본문 만들어달라고 요청)
    2. data/auth_state.json (네이버 로그인 세션)이 있으면 자동 로그인
       없으면 최초 1회 직접 로그인 (캡차/2FA 본인이 처리)

동작:
    1. Playwright Chromium 띄움 (headless=False 권장 — 처음엔 보이게)
    2. 네이버 로그인 (세션 재사용 또는 직접 로그인)
    3. 글쓰기 페이지 진입
    4. 제목 입력
    5. 본문 입력 (텍스트 단락 + 사진 업로드 교차)
    6. 카테고리 / 태그 설정
    7. 임시저장 (또는 발행)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import Page, sync_playwright

from src.config import AUTH_STATE_PATH, BLOG_ID, CATEGORY_NAME, NAVER_ID, NAVER_PW


# ─────────────────────────── 로깅 ───────────────────────────
def log(msg: str) -> None:
    print(f"[publisher] {msg}", flush=True)


# ─────────────────────────── 로그인 ───────────────────────────
def _safe_goto(page: Page, url: str, timeout: int = 20000) -> None:
    """리다이렉트로 인한 navigation interruption 을 무시하며 URL 로 이동."""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    except Exception as e:
        msg = str(e)
        # 리다이렉트로 인한 인터럽션 / 타임아웃은 무시하고 진행
        if "interrupted" in msg or "Timeout" in msg or "ERR_ABORTED" in msg:
            log(f"  (리다이렉트 또는 타임아웃 발생 — 무시하고 진행)")
            return
        raise


def _is_logged_in(page: Page) -> bool:
    """현재 페이지 상태로 로그인 여부 판단."""
    url = page.url
    if "nid.naver.com" in url or "nidlogin" in url:
        return False

    # 쿠키 기반 — 가장 신뢰할 수 있는 방법 (NID_AUT / NID_SES)
    try:
        cookies = {c["name"]: c["value"] for c in page.context.cookies()}
        if "NID_AUT" in cookies and cookies["NID_AUT"]:
            return True
    except Exception:
        pass

    # 로그인 링크 셀렉터 기반 (폴백 — 없으면 로그인 안 된 것으로 간주)
    for sel in (
        "a.MyView-module__link_login___HpHMW",
        "a.link_login",
        "a[data-clk='top.login']",
        "a[data-clk='gnb.login']",
        ".btn_login",
    ):
        try:
            if page.query_selector(sel):
                return False
        except Exception:
            continue

    # 헤더 텍스트에 '로그인' 버튼이 있고 '로그아웃'은 없으면 미로그인
    try:
        header_html = page.evaluate(
            "() => { const h = document.querySelector('header,#header,.gnb_wrap'); return h ? h.innerHTML : ''; }"
        )
        if "로그인" in header_html and "로그아웃" not in header_html:
            return False
    except Exception:
        pass

    return True


def ensure_login(context, page: Page) -> bool:
    """네이버 로그인 상태 확인. 저장된 세션이 있으면 그대로,
    없으면 사용자에게 직접 로그인 요청 후 세션 저장."""
    log("네이버 접속 중...")
    _safe_goto(page, "https://www.naver.com")
    time.sleep(2.0)

    if _is_logged_in(page):
        log("✓ 저장된 세션으로 자동 로그인되어 있습니다.")
        return True

    # 미로그인 상태 → 로그인 페이지로 이동
    if "nid.naver.com" not in page.url:
        _safe_goto(page, "https://nid.naver.com/nidlogin.login")
    time.sleep(1.0)

    # .env 에 계정 정보가 있으면 자동 입력 시도 (플레이스홀더 값 제외)
    _placeholder_hints = ("여기에", "your_", "입력", "ENTER", "example", "xxx")
    _cred_valid = (
        NAVER_ID and NAVER_PW
        and not any(h in NAVER_ID for h in _placeholder_hints)
        and not any(h in NAVER_PW for h in _placeholder_hints)
    )
    if _cred_valid:
        log("계정 정보로 자동 로그인 시도...")
        try:
            page.fill("input#id", NAVER_ID)
            time.sleep(0.4)
            page.fill("input#pw", NAVER_PW)
            time.sleep(0.4)
            page.click("button.btn_login, input.btn_login")
            time.sleep(3.0)
            log("자동 로그인 입력 완료. 캡차/2FA 가 뜬 경우 직접 처리 후 Enter 를 눌러주세요.")
        except Exception as e:
            log(f"⚠️  자동 입력 실패 ({e}) — 직접 로그인해주세요.")

        input("→ 로그인 완료 후 이 콘솔로 돌아와 Enter 를 눌러주세요... ")
    else:
        log("─" * 50)
        log("로그인이 필요합니다.")
        if NAVER_ID and any(h in NAVER_ID for h in _placeholder_hints):
            log("⚠️  .env 의 NAVER_ID / NAVER_PW 가 아직 플레이스홀더 상태입니다.")
            log("    .env 파일을 열어 실제 네이버 아이디/비밀번호로 교체해주세요.")
        else:
            log(".env 에 NAVER_ID / NAVER_PW 를 설정하면 다음 실행부터 자동 입력됩니다.")
        log("열린 Chromium 창에서 네이버에 직접 로그인해주세요.")
        log("─" * 50)
        input("→ 로그인 완료 후 이 콘솔로 돌아와 Enter 를 눌러주세요... ")

    # 로그인 검증: 네이버 메인으로 다시 가본 다음 상태 확인
    _safe_goto(page, "https://www.naver.com")
    time.sleep(2.0)
    if not _is_logged_in(page):
        log("❌ 로그인이 확인되지 않습니다. 브라우저에서 로그인 상태인지 확인하고 다시 시도하세요.")
        return False

    # 세션 저장 (다음 실행 시 자동 로그인 가능)
    try:
        context.storage_state(path=str(AUTH_STATE_PATH))
        log(f"✓ 로그인 성공. 세션 저장: {AUTH_STATE_PATH}")
    except Exception as e:
        log(f"⚠️  세션 저장 실패 (다음 실행 때 다시 로그인 필요): {e}")
    return True


# ─────────────────────────── 글쓰기 ───────────────────────────
def _is_login_page(page: Page) -> bool:
    """현재 페이지가 네이버 로그인 페이지인지 확인."""
    return "nid.naver.com" in page.url or "nidlogin" in page.url


def open_write_page(page: Page) -> None:
    """블로그 글쓰기 페이지로 진입."""
    url = f"https://blog.naver.com/PostWriteForm.naver?blogId={BLOG_ID}"
    log(f"글쓰기 페이지 진입: {url}")
    _safe_goto(page, url)
    # SmartEditor ONE(SE4) 렌더링 대기 — React 앱이라 iframe 대신 se-title-text 감지
    log("  SmartEditor 렌더링 대기 중...")
    _editor_ready = False
    for wait_sel in ("div.se-title-text", "div.se-container", "section.se-component"):
        try:
            page.wait_for_selector(wait_sel, timeout=15000)
            log(f"  ✓ 에디터 감지됨: {wait_sel}")
            _editor_ready = True
            break
        except Exception:
            continue
    if not _editor_ready:
        # 구형 SmartEditor 2 (iframe 방식) 폴백
        try:
            page.wait_for_selector("iframe", timeout=5000)
            log("  ✓ iframe 감지됨 (SE2 방식)")
        except Exception:
            log("  ⚠️ 에디터 감지 타임아웃 — 로드 상태 확인 필요")
    time.sleep(2.0)

    current_url = page.url
    log(f"  현재 URL: {current_url}")

    # 로그인 페이지로 리다이렉트 됐는지 확인
    if _is_login_page(page):
        raise RuntimeError(
            "글쓰기 페이지 진입 실패 — 로그인 페이지로 리다이렉트됨.\n"
            "  세션이 만료됐을 수 있습니다. data/auth_state.json 을 삭제하고 다시 실행하세요."
        )

    # 예상치 못한 URL (blog.naver.com 이 아닌 곳) 감지
    if "blog.naver.com" not in current_url and "se.naver.com" not in current_url:
        raise RuntimeError(
            f"글쓰기 페이지 진입 실패 — 예상치 못한 URL: {current_url}\n"
            "  로그인이 만료됐거나 BLOG_ID 가 잘못됐을 수 있습니다.\n"
            "  data/auth_state.json 을 삭제하고 다시 실행하세요."
        )

    # SmartEditor 가 보통 'mainFrame' 이름의 iframe 안에 있음
    # 일부 케이스에서 alert/팝업 (작성중인 글 있음) 뜸 — 자동으로 끌어다 쓰지 않고 처음부터 작성하는 쪽 선택
    try:
        # "새로 작성" 또는 "취소" 버튼 클릭 시도
        for txt in ("취소", "새로 작성", "처음부터 작성", "닫기"):
            btn = page.get_by_role("button", name=txt).first
            try:
                if btn.is_visible(timeout=2000):
                    btn.click()
                    log(f"팝업 처리: '{txt}' 클릭")
                    time.sleep(1.0)
                    break
            except Exception:
                continue
    except Exception:
        pass


def get_editor_frame(page: Page):
    """SmartEditor 가 살아있는 컨텍스트 반환 (SE2 / SE4 모두 지원).

    SE4(SmartEditor ONE) — iframe 없이 메인 페이지에 직접 렌더링.
    SE2 — mainFrame iframe 안에 에디터 존재.
    """
    # SE4 — 메인 페이지 자체에 se-container / se-title-text 가 있음
    try:
        if page.query_selector("div.se-container") or page.query_selector("div.se-title-text"):
            log("  ✓ SE4 에디터: 메인 페이지 직접 사용")
            return page
    except Exception:
        pass

    # SE2 — mainFrame 안에서 탐색
    mf = page.frame(name="mainFrame")
    if mf is not None:
        try:
            if (mf.query_selector("div.se-container")
                    or mf.query_selector("input#subject")
                    or mf.query_selector("div#smarteditor")):
                log(f"  ✓ SE2 에디터: mainFrame 사용 ({mf.url[:60]})")
                return mf
        except Exception:
            pass
        log(f"  ⚠️ mainFrame 감지됐지만 에디터 요소 없음 — mainFrame 사용: {mf.url[:60]}")
        return mf

    # 다른 하위 프레임에서 SE2 탐색
    for f in page.frames:
        if f == page.main_frame:
            continue
        try:
            if (f.query_selector("div#smarteditor")
                    or f.query_selector("textarea#ir1")
                    or f.query_selector("div.se2_inputarea")):
                log(f"  ✓ SE2 에디터 서브프레임: {f.url[:60]}")
                return f
        except Exception:
            continue

    log("  ⚠️ 에디터 프레임 감지 실패 — page 직접 사용")
    return page


def type_title(page: Page, frame, title: str) -> None:
    """제목 입력 — SmartEditor 2 / SmartEditor ONE 모두 지원."""
    log(f"제목 입력: {title[:30]}...")

    # ── SmartEditor 2 방식: input#subject ──────────────────────
    # SE2 에서는 mainFrame(또는 page) 안에 <input id="subject"> 가 있음
    for ctx in (frame, page):
        for sel in (
            "input#subject",
            "input[name='subject']",
            "textarea#subject",
            "input[placeholder*='제목']",
        ):
            try:
                el = ctx.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    time.sleep(0.3)
                    el.fill(title)
                    log("  ✓ SE2 방식 제목 입력 완료")
                    page.keyboard.press("Tab")
                    time.sleep(0.5)
                    return
            except Exception:
                continue

    # ── SmartEditor ONE(SE4) 방식: contenteditable div ─────────
    se4_selectors = [
        "div.se-title-text",
        "div.se-title-input div[contenteditable='true']",
        "div[contenteditable='true'].se-title-text",
        "span.se-placeholder__text",
        "div[contenteditable='true'].se-text-paragraph",
    ]
    target = None
    for sel in se4_selectors:
        try:
            el = frame.query_selector(sel)
            if el:
                target = el
                break
        except Exception:
            continue

    if target is None:
        # 진단용: 현재 프레임의 contenteditable 목록 출력
        try:
            editable_count = frame.evaluate(
                "() => document.querySelectorAll('[contenteditable=true]').length"
            )
            log(f"  진단: contenteditable 요소 수 = {editable_count} / 프레임 URL = {frame.url}")
        except Exception:
            pass
        log("⚠️  제목 영역을 찾지 못했어요. 화면에서 직접 입력해주세요.")
        return

    target.click()
    time.sleep(0.5)
    try:
        page.evaluate("text => navigator.clipboard.writeText(text)", title)
        time.sleep(0.1)
        page.keyboard.press("Control+v")
    except Exception:
        page.keyboard.type(title, delay=10)
    time.sleep(0.5)
    page.keyboard.press("Tab")
    time.sleep(0.5)


def type_text_block(page: Page, content: str) -> None:
    """본문 텍스트 블록 입력 — 클립보드 붙여넣기로 빠르게."""
    if _is_login_page(page):
        raise RuntimeError("로그인 페이지에서 본문 입력 시도 차단 — 세션 만료 가능성")
    if not content.strip():
        page.keyboard.press("Enter")
        time.sleep(0.1)
        return
    try:
        # 클립보드에 쓰고 Ctrl+V 붙여넣기 (한번에 처리)
        page.evaluate("text => navigator.clipboard.writeText(text)", content)
        time.sleep(0.15)
        page.keyboard.press("Control+v")
        time.sleep(0.3)
        page.keyboard.press("Enter")
    except Exception:
        # 폴백: 줄별 타이핑 (delay 줄여서 속도 향상)
        for line in content.split("\n"):
            if line:
                page.keyboard.type(line, delay=5)
            page.keyboard.press("Enter")
    time.sleep(0.2)


def insert_image(page: Page, frame, image_path: Path) -> None:
    """SE4 이미지 업로드.

    SE4 동작 원리:
      '사진' 툴바 버튼 클릭 → JS 가 <input id='hidden-file' type='file'> 생성 후
      즉시 .click() 호출 → OS 파일 탐색기 창이 열림.

    Playwright expect_file_chooser 를 툴바 버튼 클릭 **전**에 활성화하면
    OS 다이얼로그가 화면에 표시되기 전에 가로채 파일을 프로그래밍으로 지정.
    → 파일 탐색기 창 미표시, 자동 무음 업로드.
    """
    log(f"  📷 사진 업로드: {image_path.name}")

    # ── 이미지 툴바 버튼 찾기 ─────────────────────────────────────
    img_btn = None
    for sel in (
        "button.se-image-toolbar-button",
        "button[data-name='image']",
    ):
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                img_btn = el
                break
        except Exception:
            continue

    if img_btn is None:
        log("    ⚠️ 이미지 툴바 버튼 없음 — 텍스트 대체")
        page.keyboard.type(f"[사진:{image_path.name}]")
        page.keyboard.press("Enter")
        return

    # ── expect_file_chooser 활성화 후 버튼 클릭 ──────────────────
    # SE4 가 hidden-file input.click() 을 호출하는 순간 Playwright 가 가로챔
    upload_done = False
    try:
        with page.expect_file_chooser(timeout=5000) as fc_info:
            img_btn.click()
        fc_info.value.set_files(str(image_path))
        upload_done = True
        log("    ✓ 파일 선택 완료 (file chooser)")
    except Exception as e:
        log(f"    file chooser 방식 실패 ({e}) — hidden-file 직접 시도")

    if not upload_done:
        # 폴백: SE4 가 생성한 input#hidden-file 에 직접 set_input_files
        img_btn.click()
        time.sleep(1.0)
        fi = page.query_selector("input#hidden-file") or page.query_selector("input[type='file']")
        if fi:
            fi.set_input_files(str(image_path))
            upload_done = True
            log("    ✓ set_input_files 완료 (폴백)")
        else:
            log("    ⚠️ 이미지 업로드 실패 — 텍스트 대체")
            page.keyboard.type(f"[사진:{image_path.name}]")
            page.keyboard.press("Enter")
            return

    # ── 업로드 완료 대기 ──────────────────────────────────────────
    time.sleep(3.5)

    # ── 이미지 다음 단락으로 커서 이동 ───────────────────────────
    # SE4 는 이미지 삽입 후 새 빈 단락 자동 생성 — ArrowDown 으로 이동
    page.keyboard.press("ArrowDown")
    time.sleep(0.2)
    page.keyboard.press("End")
    time.sleep(0.1)


def _focus_body(page: Page, frame) -> None:
    """SE4 본문 편집 영역에 포커스 (커서 위치 확보)."""
    for sel in (
        "div.se-body",
        "div.se-content",
        "div.se-component.se-text",
        "section.se-component",
    ):
        try:
            el = frame.query_selector(sel) or page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                time.sleep(0.3)
                return
        except Exception:
            continue


def write_body(page: Page, frame, body_blocks: list[dict], folder: Path) -> None:
    """본문 블록(text/image) 을 순서대로 입력."""
    import os as _os

    # 첫 번째 본문 영역 클릭 — 커서를 에디터 본문에 위치
    _focus_body(page, frame)
    time.sleep(0.5)

    for i, block in enumerate(body_blocks, 1):
        btype = block.get("type")
        if btype == "text":
            log(f"[{i}/{len(body_blocks)}] 텍스트 단락 입력")
            type_text_block(page, block.get("content", ""))
        elif btype == "image":
            filename = block.get("filename", "")
            image_path = folder / filename
            # Windows MAX_PATH(260자) 초과 경로 대응 — \\?\ 접두사로 긴 경로 허용
            image_path_str = str(image_path)
            if sys.platform == "win32" and len(image_path_str) > 250:
                image_path_str = "\\\\?\\" + image_path_str.replace("/", "\\")
            if not _os.path.exists(image_path_str):
                log(f"    ⚠️ 사진 파일 없음: {image_path}")
                continue
            insert_image(page, frame, Path(image_path_str))
            # 이미지 삽입 후: 다음 블록이 텍스트면 에디터 본문에 포커스 재확보
            next_block = body_blocks[i] if i < len(body_blocks) else None
            if next_block and next_block.get("type") == "text":
                # 패널 닫힌 후 본문 클릭 (키보드 포커스 복구)
                time.sleep(0.3)
                page.keyboard.press("Escape")  # 혹시 남은 패널 한 번 더 닫기
                time.sleep(0.2)
            caption = block.get("caption", "")
            if caption:
                page.keyboard.type(caption, delay=15)
                page.keyboard.press("Enter")
        else:
            log(f"    ⚠️ 알 수 없는 블록 타입: {btype}")


def set_category_and_tags(page: Page, tags: list[str]) -> None:
    """우측 패널에서 카테고리 / 태그 설정."""
    log("카테고리 / 태그 설정 시도...")
    # 발행 영역 열기 (대부분 사이드 패널)
    try:
        # '발행' 또는 '저장' 버튼 옆 메뉴 — 카테고리 셀렉터는 블로그 스킨마다 다름
        cat_btn = page.get_by_text(CATEGORY_NAME, exact=False).first
        try:
            if cat_btn.is_visible(timeout=2000):
                cat_btn.click()
                log(f"  카테고리 클릭: {CATEGORY_NAME}")
        except Exception:
            log(f"  ⚠️ 카테고리 '{CATEGORY_NAME}' 자동 선택 실패 — 수동 선택 필요")
    except Exception:
        pass

    # 태그 입력
    tag_input_selectors = [
        "input.tag_input",
        "input[placeholder*='태그']",
        "input[aria-label*='태그']",
    ]
    tag_input = None
    for sel in tag_input_selectors:
        try:
            el = page.query_selector(sel)
            if el:
                tag_input = el
                break
        except Exception:
            continue

    if tag_input is None:
        log("  ⚠️ 태그 입력란을 찾지 못함 — 수동 입력 필요")
        return

    for t in tags:
        try:
            tag_input.click()
            page.keyboard.type(t, delay=10)
            page.keyboard.press("Enter")
            time.sleep(0.15)
        except Exception:
            continue
    log(f"  태그 {len(tags)}개 입력 완료")


def save_temp(page: Page) -> bool:
    """임시저장 클릭."""
    log("임시저장 시도...")
    for txt in ("저장", "임시저장"):
        try:
            btn = page.get_by_role("button", name=txt).first
            if btn.is_visible(timeout=2000):
                btn.click()
                time.sleep(2.5)
                log(f"✓ '{txt}' 클릭 완료")
                return True
        except Exception:
            continue
    log("❌ 저장 버튼 자동 클릭 실패 — 브라우저에서 직접 누르세요")
    return False


# ─────────────────────────── main ───────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="네이버 블로그 자동 포스팅")
    parser.add_argument("folder", help="generated_post.json 이 있는 폴더")
    parser.add_argument("--publish", action="store_true", help="임시저장 대신 즉시 발행 (위험)")
    parser.add_argument("--headless", action="store_true", help="브라우저 안 보이게 실행 (디버깅 후 사용)")
    args = parser.parse_args()

    folder = Path(args.folder).resolve()
    post_json = folder / "generated_post.json"
    if not post_json.exists():
        print(f"❌ {post_json} 가 없습니다.")
        print(f"   먼저 Claude(Cowork)에 폴더 알려주고 본문 생성 요청하세요.")
        return 1

    data = json.loads(post_json.read_text(encoding="utf-8"))
    title = data.get("title", "(제목 없음)")
    body_blocks = data.get("body", [])
    tags = data.get("tags", [])
    log(f"본문 로드: 제목 \"{title[:40]}...\" / 블록 {len(body_blocks)}개 / 태그 {len(tags)}개")

    with sync_playwright() as p:
        # 저장된 세션이 있으면 로드
        ctx_kwargs = {
            "viewport": {"width": 1280, "height": 900},
            "locale": "ko-KR",
            "permissions": ["clipboard-read", "clipboard-write"],
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/127.0 Safari/537.36"
            ),
        }
        if AUTH_STATE_PATH.exists():
            ctx_kwargs["storage_state"] = str(AUTH_STATE_PATH)
            log(f"저장된 세션 로드: {AUTH_STATE_PATH}")

        browser = p.chromium.launch(headless=args.headless)
        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()

        try:
            # 로그인 확인 / 처리
            if not ensure_login(context, page):
                browser.close()
                return 1

            # 글쓰기 페이지로
            open_write_page(page)
            time.sleep(1.5)

            frame = get_editor_frame(page)

            # 제목 입력
            type_title(page, frame, title)
            time.sleep(0.8)

            # 본문 입력
            write_body(page, frame, body_blocks, folder)
            time.sleep(1.5)

            # 카테고리 / 태그
            set_category_and_tags(page, tags)
            time.sleep(1.0)

            # 임시저장 (또는 발행)
            if args.publish:
                log("⚠️ --publish 모드: 즉시 발행은 너무 위험합니다.")
                log("   브라우저에서 직접 [발행] 버튼을 눌러주세요.")
                input("Enter 를 누르면 브라우저가 닫힙니다... ")
            else:
                save_temp(page)
                log("✓ 임시저장 완료. 네이버 앱/PC에서 검토 후 직접 발행해주세요.")
                input("브라우저를 확인 후 Enter 를 눌러 종료하세요... ")

        except Exception as e:
            log(f"❌ 오류 발생: {e}")
            # 디버깅 스크린샷
            try:
                page.screenshot(path=str(folder / "publish_error.png"), full_page=True)
                log(f"디버그 스크린샷: {folder / 'publish_error.png'}")
            except Exception:
                pass
            input("Enter 를 누르면 종료합니다... ")
            browser.close()
            return 1

        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
