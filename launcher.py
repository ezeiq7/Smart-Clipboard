# launcher.py
import tkinter as tk
import storage
import clipboard
from theme import *


class QuickPasteLauncher:
    # Width / height of the floating window
    WIN_W = 500
    WIN_H = 360
    MAX_CLIPS = 15

    def __init__(self, tk_root):
        self._root        = tk_root
        self._win         = None
        self._prev_hwnd   = None
        self._clips       = []
        self._selected    = 0
        self._search_var  = None
        self._list_frame  = None

    # ── Public entry point ─────────────────────────────────────────────────

    def open(self, prev_hwnd: int):
        """Called from the main thread via root.after()."""
        if self._win and self._win.winfo_exists():
            self._close()
            return
        self._prev_hwnd = prev_hwnd
        self._build_window()
        self._load_clips("")
        self._win.lift()
        self._win.focus_force()
        self._search_entry.focus_set()

    # ── Window construction ────────────────────────────────────────────────

    def _build_window(self):
        win = tk.Toplevel(self._root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=BORDER)

        # Position centred on whichever monitor the cursor is on
        try:
            import win32api
            cx, cy = win32api.GetCursorPos()
            mon = win32api.MonitorFromPoint((cx, cy), win32api.MONITOR_DEFAULTTONEAREST)
            info = win32api.GetMonitorInfo(mon)
            mx, my, mw, mh = (*info["Monitor"][:2],
                              info["Monitor"][2] - info["Monitor"][0],
                              info["Monitor"][3] - info["Monitor"][1])
            x = mx + (mw - self.WIN_W) // 2
            y = my + (mh - self.WIN_H) // 2 - 60
        except Exception:
            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
            x  = (sw - self.WIN_W) // 2
            y  = (sh - self.WIN_H) // 2 - 60
        win.geometry(f"{self.WIN_W}x{self.WIN_H}+{x}+{y}")

        # 1px border effect via outer/inner frames
        outer = tk.Frame(win, bg=BORDER, padx=1, pady=1)
        outer.pack(fill="both", expand=True)
        inner = tk.Frame(outer, bg=BG)
        inner.pack(fill="both", expand=True)

        # ── Accent top strip ──────────────────────────────────────────────
        tk.Frame(inner, bg=ACCENT, height=3).pack(fill="x")

        # ── Search bar ────────────────────────────────────────────────────
        search_wrap = tk.Frame(inner, bg=HEADER_BG, padx=12, pady=10)
        search_wrap.pack(fill="x")

        icon = tk.Label(search_wrap, text="⌕", bg=HEADER_BG, fg=ACCENT,
                        font=("Segoe UI", 13))
        icon.pack(side="left", padx=(0, 8))

        self._search_var = tk.StringVar()
        self._search_var.trace("w", self._on_search_change)
        self._search_entry = tk.Entry(
            search_wrap, textvariable=self._search_var,
            font=("Segoe UI", 11), relief="flat", bd=0,
            bg=HEADER_BG, fg=TEXT_DARK, insertbackground=ACCENT,
            width=38
        )
        self._search_entry.pack(side="left", fill="x", expand=True)

        hint_lbl = tk.Label(search_wrap, text="Ctrl+Shift+V",
                            bg=BORDER, fg=TEXT_GRAY,
                            font=("Segoe UI", 8), padx=6, pady=2)
        hint_lbl.pack(side="right")

        # ── Separator ─────────────────────────────────────────────────────
        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x")

        # ── Results list ──────────────────────────────────────────────────
        self._list_frame = tk.Frame(inner, bg=BG)
        self._list_frame.pack(fill="both", expand=True, padx=4, pady=4)

        # ── Footer ────────────────────────────────────────────────────────
        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x")
        footer = tk.Frame(inner, bg=HEADER_BG, padx=12, pady=6)
        footer.pack(fill="x")
        tk.Label(footer, text="↑↓  navigate", bg=HEADER_BG, fg=TEXT_GRAY,
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 14))
        tk.Label(footer, text="Enter  paste", bg=HEADER_BG, fg=TEXT_GRAY,
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 14))
        tk.Label(footer, text="Esc  dismiss", bg=HEADER_BG, fg=TEXT_GRAY,
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 14))
        tk.Label(footer, text="#tag  filter by tag", bg=HEADER_BG, fg=TEXT_GRAY,
                 font=("Segoe UI", 8)).pack(side="left")

        # ── Key bindings ──────────────────────────────────────────────────
        win.bind("<Escape>", lambda e: self._close())
        win.bind("<Return>", lambda e: self._confirm_paste())
        win.bind("<Up>",     lambda e: (self._move_selection(-1), "break"))
        win.bind("<Down>",   lambda e: (self._move_selection(1),  "break"))
        win.bind("<FocusOut>", self._on_focus_out)

        self._win = win

    # ── Data / filtering ──────────────────────────────────────────────────

    def _on_search_change(self, *_):
        self._load_clips(self._search_var.get() if self._search_var else "")

    def _load_clips(self, query: str):
        all_clips = storage.load_clips()
        # Pinned first, then rest — preserve original sort order within each group
        pinned     = [c for c in all_clips if c.get("pinned")]
        unpinned   = [c for c in all_clips if not c.get("pinned")]
        candidates = pinned + unpinned

        if query.strip().startswith("#"):
            tag_query = query.strip()[1:].lower()
            self._clips = [
                c for c in candidates
                if (c.get("tag") or "").lower().startswith(tag_query)
            ][: self.MAX_CLIPS]
        elif query.strip():
            scored = [(self._score(query, c["text"]), c) for c in candidates]
            scored = [(s, c) for s, c in scored if s > 0]
            scored.sort(key=lambda x: -x[0])
            self._clips = [c for _, c in scored][: self.MAX_CLIPS]
        else:
            self._clips = candidates[: self.MAX_CLIPS]

        self._selected = 0
        self._render_list()

    def _score(self, query: str, text: str) -> int:
        q  = query.lower()
        t  = text.lower()
        # Exact substring → highest priority
        if q in t:
            return 100 + max(0, 50 - t.index(q))
        # Sequential character match (fuzzy)
        qi = 0
        sc = 0
        for ch in t:
            if qi < len(q) and ch == q[qi]:
                qi += 1
                sc += 1
        return sc if qi == len(q) else 0

    # ── List rendering ────────────────────────────────────────────────────

    def _render_list(self):
        for w in self._list_frame.winfo_children():
            w.destroy()

        if not self._clips:
            tk.Label(self._list_frame,
                     text="No clips match your search",
                     bg=BG, fg=TEXT_GRAY,
                     font=("Segoe UI", 10)).pack(pady=30)
            return

        for i, clip in enumerate(self._clips):
            self._make_row(i, clip)

    def _make_row(self, idx: int, clip: dict):
        selected = idx == self._selected
        row_bg   = ACCENT     if selected else (PINNED_ROW if clip.get("pinned") else WHITE)
        row_fg   = "#FFFFFF"  if selected else TEXT_DARK

        row = tk.Frame(self._list_frame, bg=row_bg, cursor="hand2")
        row.pack(fill="x", padx=2, pady=1)

        # Pin indicator
        pin_lbl = tk.Label(row, text="📌" if clip.get("pinned") else "   ",
                           bg=row_bg, fg=PIN if not selected else "#FFFFFF",
                           font=("Segoe UI", 9), padx=6, pady=6)
        pin_lbl.pack(side="left")

        # Clip type icon
        is_image = clip.get("type") == "image"
        type_lbl = tk.Label(row,
                            text="🖼" if is_image else "◆",
                            bg=row_bg, fg=row_fg,
                            font=("Segoe UI", 9), padx=4)
        type_lbl.pack(side="left")

        # Preview text
        if is_image:
            preview = "Image"
        else:
            raw = clip["text"].replace("\n", " ").replace("\t", " ")
            preview = raw[:58] + "…" if len(raw) > 58 else raw

        text_lbl = tk.Label(row, text=preview,
                            bg=row_bg, fg=row_fg,
                            font=("Segoe UI", 10),
                            anchor="w", padx=4)
        text_lbl.pack(side="left", fill="x", expand=True)

        # Tag badge (right side)
        tag = clip.get("tag")
        if tag:
            tag_color = get_tag_color(tag) if not selected else "#FFFFFF"
            tag_lbl = tk.Label(row, text=f" {tag} ",
                               bg=row_bg, fg=tag_color,
                               font=("Segoe UI", 8, "bold"), padx=6, pady=4)
            tag_lbl.pack(side="right", padx=(0, 6))

        # Click on any part of the row → select + paste
        for widget in (row, pin_lbl, type_lbl, text_lbl):
            widget.bind("<Button-1>", lambda e, i=idx: self._click_row(i))
        if tag:
            tag_lbl.bind("<Button-1>", lambda e, i=idx: self._click_row(i))

        # Hover highlight (only when not selected)
        if not selected:
            hover_bg = "#2F2F4A"
            for widget in (row, pin_lbl, type_lbl, text_lbl):
                widget.bind("<Enter>", lambda e, r=row, wl=(row, pin_lbl, type_lbl, text_lbl):
                            [w.config(bg=hover_bg) for w in wl])
                widget.bind("<Leave>", lambda e, r=row, wl=(row, pin_lbl, type_lbl, text_lbl), bg=row_bg:
                            [w.config(bg=bg) for w in wl])

    # ── Navigation & selection ─────────────────────────────────────────────

    def _move_selection(self, direction: int):
        if not self._clips:
            return
        self._selected = (self._selected + direction) % len(self._clips)
        self._render_list()

    def _click_row(self, idx: int):
        self._selected = idx
        self._confirm_paste()

    # ── Paste logic ───────────────────────────────────────────────────────

    def _confirm_paste(self):
        if not self._clips or self._selected >= len(self._clips):
            return
        clip = self._clips[self._selected]
        self._close()
        self._root.after(80, lambda: self._do_paste(clip))

    def _do_paste(self, clip: dict):
        # 1. Set clipboard content
        if clip.get("type") == "image":
            clipboard.set_clipboard_image(clip["text"].strip())
        else:
            clipboard.set_clipboard(clip["text"].strip())

        # 2. Restore focus to the window that was active before the launcher
        if self._prev_hwnd:
            try:
                import win32gui
                win32gui.SetForegroundWindow(self._prev_hwnd)
            except Exception:
                pass

        # 3. Simulate Ctrl+V after focus has settled
        self._root.after(80, self._simulate_paste)

    def _simulate_paste(self):
        try:
            from pynput.keyboard import Controller, Key
            kb = Controller()
            kb.press(Key.ctrl)
            kb.press('v')
            kb.release('v')
            kb.release(Key.ctrl)
        except Exception:
            pass

    # ── Window lifecycle ──────────────────────────────────────────────────

    def _close(self):
        if self._win and self._win.winfo_exists():
            self._win.destroy()
        self._win = None

    def _on_focus_out(self, event):
        self._root.after(120, self._check_focus)

    def _check_focus(self):
        if not (self._win and self._win.winfo_exists()):
            return
        try:
            focused = self._win.focus_get()
            if focused is None:
                self._close()
        except Exception:
            self._close()
