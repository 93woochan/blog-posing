"""Naver Auto Post — GUI 앱."""
from __future__ import annotations

import builtins
import json
import sys
import threading
from pathlib import Path
from typing import Optional

import customtkinter as ctk
from tkinter import filedialog, messagebox

# frozen exe 대응
if getattr(sys, "frozen", False):
    ROOT_DIR = Path(sys.executable).parent
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))
else:
    ROOT_DIR = Path(__file__).resolve().parent.parent
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

__version__ = "1.0.0"


class StdoutRedirect:
    def __init__(self, callback):
        self._cb = callback

    def write(self, text: str):
        stripped = text.rstrip()
        if stripped:
            self._cb(stripped)

    def flush(self):
        pass


class App(ctk.CTk):

    # ── 카테고리 설정 ─────────────────────────────────────────
    # ready=True 인 카테고리만 글 생성 활성화
    # widget: "entry"(기본) | "dropdown"
    CATEGORY_CONFIGS: dict = {
        "맛집/카페": {
            "ready": True,
            "fields": [
                {"label": "카페/음식점 이름", "key": "cafe_name"},
                {"label": "위치",            "key": "location"},
                {"label": "방문일",          "key": "visit_date"},
                {"label": "메뉴",            "key": "menu"},
                {"label": "한줄평",          "key": "comment"},
            ],
        },
        "패션": {
            "ready": True,
            "fields": [
                {"label": "브랜드/아이템명", "key": "brand_item"},
                {"label": "구매처",          "key": "purchase_place"},
                {"label": "가격",            "key": "price"},
                {"label": "착용 정보",       "key": "fit_info",
                 "placeholder": "예) 165cm / M 착용"},
                {"label": "한줄평",          "key": "comment"},
            ],
        },
        "뷰티": {
            "ready": True,
            "fields": [
                {"label": "제품명",      "key": "product_name"},
                {"label": "브랜드",      "key": "brand"},
                {"label": "구매처/가격", "key": "purchase_price"},
                {"label": "피부타입",    "key": "skin_type",
                 "widget": "dropdown",
                 "options": ["복합성", "건성", "지성", "민감성", "중성"],
                 "default": "복합성"},
                {"label": "한줄평",      "key": "comment"},
            ],
        },
        "셀럽": {"ready": False, "fields": []},
        "여행": {"ready": False, "fields": []},
    }

    def __init__(self):
        super().__init__()
        self.title("은지의 블로그 자동 포스트 도구 ٩(๑❛ᴗ❛๑)۶")
        self.geometry("480x700")
        self.resizable(False, False)

        self.folder_path: Optional[Path] = None
        self.post_ready = False
        self.mode_var = ctk.StringVar(value="self_paid")

        self._build_tabs()
        self._build_version_label()
        self._check_settings_on_start()
        self.after(500, self._install_chromium_bg)

    # ── UI 구성 ──────────────────────────────────────────────

    def _build_version_label(self):
        ctk.CTkLabel(
            self, text=f"v{__version__}  made by woochan",
            text_color="gray40", font=ctk.CTkFont(size=10),
            anchor="e",
        ).place(relx=1.0, rely=1.0, x=-8, y=-6, anchor="se")

    def _build_tabs(self):
        self.tabs = ctk.CTkTabview(self, width=460, height=660)
        self.tabs.pack(padx=10, pady=10, fill="both", expand=True)
        self.tabs.add("글 작성")
        self.tabs.add("설정")
        self._build_write_tab(self.tabs.tab("글 작성"))
        self._build_settings_tab(self.tabs.tab("설정"))

    def _build_write_tab(self, parent):
        # 폴더 선택
        folder_frame = ctk.CTkFrame(parent)
        folder_frame.pack(fill="x", pady=(5, 6))
        self.folder_label = ctk.CTkLabel(
            folder_frame, text="  📁 폴더를 선택하세요", anchor="w", text_color="gray"
        )
        self.folder_label.pack(side="left", fill="x", expand=True, padx=5, pady=8)
        ctk.CTkButton(
            folder_frame, text="찾아보기", width=85, command=self._browse
        ).pack(side="right", padx=8, pady=8)

        # 카테고리 타입 선택
        self.cat_type_var = ctk.StringVar(value="맛집/카페")
        ctk.CTkSegmentedButton(
            parent,
            values=list(self.CATEGORY_CONFIGS.keys()),
            variable=self.cat_type_var,
            command=self._on_cat_type_change,
            font=ctk.CTkFont(size=12),
        ).pack(fill="x", pady=(0, 6))

        # 입력 폼 컨테이너 (카테고리에 따라 내용 교체)
        self.form_container = ctk.CTkFrame(parent)
        self.form_container.pack(fill="x", pady=(0, 6))
        self.entries: dict[str, ctk.CTkEntry | ctk.CTkOptionMenu] = {}
        self._build_form_fields("맛집/카페")

        # 버튼
        self.gen_btn = ctk.CTkButton(
            parent, text="✨  글 생성하기", height=42, command=self._on_generate_click
        )
        self.gen_btn.pack(fill="x", pady=(0, 6))

        self.pub_btn = ctk.CTkButton(
            parent, text="🚀  네이버에 올리기", height=42,
            command=self._publish, state="disabled",
            fg_color="transparent", border_width=2,
            text_color=("gray60", "gray40"),
        )
        self.pub_btn.pack(fill="x", pady=(0, 6))

        # 진행 바
        self.progress = ctk.CTkProgressBar(parent)
        self.progress.pack(fill="x", pady=(0, 4))
        self.progress.set(0)

        # 로그
        self.status_lbl = ctk.CTkLabel(parent, text="대기 중", text_color="gray", anchor="w")
        self.status_lbl.pack(fill="x", padx=4)
        self.log_box = ctk.CTkTextbox(parent, height=110, state="disabled",
                                       font=ctk.CTkFont(size=11))
        self.log_box.pack(fill="x", pady=(2, 0))

    def _build_settings_tab(self, parent):
        ctk.CTkLabel(
            parent, text="네이버 계정 설정",
            font=ctk.CTkFont(size=15, weight="bold"), anchor="w"
        ).pack(fill="x", padx=10, pady=(15, 10))

        fields = [
            ("Gemini API 키", "gemini_key", True),
            ("네이버 ID",     "naver_id",   False),
            ("네이버 PW",     "naver_pw",   True),
            ("블로그 ID",     "blog_id",    False),
            ("카테고리",      "category",   False),
        ]
        self.setting_entries: dict[str, ctk.CTkEntry] = {}
        for label, key, secret in fields:
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=5)
            ctk.CTkLabel(row, text=label, width=80, anchor="w").pack(side="left")
            e = ctk.CTkEntry(row, show="●" if secret else "", placeholder_text=label)
            e.pack(side="left", fill="x", expand=True)
            self.setting_entries[key] = e

        self._load_settings()

        ctk.CTkButton(
            parent, text="저장", height=38, command=self._save_settings
        ).pack(fill="x", padx=10, pady=(15, 0))

        self.settings_status = ctk.CTkLabel(parent, text="", text_color="gray")
        self.settings_status.pack(pady=6)

    # ── 폼 필드 빌더 ────────────────────────────────────────

    def _build_form_fields(self, cat_type: str):
        """카테고리에 맞는 폼 필드를 form_container 안에 그린다."""
        for w in self.form_container.winfo_children():
            w.destroy()
        self.entries.clear()

        cfg = self.CATEGORY_CONFIGS.get(cat_type, {})
        if not cfg.get("ready"):
            ctk.CTkLabel(
                self.form_container,
                text=f"🚧  {cat_type} 카테고리는 준비 중입니다",
                text_color="gray", font=ctk.CTkFont(size=13),
                anchor="center",
            ).pack(pady=28)
            return

        for field in cfg["fields"]:
            label       = field["label"]
            key         = field["key"]
            widget_type = field.get("widget", "entry")

            row = ctk.CTkFrame(self.form_container, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=3)
            ctk.CTkLabel(row, text=label, width=110, anchor="w").pack(side="left")

            if widget_type == "dropdown":
                options = field.get("options", [])
                default = field.get("default", options[0] if options else "")
                w = ctk.CTkOptionMenu(row, values=options)
                w.set(default)
                w.pack(side="left", fill="x", expand=True)
            else:
                placeholder = field.get("placeholder", label)
                w = ctk.CTkEntry(row, placeholder_text=placeholder)
                w.pack(side="left", fill="x", expand=True)

            self.entries[key] = w

        # 모드 (내돈내산 / 협찬)
        mode_row = ctk.CTkFrame(self.form_container, fg_color="transparent")
        mode_row.pack(fill="x", padx=10, pady=(4, 10))
        ctk.CTkLabel(mode_row, text="모드", width=110, anchor="w").pack(side="left")
        self.mode_var = ctk.StringVar(value="self_paid")
        ctk.CTkRadioButton(
            mode_row, text="내돈내산", variable=self.mode_var, value="self_paid"
        ).pack(side="left", padx=(0, 12))
        ctk.CTkRadioButton(
            mode_row, text="협찬", variable=self.mode_var, value="sponsored"
        ).pack(side="left")

    def _on_cat_type_change(self, cat_type: str):
        self._build_form_fields(cat_type)
        cfg = self.CATEGORY_CONFIGS.get(cat_type, {})
        if cfg.get("ready"):
            self.gen_btn.configure(state="normal")
            self._set_status("준비 완료")
        else:
            self.gen_btn.configure(state="disabled")
            self._set_status(f"{cat_type} — 준비 중")

    # ── 설정 ────────────────────────────────────────────────

    def _load_settings(self):
        env_path = ROOT_DIR / ".env"
        if not env_path.exists():
            return
        env = {}
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
        mapping = {"GEMINI_API_KEY": "gemini_key",
                   "NAVER_ID": "naver_id", "NAVER_PW": "naver_pw",
                   "BLOG_ID": "blog_id", "CATEGORY_NAME": "category"}
        for env_key, ui_key in mapping.items():
            val = env.get(env_key, "")
            if val:
                self.setting_entries[ui_key].delete(0, "end")
                self.setting_entries[ui_key].insert(0, val)

    def _save_settings(self):
        gemini_key = self.setting_entries["gemini_key"].get().strip()
        naver_id   = self.setting_entries["naver_id"].get().strip()
        naver_pw   = self.setting_entries["naver_pw"].get().strip()
        blog_id    = self.setting_entries["blog_id"].get().strip() or naver_id
        category   = self.setting_entries["category"].get().strip() or "맛집/카페"

        env_path = ROOT_DIR / ".env"
        lines = []
        existing: dict[str, str] = {}
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    k, v = stripped.split("=", 1)
                    existing[k.strip()] = v.strip()
                else:
                    lines.append(line)

        if gemini_key:
            existing["GEMINI_API_KEY"] = gemini_key
        existing["NAVER_ID"] = naver_id
        existing["NAVER_PW"] = naver_pw
        existing["BLOG_ID"]  = blog_id
        existing["CATEGORY_NAME"] = category

        out_lines = lines + [f"{k}={v}" for k, v in existing.items()]
        env_path.write_text("\n".join(out_lines), encoding="utf-8")

        self.settings_status.configure(text="✓ 저장됨", text_color="green")
        self.after(2000, lambda: self.settings_status.configure(text=""))

        import importlib
        import src.config as cfg
        from dotenv import load_dotenv
        load_dotenv(env_path, override=True)
        importlib.reload(cfg)

    def _check_settings_on_start(self):
        env_path = ROOT_DIR / ".env"
        if not env_path.exists():
            self.tabs.set("설정")
            return
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("NAVER_ID=") and line.split("=", 1)[1].strip():
                return
        self.tabs.set("설정")

    # ── 폴더 선택 ────────────────────────────────────────────

    def _browse(self):
        folder = filedialog.askdirectory(title="사진 폴더 선택")
        if not folder:
            return
        self.folder_path = Path(folder)
        self.folder_label.configure(
            text=f"  📁 {self.folder_path.name}", text_color="white"
        )
        self._load_info_txt()

        if (self.folder_path / "generated_post.json").exists():
            self.post_ready = True
            self.pub_btn.configure(
                state="normal", fg_color=["#2d6a4f", "#1b4332"],
                border_width=0, text_color="white",
            )
            self._set_status("generated_post.json 감지 — 바로 올릴 수 있어요.")
        else:
            self.post_ready = False
            self.pub_btn.configure(
                state="disabled", fg_color="transparent",
                border_width=2, text_color=("gray60", "gray40"),
            )
            self._set_status("준비 완료")

    def _load_info_txt(self):
        if not self.folder_path:
            return
        info_path = self.folder_path / "info.txt"
        if not info_path.exists():
            return
        cat_type = self.cat_type_var.get()
        fields = self.CATEGORY_CONFIGS.get(cat_type, {}).get("fields", [])
        label_to_key = {f["label"]: f["key"] for f in fields}
        for line in info_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if ":" in line:
                k, v = line.split(":", 1)
                key = label_to_key.get(k.strip())
                if key and key in self.entries:
                    widget = self.entries[key]
                    if isinstance(widget, ctk.CTkOptionMenu):
                        widget.set(v.strip())
                    else:
                        widget.delete(0, "end")
                        widget.insert(0, v.strip())

    def _save_info_txt(self):
        if not self.folder_path:
            return
        cat_type = self.cat_type_var.get()
        fields = self.CATEGORY_CONFIGS.get(cat_type, {}).get("fields", [])
        lines = []
        for field in fields:
            widget = self.entries.get(field["key"])
            if widget:
                v = widget.get().strip()
                if v:
                    lines.append(f"{field['label']}: {v}")
        (self.folder_path / "info.txt").write_text("\n".join(lines), encoding="utf-8")

    # ── 글 생성 ──────────────────────────────────────────────

    def _on_generate_click(self):
        if not self.folder_path:
            messagebox.showwarning("알림", "사진 폴더를 먼저 선택해주세요.")
            return

        from src.post import list_photos
        photos = list_photos(self.folder_path)
        count = len(photos)

        confirmed = messagebox.askyesno(
            "분석하시겠습니까?",
            f"우찬이의 토큰값이 나갑니다.\n"
            f"낮은 화질의 사진인지 확인해주세요.\n\n"
            f"사진 {count}장 감지됨",
        )
        if not confirmed:
            return

        self._save_info_txt()
        self.gen_btn.configure(state="disabled", text="생성 중...")
        self.pub_btn.configure(state="disabled")
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self._set_status("Gemini로 글 생성 중...")

        threading.Thread(target=self._generate_worker, daemon=True).start()

    def _generate_worker(self):
        old_stdout = sys.stdout
        sys.stdout = StdoutRedirect(self._log)
        try:
            from src.post import generate_post
            post = generate_post(self.folder_path, self.mode_var.get())
            out = self.folder_path / "generated_post.json"
            out.write_text(json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8")
            title = post.get("title", "")
            tags = " ".join(f"#{t}" for t in post.get("tags", []))
            self._log(f"\n✓ 생성 완료!")
            self._log(f"  제목: {title}")
            self._log(f"  태그: {tags}")
            self.post_ready = True
            self.after(0, self._on_generated)
        except Exception as e:
            self._log(f"\n❌ 오류: {e}")
            self.after(0, self._reset_gen_btn)
        finally:
            sys.stdout = old_stdout

    def _on_generated(self):
        self._reset_gen_btn()
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(1)
        self._set_status("생성 완료! 아래 버튼으로 올려보세요.")
        self.pub_btn.configure(
            state="normal", fg_color=["#2d6a4f", "#1b4332"],
            border_width=0, text_color="white",
        )

    def _reset_gen_btn(self):
        self.gen_btn.configure(state="normal", text="✨  글 생성하기")
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(0)

    # ── 네이버 포스팅 ────────────────────────────────────────

    def _publish(self):
        if not self.post_ready:
            messagebox.showwarning("알림", "먼저 글을 생성해주세요.")
            return
        self.pub_btn.configure(state="disabled", text="작성 중... (브라우저 닫으면 완료)")
        threading.Thread(target=self._publish_worker, daemon=True).start()

    def _publish_worker(self):
        old_stdout = sys.stdout
        old_input = builtins.input
        sys.stdout = StdoutRedirect(self._log)

        def gui_input(prompt=""):
            event = threading.Event()
            self.after(0, lambda: self._show_input_dialog(prompt, event))
            event.wait()
            return ""

        builtins.input = gui_input
        try:
            import src.publisher as pub_mod
            import importlib
            importlib.reload(pub_mod)

            old_argv = sys.argv
            sys.argv = ["publisher", str(self.folder_path)]
            result = pub_mod.main()
            sys.argv = old_argv

            if result == 0:
                self.after(0, lambda: messagebox.showinfo(
                    "완료", "글 작성 완료!\n네이버 블로그에서 확인 후 발행해주세요."
                ))
        except SystemExit:
            pass
        except Exception as e:
            self._log(f"\n❌ {e}")
        finally:
            sys.stdout = old_stdout
            builtins.input = old_input
            self.after(0, lambda: self.pub_btn.configure(
                state="normal", text="🚀  네이버에 올리기"
            ))

    def _show_input_dialog(self, prompt: str, event: threading.Event):
        messagebox.showinfo("확인 필요", prompt or "브라우저를 확인 후 확인을 누르세요.")
        event.set()

    # ── 유틸 ─────────────────────────────────────────────────

    def _log(self, msg: str):
        self.after(0, self._log_append, msg)

    def _log_append(self, msg: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.configure(state="disabled")
        self.log_box.see("end")

    def _set_status(self, msg: str):
        self.after(0, lambda: self.status_lbl.configure(text=msg))

    def _install_chromium_bg(self):
        threading.Thread(target=self._install_chromium, daemon=True).start()

    def _install_chromium(self):
        import os
        self._set_status("Chromium 확인 중...")

        if getattr(sys, "frozen", False):
            # frozen exe: sys.executable = 자기 자신이므로 subprocess 설치 불가
            # ms-playwright 폴더에 Chromium이 있는지 확인만 함
            local = os.environ.get("LOCALAPPDATA", "")
            ms_pw = Path(local) / "ms-playwright"
            has_chromium = ms_pw.exists() and any(
                d.is_dir() and d.name.startswith("chromium")
                for d in ms_pw.iterdir()
            ) if ms_pw.exists() else False

            if not has_chromium:
                self._log("⚠ Chromium 미설치. 같은 폴더의 크로미움_설치.bat을 먼저 실행하세요.")
            self._set_status("준비 완료")
            return

        # 개발 환경: playwright install 실행
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True, text=True,
        )
        if "download" in (result.stdout + result.stderr).lower():
            self._log("✓ Chromium 설치 완료")
        self._set_status("준비 완료")


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
