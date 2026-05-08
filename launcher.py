# launcher.py
import tkinter as tk
import storage
import clipboard
from theme import *

SMART_PASTE_OPTIONS = [
    ("Plain",      "As copied"),
    ("Clean",      "Fix spacing & quotes"),
    ("No Breaks",  "Remove line breaks"),
    ("Bullets",    "Bullet list"),
    ("UPPER",      "UPPERCASE"),
    ("lower",      "lowercase"),
]


def _transform(text: str, mode: str) -> str:
    if mode == "Plain":
        return text
    if mode == "Clean":
        import re
        t = text
        t = re.sub(r'[\u2018\u2019]', "'", t)   # smart single quotes
        t = re.sub(r'[\u201c\u201d]', '"', t)   # smart double quotes
        t = re.sub(r'\u2013|\u2014', '-', t)    # em/en dashes
        t = re.sub(r'[ \t]+', ' ', t)           # collapse spaces
        t = re.sub(r'\n{3,}', '\n\n', t)        # max 2 newlines
        return t.strip()
    if mode == "No Breaks":
        return " ".join(text.split())
    if mode == "Bullets":
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        return "\n".join(f"• {l}" for l in lines)
    if mode == "UPPER":
        return text.upper()
    if mode == "lower":
        return text.lower()
    return text


