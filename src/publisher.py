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

# frozen exe: Playwright가 _MEIPASS 안을 뒤지지 않도록 브라우저 경로 고정
if getattr(sys, "frozen", False):
    import os as _os
    _local = _os.environ.get("LOCALAPPDATA", "")
    if _local and "PLAYWRIGHT_BROWSERS_PATH" not in _os.environ:
        _os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(Path(_local) / "ms-playwright")


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


def open_write_page(page: Page, context) -> Page:
    """블로그 홈 → 글쓰기 버튼 클릭 → 새 탭(에디터) 반환."""
    log("네이버 블로그 홈 접근 중...")
    _safe_goto(page, "https://section.blog.naver.com/BlogHome.naver")
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    time.sleep(2.0)

    if _is_login_page(page):
        raise RuntimeError("로그인 페이지로 리다이렉트됨 — 세션 만료. data/auth_state.json 삭제 후 재시도.")

    # 글쓰기 버튼 클릭 — 새 탭으로 열림
    write_sel = "#container > div > aside > div > div:nth-child(1) > nav > a:nth-child(2)"
    try:
        page.wait_for_selector(write_sel, timeout=8000)
    except Exception as e:
        try:
            page.screenshot(path="debug_blog_home.png", full_page=True)
        except Exception:
            pass
        raise RuntimeError(f"글쓰기 버튼을 찾지 못했습니다: {e}")

    with context.expect_page() as new_page_info:
        page.click(write_sel)

    editor_page = new_page_info.value
    log("  ✓ 글쓰기 새 탭 열림")
    try:
        editor_page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    time.sleep(2.0)
    log(f"  에디터 URL: {editor_page.url}")

    # "작성 중인 글 있음" 팝업 → 취소(새로 작성) 클릭
    _dismiss_draft_popup(editor_page)
    time.sleep(1.0)  # 도움말 패널 렌더링 대기

    return editor_page


