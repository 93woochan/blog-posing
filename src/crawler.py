"""Phase A 1단계 — bbtn96 블로그에서 맛집/카페 카테고리 글 N개 수집.

실행:
    python -m src.crawler

동작:
    1. Chromium을 띄워 https://blog.naver.com/{BLOG_ID} 접속
    2. 좌측 카테고리에서 '맛집/카페' 클릭
    3. 최신 N개 글의 제목·URL 수집 → 콘솔 출력
    4. 각 글 본문/이미지alt/태그 추출 → data/raw_posts/*.json 저장
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime

# Windows 터미널 cp949 환경에서 한글/유니코드 깨짐 방지
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import Page, sync_playwright

from src.config import BLOG_ID, CATEGORY_NAME, CATEGORY_NO, NUM_POSTS, RAW_POSTS_DIR


def log(msg: str) -> None:
    print(f"[crawler] {msg}", flush=True)


def get_main_frame(page: Page):
    """Naver 블로그의 본문 iframe(mainFrame) 핸들을 반환."""
    page.goto(f"https://blog.naver.com/{BLOG_ID}", wait_until="domcontentloaded")
    page.wait_for_selector("iframe#mainFrame", timeout=15000)
    frame = page.frame(name="mainFrame")
    if frame is None:
        iframe_el = page.query_selector("iframe#mainFrame")
        frame = iframe_el.content_frame() if iframe_el else None
    if frame is None:
        raise RuntimeError("mainFrame iframe을 찾지 못했습니다.")
    return frame


def _norm(s: str) -> str:
    """비교용 정규화: 공백 제거, 슬래시·중점 통일, 괄호 안 숫자/공백 제거."""
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"\(\d+\)$", "", s)         # 끝의 '(43)' 같은 카운트 제거
    s = s.replace("／", "/").replace("·", "/").replace("∙", "/")
    return s.lower()


def find_and_click_category(page, category_name: str) -> bool:
    """페이지 + 모든 iframe에서 카테고리 텍스트를 찾아 클릭.

    Returns True 클릭 성공, False 실패.
    """
    log(f"카테고리 '{category_name}' 찾는 중 (페이지 + 모든 iframe 탐색)...")

    target_norm = _norm(category_name)
    # 검색 컨텍스트: 페이지 + 모든 iframe
    contexts = [page] + list(page.frames)

    for ctx in contexts:
        try:
            # 모든 <a> 태그를 훑으며 정규화된 텍스트가 일치하는지 확인
            anchors = ctx.query_selector_all("a")
        except Exception:
            continue
        for a in anchors:
            try:
                t = (a.inner_text() or "").strip()
                if not t:
                    continue
                if _norm(t) == target_norm or target_norm in _norm(t):
                    a.click(timeout=5000)
                    log(f"카테고리 클릭 완료 (텍스트: '{t}')")
                    return True
            except Exception:
                continue

    # 클릭 실패 — 디버깅용으로 페이지/iframe에서 보이는 모든 카테고리성 텍스트 출력
    log("─── 페이지에서 발견된 카테고리 후보 (디버깅) ───")
    seen_texts: set[str] = set()
    for ctx in contexts:
        try:
            anchors = ctx.query_selector_all("a")
        except Exception:
            continue
        for a in anchors:
            try:
                t = (a.inner_text() or "").strip()
                if not t or len(t) > 40 or t.startswith("http"):
                    continue
                seen_texts.add(t)
            except Exception:
                continue
    for t in sorted(seen_texts)[:100]:
        print(f"   • {t}")
    log("──────────────────────────────────────────────")
    return False


def click_category_via_url(page, blog_id: str, category_no: int) -> bool:
    """URL로 카테고리 페이지에 직접 진입 (categoryNo를 알 때의 폴백)."""
    url = f"https://blog.naver.com/{blog_id}?categoryNo={category_no}"
    log(f"URL로 카테고리 직접 진입: {url}")
    page.goto(url, wait_until="domcontentloaded", timeout=20000)
    return True


def _is_post_link(href: str) -> bool:
    """글 상세 링크인지 확인 (숫자 logNo 또는 /blogId/숫자 패턴)."""
    return bool(re.search(rf"/{re.escape(BLOG_ID)}/\d+|logNo=\d+", href))


def _extract_links_from_el(el, seen: set[str]) -> list[dict]:
    """주어진 엘리먼트 안에서 글 링크만 추출."""
    results = []
    for a in el.query_selector_all("a"):
        href = (a.get_attribute("href") or "").strip()
        title = (a.inner_text() or "").strip()
        if not href or not title:
            continue
        if href.startswith("/"):
            href = "https://blog.naver.com" + href
        if BLOG_ID not in href:
            continue
        if not _is_post_link(href):
            continue
        if href in seen:
            continue
        seen.add(href)
        results.append({"title": title, "url": href})
    return results


def _collect_from_frame(frame, seen: set[str]) -> list[dict]:
    """현재 frame에서 글 목록 컨테이너를 찾아 링크를 추출.

    사이드바/추천글 오염 방지: 메인 컨테이너 범위 내에서만 탐색.
    """
    try:
        frame.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    time.sleep(1.2)

    # tbody#postBottomTitleListBody: PostList.naver 페이지의 실제 글 목록 tbody
    container_selectors = [
        "tbody#postBottomTitleListBody",
        "#postListBody",
        "div.post_list",
        "div.post-body",
        "div#searchList",
        "table#postListTableBody",
        "ul.list_post_article",
        "div.blog2_series",
        "div.postList",
        "div[id*='postList']",
    ]

    for sel in container_selectors:
        try:
            container = frame.query_selector(sel)
        except Exception:
            continue
        if container is None:
            continue
        found = _extract_links_from_el(container, seen)
        if found:
            log(f"컨테이너 '{sel}' 에서 {len(found)}개 링크 발견.")
            return found

    # 컨테이너 탐색 실패 — 디버깅 정보 출력 후 빈 리스트 반환
    log("컨테이너 탐색 실패 — 발견된 링크 목록 (디버깅):")
    try:
        for a in frame.query_selector_all("a")[:60]:
            href = a.get_attribute("href") or ""
            text = (a.inner_text() or "").strip()[:40]
            if href and text:
                print(f"   href={href!r}  text={text!r}")
    except Exception:
        pass
    return []


def _click_next_page(frame) -> bool:
    """iframe 안의 '다음' 페이지 버튼을 클릭. 버튼이 없으면 False 반환."""
    # a._next_category 가 있으면 활성 '다음' 버튼, span 이면 마지막 페이지
    next_btn = frame.query_selector("a._next_category")
    if next_btn is None:
        return False
    next_btn.click()
    return True


def collect_post_links(page, frame, n: int) -> list[dict]:
    """카테고리 글 목록을 iframe 내 '다음' 버튼으로 페이지네이션하며 n개 수집."""
    results: list[dict] = []
    seen: set[str] = set()
    page_no = 1

    while len(results) < n:
        log(f"글 목록 수집 중 (page {page_no})...")
        found = _collect_from_frame(frame, seen)

        if not found:
            if page_no == 1:
                raise RuntimeError("글 목록을 찾지 못했습니다. 위 디버깅 출력을 확인하세요.")
            log("더 이상 글이 없습니다.")
            break

        results.extend(found)
        if len(results) >= n:
            break

        # iframe 안의 '다음' 버튼 클릭
        has_next = _click_next_page(frame)
        if not has_next:
            log("마지막 페이지입니다.")
            break

        page_no += 1
        log(f"다음 페이지 로드 대기 중 (page {page_no})...")
        try:
            frame.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        page.wait_for_timeout(1500)

    log(f"총 {len(results[:n])}개 확보 ({page_no}페이지).")
    return results[:n]


def _normalize_post_url(url: str, blog_id: str) -> str:
    """글 URL을 본문이 직접 보이는 PostView.naver 형식으로 정규화.

    `https://blog.naver.com/bbtn96/12345`  →
    `https://blog.naver.com/PostView.naver?blogId=bbtn96&logNo=12345`
    이미 PostView 형식이면 그대로 반환.
    """
    if "PostView" in url:
        return url
    m = re.search(rf"/{re.escape(blog_id)}/(\d+)", url)
    if m:
        return (
            f"https://blog.naver.com/PostView.naver"
            f"?blogId={blog_id}&logNo={m.group(1)}"
        )
    return url


def fetch_post_detail(page: Page, url: str) -> dict:
    """단일 글의 본문/이미지/태그/제목/작성일을 추출.

    글 URL은 두 가지 형태가 있음:
    - `/bbtn96/12345` : 외부 페이지로 iframe(mainFrame) 안에 본문
    - `PostView.naver?blogId=...&logNo=...` : 페이지 자체가 본문
    여기서는 PostView 형식으로 정규화해 iframe 의존성을 제거한다.
    """
    norm_url = _normalize_post_url(url, BLOG_ID)
    page.goto(norm_url, wait_until="domcontentloaded", timeout=20000)

    # iframe 이 있으면 그 안을 쓰고, 없으면 페이지 자체를 쓴다
    try:
        page.wait_for_selector("iframe#mainFrame", timeout=2000)
        frame = page.frame(name="mainFrame")
        if frame is None:
            iframe_el = page.query_selector("iframe#mainFrame")
            frame = iframe_el.content_frame() if iframe_el else None
    except Exception:
        frame = None

    ctx = frame if frame is not None else page

    try:
        ctx.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    time.sleep(0.6)

    # 본문 영역 (SmartEditor ONE 또는 구버전)
    body_text = ""
    images: list[dict] = []
    for sel in ["div.se-main-container", "div#postViewArea", "div.post_ct", "div#viewTypeSelector"]:
        el = ctx.query_selector(sel)
        if el:
            body_text = (el.inner_text() or "").strip()
            for img in el.query_selector_all("img"):
                images.append({
                    "alt": img.get_attribute("alt") or "",
                    "src": img.get_attribute("src") or "",
                })
            if body_text:
                break

    # 제목
    title = ""
    for sel in [
        "div.se-title-text",
        "h3.se_textarea",
        "span.pcol1",
        "div.htitle",
        "h3.tit_h3",
    ]:
        el = ctx.query_selector(sel)
        if el:
            title = (el.inner_text() or "").strip()
            if title:
                break

    # 태그
    tags: list[str] = []
    for sel in ["div.post_tag a", "div.wrap_tag a", "ul.tag_list a", "div.tag_list a"]:
        for el in ctx.query_selector_all(sel):
            t = (el.inner_text() or "").strip().lstrip("#")
            if t:
                tags.append(t)
        if tags:
            break

    # 작성일
    posted_at = ""
    for sel in ["span.se_publishDate", "p.date", "span.date"]:
        el = ctx.query_selector(sel)
        if el:
            posted_at = (el.inner_text() or "").strip()
            break

    return {
        "url": url,
        "normalized_url": norm_url,
        "title": title,
        "body": body_text,
        "images": images,
        "tags": tags,
        "posted_at": posted_at,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }


def slugify(s: str, maxlen: int = 20) -> str:
    """파일명용 슬러그. 한글 포함 maxlen자로 제한 (Windows 경로 길이 회피)."""
    s = re.sub(r"[^\w가-힣]+", "_", s).strip("_")
    return s[:maxlen] or "post"


def main() -> int:
    log(f"블로그: https://blog.naver.com/{BLOG_ID}")
    log(f"카테고리: {CATEGORY_NAME}")
    log(f"수집 개수: {NUM_POSTS}")

    RAW_POSTS_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        # 처음에는 headless=False 로 띄워서 무슨 일이 일어나는지 보세요.
        # 잘 동작 확인되면 headless=True 로 바꿔도 됩니다.
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/127.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="ko-KR",
        )
        page = ctx.new_page()

        try:
            # CATEGORY_NO 가 .env 에 지정되어 있으면 URL 직접 진입 (가장 안정적)
            if CATEGORY_NO:
                click_category_via_url(page, BLOG_ID, CATEGORY_NO)
            else:
                # 텍스트 검색으로 카테고리 클릭 시도
                get_main_frame(page)
                page.wait_for_timeout(1500)
                clicked = find_and_click_category(page, CATEGORY_NAME)
                if not clicked:
                    raise RuntimeError(
                        f"카테고리 '{CATEGORY_NAME}'를 찾지 못했습니다. "
                        "위 후보를 확인해 .env 의 CATEGORY_NAME 을 수정하거나, "
                        "URL의 categoryNo=N 숫자를 CATEGORY_NO 에 넣어주세요."
                    )

            # iframe 등장 + 로드 대기
            try:
                page.wait_for_selector("iframe#mainFrame", timeout=15000)
            except Exception:
                pass
            page.wait_for_timeout(2000)

            # 카테고리 페이지의 frame 재획득
            frame = page.frame(name="mainFrame")
            if frame is None:
                iframe_el = page.query_selector("iframe#mainFrame")
                frame = iframe_el.content_frame() if iframe_el else None
            if frame is None:
                log("mainFrame iframe 없음 — 페이지 자체에서 수집 시도.")
                frame = page

            # 현재 URL 확인 (디버깅)
            try:
                current_url = page.url
                log(f"현재 페이지 URL: {current_url}")
                if frame != page:
                    log(f"mainFrame URL: {frame.url}")
            except Exception:
                pass

            posts = collect_post_links(page, frame, NUM_POSTS)
        except Exception as e:
            log(f"❌ 글 목록 수집 실패: {e}")
            log("브라우저를 열어둡니다. 수동으로 카테고리에 진입해 구조를 살펴보세요.")
            input("Enter를 누르면 종료합니다... ")
            browser.close()
            return 1

        log(f"✓ 목록 {len(posts)}개 확보.")
        print()
        print("─" * 70)
        print(f"  수집한 글 제목 ({len(posts)}개)")
        print("─" * 70)
        for i, item in enumerate(posts, 1):
            print(f"  [{i:2d}] {item['title']}")
        print("─" * 70)
        print()

        # 본문 상세 수집
        detail_page = ctx.new_page()
        ok = 0
        # Windows 경로 길이(260자) 회피: 디렉토리 길이 보고 파일명 줄이기
        base_len = len(str(RAW_POSTS_DIR)) + 1  # + path separator
        # 안전 마진 후 남는 길이 (.json 5자 포함)
        max_name_len = max(8, 240 - base_len)

        for i, item in enumerate(posts, 1):
            try:
                log(f"[{i}/{len(posts)}] 본문 수집: {item['title'][:30]}...")
                detail = fetch_post_detail(detail_page, item["url"])

                # 파일명 만들기 — 경로 길이 안전하게
                slug = slugify(item["title"], maxlen=20)
                filename = f"{i:02d}_{slug}.json"
                if len(filename) > max_name_len:
                    filename = f"{i:02d}.json"  # 최후의 폴백
                out_path = RAW_POSTS_DIR / filename
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(
                    json.dumps(detail, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                ok += 1
            except Exception as e:
                log(f"  ⚠️ 실패: {e}")
            time.sleep(0.8)

        # 제목 목록 요약 파일도 함께 저장
        summary_path = RAW_POSTS_DIR / "_titles.txt"
        summary_path.write_text(
            "\n".join(f"{i:2d}. {p['title']}\n    {p['url']}" for i, p in enumerate(posts, 1)),
            encoding="utf-8",
        )

        log(f"✓ 성공 {ok}/{len(posts)}. 저장: {RAW_POSTS_DIR}")
        log(f"✓ 제목 요약: {summary_path}")
        browser.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