def _suggest_format(text: str) -> int:
    """Return the SMART_PASTE_OPTIONS index that best fits the clip content."""
    import re
    # 3+ delimited items → Bullets (index 3)
    for delim in (",", ";"):
        if delim in text:
            parts = [p.strip() for p in text.split(delim) if p.strip()]
            if len(parts) >= 3:
                return 3
    # All-uppercase text → lower (index 5)
    letters = [c for c in text if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        return 5
    # Smart quotes, em/en dashes, or multiple spaces → Clean (index 1)
    if re.search(r'[\u2018\u2019\u201c\u201d\u2013\u2014]|  ', text):
        return 1
    # 3 or more line breaks → No Breaks (index 2)
    if text.count("\n") >= 3:
        return 2
    return 0


class QuickPasteLauncher:
    WIN_W    = 500
    WIN_H    = 360
    MAX_CLIPS = 200
    ROW_H    = 34   # fixed pixel height per clip row
    _VBUF    = 10   # rows to keep rendered above/below the visible viewport

    def __init__(self, tk_root, suppress_fn=None):
        self._root            = tk_root
        self._suppress_fn     = suppress_fn
        self._win             = None
        self._prev_hwnd       = None
        self._clips           = []
        self._selected        = 0
        self._search_var      = None
        self._list_frame      = None
        self._smart_bar       = None
        self._smart_opt_idx   = 0
        self._smart_mode      = False
        self._help_card       = None
        self._help_after      = None
        self._render_after    = None
        self._last_nav_time   = 0.0
        self._row_widgets     = {}   # dict: idx -> (row, pin_lbl, type_lbl, text_lbl, tag_lbl|None, clip)

    # ── Public entry point ─────────────────────────────────────────────────

    def open(self, prev_hwnd: int):
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

        try:
            import win32api
            cx, cy = win32api.GetCursorPos()
            mon  = win32api.MonitorFromPoint((cx, cy), win32api.MONITOR_DEFAULTTONEAREST)
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

        outer = tk.Frame(win, bg=BORDER, padx=1, pady=1)
        outer.pack(fill="both", expand=True)
        inner = tk.Frame(outer, bg=BG)
        inner.pack(fill="both", expand=True)

        tk.Frame(inner, bg=ACCENT, height=3).pack(fill="x")

        # ── Search bar ────────────────────────────────────────────────────
        search_wrap = tk.Frame(inner, bg=HEADER_BG, padx=12, pady=10)
        search_wrap.pack(fill="x")

        tk.Label(search_wrap, text="⌕", bg=HEADER_BG, fg=ACCENT,
                 font=("Segoe UI", 13)).pack(side="left", padx=(0, 8))

        self._search_var = tk.StringVar()
        self._search_var.trace("w", self._on_search_change)
        self._search_entry = tk.Entry(
            search_wrap, textvariable=self._search_var,
            font=("Segoe UI", 11), relief="flat", bd=0,
            bg=HEADER_BG, fg=TEXT_DARK, insertbackground=ACCENT,
            width=38
        )
        self._search_entry.pack(side="left", fill="x", expand=True)

        tk.Label(search_wrap, text="Ctrl+Shift+V",
                 bg=BORDER, fg=TEXT_GRAY,
                 font=("Segoe UI", 8), padx=6, pady=2).pack(side="right")

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x")

        # ── Results list ──────────────────────────────────────────────────
        list_container = tk.Frame(inner, bg=BG)
        list_container.pack(fill="both", expand=True, padx=4, pady=4)

        self._canvas = tk.Canvas(list_container, bg=BG, highlightthickness=0, bd=0)
        self._canvas.pack(side="left", fill="both", expand=True)

        # ── Custom scrollbar (avoids native Scrollbar drag bugs) ─────────────
        sb_track = tk.Frame(list_container, bg="#2A2A3F", width=8)
        sb_track.pack(side="right", fill="y")
        sb_track.pack_propagate(False)
        self._sb_track = sb_track
        self._sb_thumb = tk.Frame(sb_track, bg=ACCENT, cursor="hand2")

        def _update_sb(first, last):
            first, last = float(first), float(last)
            if last - first >= 1.0:
                self._sb_thumb.place_forget()
                return
            h = sb_track.winfo_height()
            self._sb_thumb.place(x=0, y=int(first * h),
                                 width=8, height=max(20, int((last - first) * h)))

        def _sb_press(e):
            pass  # anchor recorded implicitly via y_root in motion

        def _sb_motion(e):
            h = self._sb_track.winfo_height()
            if h <= 0:
                return
            ratio = (e.y_root - self._sb_track.winfo_rooty()) / h
            self._canvas.yview_moveto(max(0.0, min(1.0, ratio)))

        def _sb_release(e):
            pass  # no momentum to cancel

        for w in (sb_track, self._sb_thumb):
            w.bind("<Button-1>",       _sb_press)
            w.bind("<B1-Motion>",      _sb_motion)
            w.bind("<ButtonRelease-1>", _sb_release)

        self._list_frame = tk.Frame(self._canvas, bg=BG)
        self._canvas_window = self._canvas.create_window((0, 0), window=self._list_frame, anchor="nw")

        # With virtual scrolling the scrollregion is managed explicitly;
        # only keep the width-sync on configure events.
        self._list_frame.bind("<Configure>", lambda _e:
            self._canvas.itemconfig(self._canvas_window, width=self._canvas.winfo_width()))
        self._canvas.bind("<Configure>", lambda e: (
            self._canvas.itemconfig(self._canvas_window, width=e.width),
            self._update_virtual_rows(),
        ))

        def _on_wheel(e):
            self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
            self._update_virtual_rows()

        self._canvas.bind("<MouseWheel>", _on_wheel)
        win.bind("<MouseWheel>", _on_wheel)

        # Trigger virtual-row update whenever the view position changes.
        def _on_yscroll(first, last):
            _update_sb(first, last)
            self._update_virtual_rows()

        self._canvas.configure(yscrollcommand=_on_yscroll)

        # ── Smart paste bar (hidden until Enter pressed) ──────────────────
        self._smart_bar = tk.Frame(inner, bg="#1E1E30")
        self._smart_bar_btns = []
        self._build_smart_bar()

        # ── Footer ────────────────────────────────────────────────────────
        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x")
        self._footer = tk.Frame(inner, bg=HEADER_BG, padx=12, pady=6)
        self._footer.pack(fill="x")
        self._footer_hint = tk.Label(self._footer, text="↑↓  navigate    Enter  smart paste    click  paste plain    Esc  dismiss",
                                     bg=HEADER_BG, fg=TEXT_GRAY, font=("Segoe UI", 8))
        self._footer_hint.pack(side="left")
        help_btn = tk.Label(self._footer, text="?",
                            font=("Segoe UI", 9, "bold"),
                            bg=BORDER, fg=TEXT_GRAY,
                            padx=7, pady=2, cursor="hand2")
        help_btn.pack(side="right")
        help_btn.bind("<Enter>", lambda e: self._schedule_help(help_btn))
        help_btn.bind("<Leave>", lambda e: self._cancel_help())

        # ── Key bindings ──────────────────────────────────────────────────
        win.bind("<Escape>",  lambda e: self._on_escape())
        win.bind("<Return>",  lambda e: self._on_enter())
        win.bind("<Up>",      lambda e: self._on_up())
        win.bind("<Down>",    lambda e: self._on_down())
        win.bind("<Left>",    lambda e: self._smart_nav(-1))
        win.bind("<Right>",   lambda e: self._smart_nav(+1))
        win.bind("<FocusOut>", self._on_focus_out)

        self._win = win

    def _build_smart_bar(self):
        tk.Frame(self._smart_bar, bg=BORDER, height=1).pack(fill="x")
        label = tk.Label(self._smart_bar, text="Smart Paste  —  choose format:",
                         bg="#1E1E30", fg=TEXT_GRAY,
                         font=("Segoe UI", 8), pady=4)
        label.pack()

        btn_row = tk.Frame(self._smart_bar, bg="#1E1E30")
        btn_row.pack(pady=(0, 6))

        self._smart_bar_btns = []
        for i, (name, tip) in enumerate(SMART_PASTE_OPTIONS):
            btn = tk.Label(btn_row, text=name,
                           font=("Segoe UI", 8, "bold"),
                           padx=10, pady=5, cursor="hand2")
            btn.pack(side="left", padx=3)
            btn.bind("<Button-1>", lambda e, idx=i: self._smart_click(idx))
            self._smart_bar_btns.append(btn)

        hint = tk.Label(self._smart_bar,
                        text="← → navigate    Enter confirm    Esc cancel",
                        bg="#1E1E30", fg=TEXT_GRAY, font=("Segoe UI", 7), pady=2)
        hint.pack()

    def _refresh_smart_bar(self):
        for i, btn in enumerate(self._smart_bar_btns):
            if i == self._smart_opt_idx:
                btn.config(bg=ACCENT, fg="white")
            else:
                btn.config(bg=BORDER, fg=TEXT_DARK)

    # ── Data / filtering ──────────────────────────────────────────────────

    def _on_search_change(self, *_):
        self._hide_smart_bar()
        self._load_clips(self._search_var.get() if self._search_var else "")

    def _load_clips(self, query: str):
        from datetime import datetime
        def _date_key(c):
            try:
                return datetime.strptime(c.get("date", ""), "%d %b %Y, %H:%M")
            except Exception:
                return datetime.min
        all_clips  = sorted(storage.load_clips(), key=_date_key, reverse=True)
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
            q_words        = query.strip().lower().split()
            wants_template = any("template".startswith(w) for w in q_words if len(w) >= 3)
            wants_hotkey   = any("hotkey".startswith(w)   for w in q_words if len(w) >= 3)
            scored = []
            for c in candidates:
                s = self._score(query, c["text"])
                if s == 0 and wants_template and c.get("template"):
                    s = 50
                if s == 0 and wants_hotkey and c.get("hotkey_slot") is not None:
                    s = 50
                if s > 0:
                    scored.append((s, c))
            scored.sort(key=lambda x: -x[0])
            self._clips = [c for _, c in scored][: self.MAX_CLIPS]
        else:
            self._clips = candidates[: self.MAX_CLIPS]

        self._selected = 0
        self._render_list()

    def _score(self, query: str, text: str) -> int:
        q = query.lower()
        t = text.lower()
        # Exact substring — highest priority
        if q in t:
            return 200 + max(0, 50 - t.index(q))
        # All individual words appear somewhere in the text
        words = [w for w in q.split() if w]
        if words and all(w in t for w in words):
            return 100
        return 0

    # ── List rendering ────────────────────────────────────────────────────

    def _render_list(self):
        # Destroy all currently rendered rows.
        for entry in self._row_widgets.values():
            entry[0].destroy()
        self._row_widgets = {}
        # Also clear any non-row children (e.g. the empty-state label).
        for w in self._list_frame.winfo_children():
            w.destroy()
        self._canvas.yview_moveto(0)

        if not self._clips:
            tk.Label(self._list_frame,
                     text="No clips match your search",
                     bg=BG, fg=TEXT_GRAY,
                     font=("Segoe UI", 10)).pack(pady=30)
            self._canvas.config(scrollregion=(0, 0, self._canvas.winfo_width(), 80))
            return

        total_h = len(self._clips) * self.ROW_H
        self._list_frame.config(height=total_h)
        self._canvas.itemconfig(self._canvas_window, height=total_h)
        self._canvas.config(scrollregion=(0, 0, self._canvas.winfo_width(), total_h))
        # Defer to allow the canvas to settle before measuring the viewport.
        self._canvas.after(1, self._update_virtual_rows)

    def _update_virtual_rows(self):
        """Create rows entering the viewport and destroy rows that have left it."""
        if not self._clips:
            return
        canvas_h = self._canvas.winfo_height()
        if canvas_h <= 1:
            # Canvas not yet sized — retry once it is.
            self._canvas.after(20, self._update_virtual_rows)
            return

        total_h = len(self._clips) * self.ROW_H
        top_frac, bot_frac = self._canvas.yview()
        first_vis = max(0, int(top_frac * total_h / self.ROW_H) - self._VBUF)
        last_vis  = min(len(self._clips) - 1,
                        int(bot_frac * total_h / self.ROW_H) + self._VBUF)

        needed = set(range(first_vis, last_vis + 1))
        current = set(self._row_widgets.keys())

        # Destroy rows that scrolled out of the buffer zone.
        for idx in current - needed:
            self._row_widgets[idx][0].destroy()
            del self._row_widgets[idx]

        # Create rows that scrolled into the buffer zone.
        for idx in sorted(needed - current):
            self._make_row(idx, self._clips[idx])

    def _update_highlight(self, old_idx: int, new_idx: int):
        """Recolor only the two changed rows — no widget rebuild needed."""
        for idx in (old_idx, new_idx):
            if idx not in self._row_widgets:
                continue
            row, pin_lbl, type_lbl, text_lbl, tag_lbl, clip = self._row_widgets[idx]
            selected = idx == new_idx
            row_bg = ACCENT if selected else (PINNED_ROW if clip.get("pinned") else WHITE)
            row_fg = "#FFFFFF" if selected else TEXT_DARK
            for w in (row, pin_lbl, type_lbl, text_lbl):
                w.config(bg=row_bg)
            type_lbl.config(fg=row_fg)
            text_lbl.config(fg=row_fg)
            pin_lbl.config(fg="#FFFFFF" if selected else PIN)
            if tag_lbl:
                tag_lbl.config(bg=row_bg,
                               fg="#FFFFFF" if selected else get_tag_color(clip.get("tag")))
            hover_bg = "#2F2F4A"
            widgets = (row, pin_lbl, type_lbl, text_lbl)
            if selected:
                for w in widgets:
                    w.unbind("<Enter>")
                    w.unbind("<Leave>")
            else:
                for w in widgets:
                    w.bind("<Enter>", lambda e, wl=widgets:
                           [x.config(bg=hover_bg) for x in wl])
                    w.bind("<Leave>", lambda e, wl=widgets, bg=row_bg:
                           [x.config(bg=bg) for x in wl])

    def _make_row(self, idx: int, clip: dict):
        selected = idx == self._selected
        row_bg   = ACCENT    if selected else (PINNED_ROW if clip.get("pinned") else WHITE)
        row_fg   = "#FFFFFF" if selected else TEXT_DARK

        row = tk.Frame(self._list_frame, bg=row_bg, cursor="hand2")
        row.place(x=2, y=idx * self.ROW_H + 1, relwidth=1, width=-4, height=self.ROW_H - 2)

        pin_lbl = tk.Label(row, text="📌" if clip.get("pinned") else "   ",
                           bg=row_bg, fg=PIN if not selected else "#FFFFFF",
                           font=("Segoe UI", 9), padx=6, pady=6)
        pin_lbl.pack(side="left")

        is_image = clip.get("type") == "image"
        type_lbl = tk.Label(row, text="🖼" if is_image else "◆",
                            bg=row_bg, fg=row_fg,
                            font=("Segoe UI", 9), padx=4)
        type_lbl.pack(side="left")

        if is_image:
            _d = clip.get("date", "")
            preview = f"📸 Screenshot  ·  {_d.replace(', ', '  ·  ')}" if _d else "📸 Screenshot"
        else:
            raw     = clip["text"].replace("\r", "").replace("\n", " ").replace("\t", " ")
            preview = raw[:58] + "…" if len(raw) > 58 else raw

        text_lbl = tk.Label(row, text=preview,
                            bg=row_bg, fg=row_fg,
                            font=("Segoe UI", 10), anchor="w", padx=4,
                            height=1)
        text_lbl.pack(side="left", fill="x", expand=True)

        tag = clip.get("tag")
        if tag:
            tag_color = get_tag_color(tag) if not selected else "#FFFFFF"
            tag_lbl   = tk.Label(row, text=f" {tag} ",
                                 bg=row_bg, fg=tag_color,
                                 font=("Segoe UI", 8, "bold"), padx=6, pady=4)
            tag_lbl.pack(side="right", padx=(0, 6))

        self._row_widgets[idx] = (row, pin_lbl, type_lbl, text_lbl,
                                  tag_lbl if tag else None, clip)

        # Single click → paste plain immediately
        for widget in (row, pin_lbl, type_lbl, text_lbl):
            widget.bind("<Button-1>", lambda e, i=idx: self._click_row(i))
        if tag:
            tag_lbl.bind("<Button-1>", lambda e, i=idx: self._click_row(i))


        if not selected:
            hover_bg = "#2F2F4A"
            for widget in (row, pin_lbl, type_lbl, text_lbl):
                widget.bind("<Enter>", lambda e, wl=(row, pin_lbl, type_lbl, text_lbl):
                            [w.config(bg=hover_bg) for w in wl])
                widget.bind("<Leave>", lambda e, wl=(row, pin_lbl, type_lbl, text_lbl), bg=row_bg:
                            [w.config(bg=bg) for w in wl])

    # ── Smart paste bar ────────────────────────────────────────────────────

    def _show_smart_bar(self):
        if not self._clips or self._selected >= len(self._clips):
            return
        clip = self._clips[self._selected]
        if clip.get("type") == "image":
            self._confirm_paste_plain()
            return
        self._smart_mode    = True
        self._smart_opt_idx = _suggest_format(clip["text"])
        self._refresh_smart_bar()
        self._smart_bar.pack(fill="x", before=self._footer)
        self._footer_hint.config(text="← → navigate    Enter confirm    Esc cancel")
        # Grow window to fit the bar
        if self._win and self._win.winfo_exists():
            self._win.geometry(f"{self.WIN_W}x{self.WIN_H + 80}")

    def _hide_smart_bar(self):
        self._smart_mode = False
        self._smart_bar.pack_forget()
        self._footer_hint.config(
            text="↑↓  navigate    Enter  smart paste    click  paste plain    Esc  dismiss")
        # Shrink window back
        if self._win and self._win.winfo_exists():
            self._win.geometry(f"{self.WIN_W}x{self.WIN_H}")

    def _smart_nav(self, direction: int):
        if not self._smart_mode:
            return
        self._smart_opt_idx = (self._smart_opt_idx + direction) % len(SMART_PASTE_OPTIONS)
        self._refresh_smart_bar()

    def _smart_click(self, idx: int):
        self._smart_opt_idx = idx
        self._execute_smart_paste()

    def _execute_smart_paste(self):
        if not self._clips or self._selected >= len(self._clips):
            return
        clip = self._clips[self._selected]
        mode = SMART_PASTE_OPTIONS[self._smart_opt_idx][0]
        text = _transform(clip["text"], mode)
        self._close()
        self._root.after(80, lambda: self._do_paste_text(text))

    # ── Key handlers ──────────────────────────────────────────────────────

    def _on_escape(self):
        if self._smart_mode:
            self._hide_smart_bar()
        else:
            self._close()

    def _on_enter(self):
        if self._smart_mode:
            self._execute_smart_paste()
        else:
            self._show_smart_bar()

    def _on_up(self):
        if self._smart_mode:
            return
        self._nav_throttled(-1)

    def _on_down(self):
        if self._smart_mode:
            return
        self._nav_throttled(1)

    def _nav_throttled(self, direction: int):
        import time
        now = time.time()
        if now - self._last_nav_time < 0.08:
            return
        self._last_nav_time = now
        self._move_selection(direction)

    # ── Navigation & selection ─────────────────────────────────────────────

    def _move_selection(self, direction: int):
        if not self._clips:
            return
        old = self._selected
        self._selected = (self._selected + direction) % len(self._clips)
        self._update_highlight(old, self._selected)
        self._scroll_to_selected()

    def _scroll_to_selected(self):
        try:
            if not self._clips:
                return
            total_h  = len(self._clips) * self.ROW_H
            canvas_h = self._canvas.winfo_height()
            if canvas_h <= 0 or total_h <= canvas_h:
                return
            row_y    = self._selected * self.ROW_H
            top_frac = row_y / total_h
            bot_frac = (row_y + self.ROW_H) / total_h
            cur_top, cur_bot = self._canvas.yview()
            if top_frac < cur_top:
                self._canvas.yview_moveto(top_frac)
            elif bot_frac > cur_bot:
                self._canvas.yview_moveto(bot_frac - canvas_h / total_h)
            self._update_virtual_rows()
        except Exception:
            pass

    def _click_row(self, idx: int):
        self._selected = idx
        self._confirm_paste_plain()

    # ── Paste logic ───────────────────────────────────────────────────────

    def _confirm_paste_plain(self):
        if not self._clips or self._selected >= len(self._clips):
            return
        clip = self._clips[self._selected]
        self._close()
        self._root.after(80, lambda: self._do_paste(clip))

    def _do_paste(self, clip: dict):
        if clip.get("type") == "image":
            if self._suppress_fn:
                self._suppress_fn()
            clipboard.set_clipboard_image(clip["text"].strip())
        else:
            clipboard.set_clipboard(clip["text"].strip())
        if self._prev_hwnd:
            try:
                import win32gui
                win32gui.SetForegroundWindow(self._prev_hwnd)
            except Exception:
                pass
        self._root.after(80, self._simulate_paste)

    def _do_paste_text(self, text: str):
        if self._suppress_fn:
            self._suppress_fn()
        clipboard.set_clipboard(text)
        if self._prev_hwnd:
            try:
                import win32gui
                win32gui.SetForegroundWindow(self._prev_hwnd)
            except Exception:
                pass
        self._root.after(80, self._simulate_paste)

    def _simulate_paste(self):
        try:
            from pynput.keyboard import Controller, Key
            kb = Controller()
            kb.press(Key.ctrl); kb.press('v')
            kb.release('v');    kb.release(Key.ctrl)
        except Exception:
            pass

    # ── Window lifecycle ──────────────────────────────────────────────────

    def _schedule_help(self, btn):
        self._cancel_help()
        self._help_after = self._win.after(150, lambda: self._show_help(btn))

    def _cancel_help(self):
        if self._help_after:
            self._win.after_cancel(self._help_after)
            self._help_after = None
        if self._help_card and self._help_card.winfo_exists():
            self._help_card.destroy()
            self._help_card = None

    def _show_help(self, btn):
        if self._help_card and self._help_card.winfo_exists():
            return
        card = tk.Toplevel(self._win)
        card.overrideredirect(True)
        card.attributes("-topmost", True)
        card.configure(bg=ACCENT)
        self._help_card = card

        outer = tk.Frame(card, bg=ACCENT, padx=1, pady=1)
        outer.pack(fill="both", expand=True)
        inner = tk.Frame(outer, bg=HEADER_BG, padx=14, pady=10)
        inner.pack(fill="both", expand=True)

        tk.Label(inner, text="Launcher Shortcuts",
                 font=("Segoe UI", 9, "bold"),
                 bg=HEADER_BG, fg=ACCENT).pack(anchor="w", pady=(0, 6))
        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=(0, 8))

        sections = [
            ("Navigation", [
                ("↑ ↓",          "Navigate clips"),
                ("← →",          "Navigate smart paste options"),
                ("Click",        "Paste plain instantly"),
            ]),
            ("Paste", [
                ("Enter",        "Open Smart Paste bar"),
                ("Enter (bar)",  "Paste with selected format"),
                ("Esc (bar)",    "Close Smart Paste bar"),
                ("Esc",          "Dismiss launcher"),
            ]),
            ("Smart Paste Formats", [
                ("Plain",        "Paste as copied"),
                ("Clean",        "Fix quotes, dashes & spaces"),
                ("No Breaks",    "Remove all line breaks"),
                ("Bullets",      "Convert lines to bullet list"),
                ("UPPER",        "UPPERCASE"),
                ("lower",        "lowercase"),
            ]),
            ("Search", [
                ("#tag",         "Filter clips by tag"),
            ]),
        ]

        for section, rows in sections:
            tk.Label(inner, text=section.upper(),
                     font=("Segoe UI", 7, "bold"),
                     bg=HEADER_BG, fg=TEXT_GRAY).pack(anchor="w", pady=(6, 2))
            for key, desc in rows:
                row = tk.Frame(inner, bg=HEADER_BG)
                row.pack(fill="x", pady=1)
                tk.Label(row, text=key, font=("Segoe UI", 9, "bold"),
                         bg=HEADER_BG, fg=TEXT_DARK,
                         width=16, anchor="w").pack(side="left")
                tk.Label(row, text=desc, font=("Segoe UI", 9),
                         bg=HEADER_BG, fg=TEXT_GRAY,
                         anchor="w").pack(side="left")

        card.update_idletasks()
        cw = card.winfo_reqwidth()
        ch = card.winfo_reqheight()
        x  = btn.winfo_rootx() + btn.winfo_width() - cw
        y  = btn.winfo_rooty() - ch - 6
        card.geometry(f"+{x}+{y}")
        card.bind("<Leave>", lambda _e: self._cancel_help())

    def _close(self):
        self._smart_mode = False
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