def _dismiss_draft_popup(editor_page: Page) -> None:
    """임시저장된 글 불러오기 팝업이 뜨면 취소(새로 작성) 버튼 클릭."""
    # editor_page 및 mainFrame 양쪽 탐색
    mf = editor_page.frame(name="mainFrame")
    contexts = ([mf, editor_page] if mf else [editor_page])

    handled = False

    # 1) CSS 셀렉터
    cancel_selectors = [
        "button.se-popup-button-cancel",
        "button[class*='cancel']",
        "button[class*='Cancel']",
        ".se-popup-button:last-child",
        ".btn_cancel",
        "button.btn_close",
    ]
    for ctx in contexts:
        for sel in cancel_selectors:
            try:
                el = ctx.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    log(f"  팝업 취소: CSS '{sel}'")
                    time.sleep(1.0)
                    handled = True
                    break
            except Exception:
                continue
        if handled:
            return

    # 2) 텍스트 기반
    for ctx in contexts:
        for txt in ("취소", "새로 작성", "처음부터 작성", "닫기"):
            try:
                btn = ctx.get_by_role("button", name=txt).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    log(f"  팝업 취소: '{txt}' 클릭")
                    time.sleep(1.0)
                    return
            except Exception:
                continue

    # 3) 팝업 안 버튼 전체 — 마지막 버튼이 보통 취소
    for ctx in contexts:
        try:
            popup_btns = ctx.query_selector_all(
                ".se-popup button, [role='dialog'] button, .modal button"
            )
            if popup_btns:
                popup_btns[-1].click()
                log("  팝업 취소: 마지막 버튼 클릭")
                time.sleep(1.0)
                return
        except Exception:
            continue


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

    # SE2/SE4-in-iframe — mainFrame 안에서 탐색
    mf = page.frame(name="mainFrame")
    if mf is not None:
        try:
            # SE4 in iframe
            if mf.query_selector("div.se-container") or mf.query_selector("div.se-title-text"):
                log(f"  ✓ SE4-in-mainFrame 에디터: mainFrame 사용 ({mf.url[:60]})")
                return mf
            # SE2
            if (mf.query_selector("input#subject")
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
                    time.sleep(0.15)
                    el.fill(title)
                    log("  ✓ SE2 방식 제목 입력 완료")
                    page.keyboard.press("Tab")
                    time.sleep(0.2)
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
    time.sleep(0.2)
    try:
        page.evaluate("text => navigator.clipboard.writeText(text)", title)
        time.sleep(0.08)
        page.keyboard.press("Control+v")
    except Exception:
        page.keyboard.type(title, delay=5)
    time.sleep(0.2)
    # SE4: Enter 키가 title→body 이동. Tab은 포커스를 엉뚱한 곳으로 보냄
    page.keyboard.press("Enter")
    time.sleep(0.3)


def type_text_block(page: Page, content: str, frame=None) -> None:
    """본문 텍스트 블록 입력.

    1순위: execCommand('insertText') — SE4 paste 핸들러 우회, 서식 미상속
    2순위: clipboard + Ctrl+V 폴백
    """
    if _is_login_page(page):
        raise RuntimeError("로그인 페이지에서 본문 입력 시도 차단 — 세션 만료 가능성")
    ctx = frame if frame is not None else page
    if not content.strip():
        page.keyboard.press("Enter")
        time.sleep(0.05)
        return
    try:
        ok = ctx.evaluate(
            """(text) => {
                // 현재 포커스가 제목 영역이면 거부
                const active = document.activeElement;
                if (active && (active.closest('.se-title-text') || active.closest('.se-title-input')))
                    return false;
                // 취소선 등 서식 초기화
                try {
                    if (document.queryCommandState('strikeThrough'))
                        document.execCommand('strikeThrough', false, null);
                    if (document.queryCommandState('bold'))
                        document.execCommand('bold', false, null);
                    if (document.queryCommandState('italic'))
                        document.execCommand('italic', false, null);
                    if (document.queryCommandState('underline'))
                        document.execCommand('underline', false, null);
                } catch(e) {}
                return document.execCommand('insertText', false, text);
            }""",
            content,
        )
        if ok:
            time.sleep(0.1)
            page.keyboard.press("Enter")
            time.sleep(0.05)
            return
    except Exception:
        pass
    # 폴백: clipboard + Ctrl+V
    try:
        ctx.evaluate("text => navigator.clipboard.writeText(text)", content)
        time.sleep(0.08)
        page.keyboard.press("Control+v")
        time.sleep(0.15)
        page.keyboard.press("Enter")
    except Exception:
        for line in content.split("\n"):
            if line:
                page.keyboard.type(line, delay=3)
            page.keyboard.press("Enter")
    time.sleep(0.08)


def insert_image(page: Page, frame, image_path: Path) -> None:
    """SE4/SE2 이미지 업로드.

    frame(mainFrame) 안에서 먼저 이미지 툴바 버튼을 탐색한다.
    SE4 동작: '사진' 버튼 클릭 → hidden file input 트리거 → expect_file_chooser 로 가로챔.
    """
    log(f"  📷 사진 업로드: {image_path.name}")

    # ── 이미지 툴바 버튼 찾기 (frame 우선, page 폴백) ─────────────
    img_btn = None
    for ctx in (frame, page):
        for sel in (
            "button.se-image-toolbar-button",
            "button[data-name='image']",
            "li[data-name='image'] button",
            ".se-toolbar-item-image button",
            "[data-name='image']",
            "button[title*='사진']",
            "button[title*='이미지']",
            ".se-toolbar button:has(.se-icon-image)",
        ):
            try:
                el = ctx.query_selector(sel)
                if el and el.is_visible():
                    img_btn = el
                    break
            except Exception:
                continue
        if img_btn:
            break

    if img_btn is None:
        log("    ⚠️ 이미지 툴바 버튼 없음 — 텍스트 대체")
        page.keyboard.type(f"[사진:{image_path.name}]")
        page.keyboard.press("Enter")
        return

    # ── expect_file_chooser 활성화 후 버튼 클릭 ──────────────────
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
        img_btn.click()
        time.sleep(1.0)
        # frame 및 page 양쪽에서 파일 input 탐색
        fi = None
        for ctx in (frame, page):
            fi = (ctx.query_selector("input#hidden-file")
                  or ctx.query_selector("input[type='file']"))
            if fi:
                break
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
    time.sleep(2.5)

    # ── 이미지 다음 단락으로 커서 이동 ───────────────────────────
    page.keyboard.press("ArrowDown")
    time.sleep(0.1)
    page.keyboard.press("End")
    time.sleep(0.05)


def _focus_body(page: Page, frame) -> None:
    """SE4/SE2 본문 편집 영역 포커스.

    type_title 에서 Enter 로 이미 body 이동 완료.
    현재 포커스가 title 영역이면 강제로 body로 이동, 아니면 유지.
    """
    js = """() => {
        const active = document.activeElement;
        // 이미 body에 있으면 취소선만 끄고 리턴
        if (active && !active.closest('.se-title-text') && !active.closest('.se-title-input')) {
            try {
                if (document.queryCommandState('strikeThrough'))
                    document.execCommand('strikeThrough', false, null);
            } catch(e) {}
            return true;
        }
        // title에 있으면 body 요소 탐색
        const candidates = document.querySelectorAll(
            'p.se-text-paragraph, div.se-text-paragraph, div[contenteditable="true"]'
        );
        for (const el of candidates) {
            if (el.closest('.se-title-text') || el.closest('.se-title-input')) continue;
            if (el.classList.contains('se-title-text') || el.classList.contains('se-title-input')) continue;
            if (!el.offsetParent) continue;
            el.focus();
            try {
                if (document.queryCommandState('strikeThrough'))
                    document.execCommand('strikeThrough', false, null);
            } catch(e) {}
            return true;
        }
        return false;
    }"""
    for ctx in (frame, page):
        try:
            ok = ctx.evaluate(js)
            if ok:
                time.sleep(0.1)
                return
        except Exception:
            continue


def write_body(page: Page, frame, body_blocks: list[dict], folder: Path,
               tags: list[str] | None = None) -> None:
    """본문 블록(text/image) 을 순서대로 입력. tags 있으면 본문 마지막에 #태그 추가."""
    import os as _os

    # 첫 번째 본문 영역 클릭 — 커서를 에디터 본문에 위치
    _focus_body(page, frame)
    time.sleep(0.5)

    for i, block in enumerate(body_blocks, 1):
        btype = block.get("type")
        if btype == "text":
            log(f"[{i}/{len(body_blocks)}] 텍스트 단락 입력")
            type_text_block(page, block.get("content", ""), frame=frame)
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
                time.sleep(0.3)
                page.keyboard.press("Escape")
                time.sleep(0.2)
            caption = block.get("caption", "")
            if caption:
                page.keyboard.type(caption, delay=15)
                page.keyboard.press("Enter")
        else:
            log(f"    ⚠️ 알 수 없는 블록 타입: {btype}")

    # 태그를 본문 하단에 #태그 형식으로 추가
    if tags:
        tag_line = " ".join(f"#{t}" for t in tags[:30])
        log(f"태그 본문 추가: {tag_line}")
        page.keyboard.press("Enter")
        time.sleep(0.2)
        type_text_block(page, tag_line, frame=frame)


def close_help_panel(page: Page, frame) -> None:
    """SE4 도움말 패널 닫기.

    정확한 경로(사용자 확인):
      div.se-dnd-wrap > div > div.se-container > article > div > header > button
    UUID ID는 매번 바뀌므로 se-dnd-wrap 기준 직접 자식(>) 조합자로 탐색.
    광범위 셀렉터 금지 — 툴바 포맷 버튼(취소선 등) 오클릭 방지.
    """
    contexts = ([frame, page] if frame and frame is not page else [page])

    for ctx in contexts:
        try:
            found = ctx.evaluate("""() => {
                // se-dnd-wrap 기준으로 정확한 경로 탐색
                const roots = document.querySelectorAll('div.se-dnd-wrap, div.se-wrap');
                for (const root of roots) {
                    const btn = root.querySelector(
                        'div.se-container > article > div > header > button'
                    );
                    if (btn && btn.offsetParent !== null) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }""")
            if found:
                log("  도움말 패널 닫기 완료")
                time.sleep(0.3)
                return
        except Exception:
            continue

    log("  도움말 패널 없음 또는 이미 닫힘")


def insert_place(page: Page, frame, place_search: str) -> None:
    """SE4 장소 추가 버튼 → 검색 → 첫 번째 결과 선택.

    툴바 경로: div.se-dnd-wrap > div > header > div.se-header-inbox > ul > li.se-toolbar-item-map
    버튼 클릭 후 팝업 창 / 인라인 패널 / 새 iframe 모두 대응.
    """
    if not place_search:
        return
    log(f"장소 추가: {place_search}")

    contexts = ([frame, page] if frame and frame is not page else [page])

    # ── 1) 팝업 감지하면서 버튼 클릭 ────────────────────────────
    popup_page = None
    clicked = False

    def _click_map_btn(ctx_list) -> bool:
        for ctx in ctx_list:
            try:
                result = ctx.evaluate("""() => {
                    // 두 클래스 모두 가진 li 안의 button 탐색
                    const selectors = [
                        'li.se-toolbar-item.se-toolbar-item-map button',
                        'li.se-toolbar-item-map button',
                        'li.se-toolbar-item-map',
                    ];
                    for (const sel of selectors) {
                        const btn = document.querySelector(sel);
                        if (btn && btn.offsetParent !== null) { btn.click(); return true; }
                    }
                    return false;
                }""")
                if result:
                    return True
            except Exception:
                continue
        return False

    try:
        with page.expect_popup(timeout=2500) as popup_info:
            clicked = _click_map_btn(contexts)
        popup_page = popup_info.value
        log(f"  장소 팝업 창 감지: {popup_page.url[:80]}")
        try:
            popup_page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass
    except Exception:
        # 팝업 없음 — 이미 클릭됐으면 OK, 안 됐으면 재시도
        if not clicked:
            clicked = _click_map_btn(contexts)

    if not clicked:
        log("  ⚠️ 장소 버튼 없음 — 건너뜀")
        return

    time.sleep(1.5)

    # ── 2) 검색 컨텍스트 수집 (팝업 > 새 iframe > 기존 컨텍스트) ─
    search_ctxs: list = []
    if popup_page:
        search_ctxs = [popup_page]
    else:
        # 버튼 클릭 후 새로 생긴 iframe 탐색
        existing = set(id(f) for f in ([frame] if frame else []))
        new_frames = [f for f in page.frames
                      if id(f) not in existing and f is not page.main_frame]
        search_ctxs = new_frames + contexts

    # ── 3) 검색어 입력 ──────────────────────────────────────────
    search_selectors = [
        "input[placeholder*='장소']",
        "input[placeholder*='검색']",
        "input[placeholder*='업체']",
        "input[placeholder*='지역']",
        "input[placeholder*='주소']",
        "input[placeholder*='place']",
        "input[placeholder*='search']",
        ".se-place-search-input",
        "input[type='search']",
        "input[type='text']:not([style*='display:none'])",
        "input[type='text']",
    ]
    typed = False
    key_ctx = popup_page if popup_page else page  # 키보드 이벤트 대상
    for ctx in search_ctxs:
        for sel in search_selectors:
            try:
                el = ctx.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    time.sleep(0.2)
                    el.fill(place_search)
                    time.sleep(0.3)
                    key_ctx.keyboard.press("Enter")
                    typed = True
                    log(f"  검색어 입력: {place_search}  (sel={sel})")
                    break
            except Exception:
                continue
        if typed:
            break

    if not typed:
        log("  ⚠️ 검색 입력창 없음 — 건너뜀")
        return

    time.sleep(2.5)  # 검색 결과 로딩 대기

    time.sleep(2.5)  # 검색 결과 로딩 추가 대기

    # ── 4) 첫 번째 결과 버튼 클릭 ───────────────────────────────
    # 경로: .se-popup.se-popup-placesMap ul li button
    _place_result_sel = ".se-popup.se-popup-placesMap ul li button"
    result_clicked = False
    for ctx in search_ctxs:
        # 4-a) Playwright 클릭 (force=True 로 오버레이 무시)
        try:
            el = ctx.query_selector(_place_result_sel)
            if el:
                log(f"  결과 버튼 발견: {el.text_content()[:30] if el.text_content() else ''}")
                el.click(timeout=3000, force=True)
                result_clicked = True
                log("  ✓ 장소 첫 번째 결과 선택")
                break
        except Exception as e:
            log(f"  [클릭 오류] {e}")
        # 4-b) JS dispatchEvent 폴백
        try:
            result_clicked = ctx.evaluate("""() => {
                const popup = document.querySelector('.se-popup.se-popup-placesMap');
                if (!popup) return false;
                const btn = popup.querySelector('ul li button');
                if (!btn) return false;
                btn.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true}));
                btn.dispatchEvent(new MouseEvent('mouseup',   {bubbles:true, cancelable:true}));
                btn.dispatchEvent(new MouseEvent('click',     {bubbles:true, cancelable:true}));
                return true;
            }""")
            if result_clicked:
                log("  ✓ 장소 첫 번째 결과 선택 (JS)")
                break
        except Exception:
            continue

    if not result_clicked:
        log("  ⚠️ 검색 결과 없음 — 건너뜀")
        return

    time.sleep(1.0)

    # ── 5) 확인 버튼 클릭 (지도 삽입) ──────────────────────────
    # 경로: .se-popup.se-popup-placesMap footer div button
    _confirm_sel = ".se-popup.se-popup-placesMap footer div button"
    confirmed = False
    for ctx in search_ctxs:
        try:
            el = ctx.query_selector(_confirm_sel)
            if el:
                el.click(timeout=3000, force=True)
                confirmed = True
                log("  ✓ 장소 확인 버튼 클릭 (지도 삽입)")
                break
        except Exception as e:
            log(f"  [확인 클릭 오류] {e}")
        try:
            confirmed = ctx.evaluate("""() => {
                const popup = document.querySelector('.se-popup.se-popup-placesMap');
                if (!popup) return false;
                const btn = popup.querySelector('footer div button, footer button');
                if (!btn) return false;
                btn.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true}));
                btn.dispatchEvent(new MouseEvent('mouseup',   {bubbles:true, cancelable:true}));
                btn.dispatchEvent(new MouseEvent('click',     {bubbles:true, cancelable:true}));
                return true;
            }""")
            if confirmed:
                log("  ✓ 장소 확인 버튼 클릭 JS (지도 삽입)")
                break
        except Exception:
            continue

    if not confirmed:
        log("  ⚠️ 확인 버튼 없음 — 건너뜀")

    time.sleep(1.0)


def set_category(page: Page) -> None:
    """우측 패널에서 카테고리 설정."""
    log("카테고리 설정 시도...")
    try:
        cat_btn = page.get_by_text(CATEGORY_NAME, exact=False).first
        if cat_btn.is_visible(timeout=2000):
            cat_btn.click()
            log(f"  카테고리 클릭: {CATEGORY_NAME}")
            time.sleep(0.5)
    except Exception:
        log(f"  ⚠️ 카테고리 '{CATEGORY_NAME}' 자동 선택 실패 — 수동 선택 필요")


def save_temp(page: Page, frame=None) -> bool:
    """임시저장 클릭 (frame 우선, page 폴백)."""
    log("임시저장 시도...")

    contexts = ([frame, page] if frame and frame is not page else [page])

    # 1) 텍스트 role 기반
    for txt in ("임시저장", "저장"):
        for ctx in contexts:
            try:
                btn = ctx.get_by_role("button", name=txt).first
                if btn.is_visible(timeout=1500):
                    btn.click()
                    time.sleep(2.5)
                    log(f"✓ '{txt}' 버튼 클릭 완료")
                    return True
            except Exception:
                continue

    # 2) CSS 셀렉터
    save_selectors = [
        "button[class*='save_btn']",
        "button[class*='temp']",
        "button[class*='draft']",
        "#btnSave",
        ".btn_save",
        "a[class*='save']",
        ".se-save-btn",
        "button[data-name='save']",
        "a.btn_tempsave",
        "button.btn_tempsave",
    ]
    for sel in save_selectors:
        for ctx in contexts:
            try:
                el = ctx.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    time.sleep(2.5)
                    log(f"✓ 임시저장 클릭 ({sel})")
                    return True
            except Exception:
                continue

    # 3) JS로 텍스트 포함 버튼/링크 탐색 (button, a, input 모두)
    js_click = """() => {
        const tags = ['button', 'a', 'input'];
        for (const tag of tags) {
            for (const el of document.querySelectorAll(tag)) {
                const txt = (el.textContent || el.value || '').trim();
                if (txt.includes('임시저장') && el.offsetParent !== null) {
                    el.click();
                    return true;
                }
            }
        }
        return false;
    }"""
    for ctx in contexts:
        try:
            found = ctx.evaluate(js_click)
            if found:
                time.sleep(2.5)
                log("✓ 임시저장 JS 클릭 완료")
                return True
        except Exception:
            continue

    log("❌ 저장 버튼 자동 클릭 실패 — 브라우저에서 직접 눌러주세요")
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
    place_search = data.get("place_search", "")

    # place_search 없으면 info.txt 에서 직접 구성
    if not place_search:
        info_path = folder / "info.txt"
        if info_path.exists():
            info: dict[str, str] = {}
            for line in info_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                sep = ":" if ":" in line else ("：" if "：" in line else None)
                if sep:
                    k, v = line.split(sep, 1)
                    info[k.strip()] = v.strip()
            place_name = (
                info.get("카페/음식점 이름") or info.get("카페 이름")
                or info.get("음식점 이름") or info.get("가게 이름") or ""
            )
            location = info.get("위치", "")
            place_search = f"{place_name} {location}".strip()

    log(f"본문 로드: 제목 \"{title[:40]}...\" / 블록 {len(body_blocks)}개 / 태그 {len(tags)}개")
    if place_search:
        log(f"장소 검색어: {place_search}")

    with sync_playwright() as p:
        # 저장된 세션이 있으면 로드
        ctx_kwargs = {
            "no_viewport": True,
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

        browser = p.chromium.launch(
            headless=args.headless,
            args=["--start-maximized"],
        )
        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()

        editor_page = None
        try:
            # 로그인 확인 / 처리
            if not ensure_login(context, page):
                browser.close()
                return 1

            # 글쓰기 페이지로
            # 글쓰기 새 탭 열기 — editor_page 로 이후 모든 작업
            editor_page = open_write_page(page, context)
            time.sleep(0.5)

            frame = get_editor_frame(editor_page)

            # 도움말/가이드 패널 닫기
            close_help_panel(editor_page, frame)

            # 제목 입력
            type_title(editor_page, frame, title)
            time.sleep(0.5)

            # 본문 입력 (태그도 본문 하단에 #태그 형식으로 추가)
            write_body(editor_page, frame, body_blocks, folder, tags=tags)
            time.sleep(0.8)

            # 장소 추가 (태그 이후)
            insert_place(editor_page, frame, place_search)

            # 카테고리
            set_category(editor_page)
            time.sleep(0.5)

            log("✓ 글 작성 완료! 발행 후 브라우저를 직접 닫아주세요.")

        except Exception as e:
            log(f"❌ 오류 발생: {e}")
            try:
                page.screenshot(path=str(folder / "publish_error.png"), full_page=True)
                log(f"디버그 스크린샷: {folder / 'publish_error.png'}")
            except Exception:
                pass

        # 에디터 탭(또는 브라우저)이 닫힐 때까지 대기
        log("브라우저를 닫으면 자동 종료됩니다.")
        try:
            target = None
            for candidate in (editor_page, page):
                if candidate is None:
                    continue
                try:
                    if not candidate.is_closed():
                        target = candidate
                        break
                except Exception:
                    continue
            if target is not None:
                target.wait_for_event("close", timeout=0)
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
