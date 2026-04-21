# ui.py
import re
import tkinter as tk
from tkinter import messagebox
import clipboard
import storage
import shortcut
import tray
import tags

from theme import *

def _get_active_window():
    try:
        import win32gui
        hwnd = win32gui.GetForegroundWindow()
        return win32gui.GetWindowText(hwnd).lower()
    except Exception:
        return ""


def _is_excluded_app():
    title = _get_active_window()
    excluded = storage.load_settings().get("excluded_apps", [])
    return any(app.strip() in title for app in excluded if len(app.strip()) >= 5)


def _looks_like_sensitive(text):
    """Returns True if text looks like a password, credit card, or SSN."""
    import re
    t = text.strip()
    if re.fullmatch(r'\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}', t):  # credit card
        return True
    if re.fullmatch(r'\d{3}-\d{2}-\d{4}', t):                   # SSN
        return True
    if re.fullmatch(r'\S{8,}', t):                               # single token 8+ chars, no spaces
        # Let through obvious non-passwords
        if re.search(r'https?://|www\.', t, re.I):               # URL
            return False
        if re.search(r'[/\\]', t):                               # file path
            return False
        if re.match(r'^[a-zA-ZæøåÆØÅ]+-[a-zA-ZæøåÆØÅ-]+$', t): # hyphenated word
            return False
        if re.fullmatch(r'[\w\-.]+\.[a-zA-Z]{2,5}', t):         # filename like README.md
            return False
        if re.fullmatch(r'[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}', t): # email address
            return False
        has_upper   = bool(re.search(r'[A-Z]', t))
        has_digit   = bool(re.search(r'\d', t))
        has_special = bool(re.search(r'[^a-zA-Z0-9]', t))
        if sum([has_upper, has_digit, has_special]) >= 2:
            return True
    return False


def _looks_like_code(text):
    """Returns True if text looks like code and should preserve formatting."""
    code_hints = [
        "def ",
        "class ",
        "import ",
        "function ",
        "const ",
        "return ",
        "if (",
        "for (",
        "=>",
        "{}",
        "();",
        "#include",
    ]
    matches = sum(1 for hint in code_hints if hint in text)
    return matches >= 2

def _detect_delimiter(text):
    """Return the first delimiter found in text (comma, semicolon, pipe), or None."""
    for delim in (",", ";", "|"):
        if delim in text:
            return delim
    return None

def _looks_like_splittable(text):
    """Return True if text looks like a delimited list suitable for splitting."""
    delim = _detect_delimiter(text)
    if delim is None:
        return False
    pieces = [p.strip() for p in text.split(delim)]
    return len(pieces) >= 3 and all(len(p) <= 30 for p in pieces if p)

def _hover(btn, normal_bg, hover_bg, normal_fg=TEXT_DARK, hover_fg=TEXT_DARK):
    btn.bind("<Enter>", lambda _e: btn.config(bg=hover_bg, fg=hover_fg))
    btn.bind("<Leave>", lambda _e: btn.config(bg=normal_bg, fg=normal_fg))


def _image_label(clip):
    """Return a human-readable label for an image clip using its date field."""
    try:
        from datetime import datetime
        raw = clip.get("date", "")
        dt  = datetime.strptime(raw, "%d %b %Y, %H:%M")
        return f"🖼  Screenshot – {dt.day} {dt.strftime('%b, %H:%M')}"
    except Exception:
        return "🖼  Image"


# ── Tooltip ────────────────────────────────────────────────────────────────
class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text   = text
        self.tip    = None
        self._id    = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self.hide)

    def _schedule(self, e=None):
        self._id = self.widget.after(400, self.show)

    def show(self, e=None):
        if self.tip:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() - 34
        self.tip = tk.Toplevel(self.widget)
        self.tip.overrideredirect(True)
        self.tip.geometry(f"+{x}+{y}")
        outer = tk.Frame(self.tip, bg=ACCENT, padx=1, pady=1)
        outer.pack()
        tk.Label(outer, text=self.text, bg=HEADER_BG, fg=TEXT_DARK,
                 font=("Segoe UI", 9), padx=10, pady=5).pack()

    def hide(self, e=None):
        if self._id:
            self.widget.after_cancel(self._id)
            self._id = None
        if self.tip:
            self.tip.destroy()
            self.tip = None


# ── Shortcuts card (hover on ? button) ────────────────────────────────────
class ShortcutsCard:
    _SHORTCUTS = [
        ("Clipboard",  [
            ("Ctrl+C",           "Capture to clipboard"),
            ("Ctrl+Alt+C",       "Capture & pin"),
            ("Ctrl+Shift+V",     "Open quick-paste launcher"),
            ("Ctrl+Shift+E",     "Toggle capture on / off"),
            ("Ctrl+Shift+X",     "Toggle private mode"),
            ("Double Ctrl",      "Open Smart Clipboard"),
            ("Ctrl+Shift+1–9",   "Paste hotkey clip instantly"),
            ("Ctrl+Shift hold",    "Peek at latest clip  (click to lock)"),
        ]),
        ("List",  [
            ("C",  "Copy selected"),
            ("P",  "Pin / unpin"),
            ("T",  "Tag selected"),
            ("M",  "Mark / unmark template"),
            ("F",  "Merge selected clips"),
            ("X",  "Split clip into parts"),
            ("H",  "Assign hotkey slot  (Ctrl+Shift+1–9)"),
            ("S",  "Focus search bar"),
            ("E",  "Edit selected"),
            ("B",  "Open Settings"),
            ("Del","Delete selected"),
            ("↑ ↓","Navigate"),
            ("↵",  "Copy & close"),
        ]),
    ]

    def __init__(self, widget):
        self.widget = widget
        self.card   = None
        self._id    = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self.hide)

    def _schedule(self, e=None):
        self._id = self.widget.after(150, self.show)

    def show(self, e=None):
        if self.card:
            return
        self.card = tk.Toplevel(self.widget)
        self.card.overrideredirect(True)
        self.card.attributes("-topmost", True)

        outer = tk.Frame(self.card, bg=ACCENT, padx=1, pady=1)
        outer.pack(fill="both", expand=True)
        inner = tk.Frame(outer, bg=HEADER_BG, padx=14, pady=10)
        inner.pack(fill="both", expand=True)

        tk.Label(inner, text="Keyboard Shortcuts",
                 font=("Segoe UI", 9, "bold"), bg=HEADER_BG, fg=ACCENT).pack(anchor="w", pady=(0, 8))
        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=(0, 8))

        for section, rows in self._SHORTCUTS:
            tk.Label(inner, text=section.upper(),
                     font=("Segoe UI", 7, "bold"), bg=HEADER_BG, fg=TEXT_GRAY).pack(anchor="w", pady=(4, 2))
            for key, desc in rows:
                row = tk.Frame(inner, bg=HEADER_BG)
                row.pack(fill="x", pady=1)
                tk.Label(row, text=key, font=("Segoe UI", 9, "bold"),
                         bg=HEADER_BG, fg=TEXT_DARK, width=14, anchor="w").pack(side="left")
                tk.Label(row, text=desc, font=("Segoe UI", 9),
                         bg=HEADER_BG, fg=TEXT_GRAY, anchor="w").pack(side="left")

        self.card.update_idletasks()
        cw = self.card.winfo_reqwidth()
        ch = self.card.winfo_reqheight()
        x  = self.widget.winfo_rootx() + self.widget.winfo_width() - cw
        y  = self.widget.winfo_rooty() - ch - 6
        self.card.geometry(f"+{x}+{y}")

    def hide(self, e=None):
        if self._id:
            self.widget.after_cancel(self._id)
            self._id = None
        if self.card:
            self.card.destroy()
            self.card = None


# ── App ────────────────────────────────────────────────────────────────────
class App:
    def __init__(self, startup=False):
        self.root = tk.Tk()

        # Apply icon before anything renders so the tkinter feather never shows
        import os, sys
        _base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        ico = os.path.join(_base, "SmartClipboard_1.ico")
        if not os.path.exists(ico):
            ico = "SmartClipboard_1.ico"
        try:
            self.root.iconbitmap(default=ico)
            self.root.iconbitmap(ico)
        except Exception:
            pass

        if startup:
            self.root.withdraw()
        self.root.title("Smart Clipboard ")
        self.root.resizable(False, False)
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x  = (sw - 820) // 2 - 80
        y  = (sh - 520) // 2 - 60
        self.root.geometry(f"820x520+{x}+{y}")
        self.root.configure(bg=BG)

        self._incognito           = False
        self._incognito_clips     = []
        self._pending_split_text  = None
        self._suppress_next_capture = False
        self._peek_window      = None
        self._peek_locked      = False
        self._peek_last_x      = None
        self._peek_last_y      = None
        self._peek_last_w      = None
        self._peek_last_h      = None
        self._peek_clips       = []
        self._peek_idx         = 0
        self._peek_counter_lbl = None
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._hide_window)
        self.tray_icon = tray.start_tray(
            show_callback=self._show_window,
            quit_callback=self.root.quit
        )
        tray.set_tray_title(self.tray_icon, self._active)
        from launcher import QuickPasteLauncher
        self._launcher = QuickPasteLauncher(self.root, suppress_fn=lambda: setattr(self, '_suppress_next_capture', True))
        def _sc(*keys):
            """Return True when global shortcuts AND all listed individual keys are enabled."""
            s = storage.load_settings()
            return s.get("global_shortcuts", True) and all(s.get(k, True) for k in keys)

        shortcut.start_listener(
            self._on_clipboard_change,
            lambda: self._on_pin_shortcut() if (self._active and _sc("shortcut_pin")) else None,
            launcher_callback=lambda hwnd: self.root.after(0, lambda: self._launcher.open(hwnd)) if (self._active and _sc("shortcut_launcher")) else None,
            toggle_callback=lambda: self.root.after(0, self._toggle_active) if _sc("shortcut_toggle") else None,
            incognito_callback=lambda: self.root.after(0, self._toggle_incognito) if (self._active and _sc("shortcut_incognito")) else None,
            show_callback=lambda: self.root.after(0, self._show_window) if (self._active and _sc("shortcut_show")) else None,
            hotkey_clip_callback=lambda slot, hwnd: self.root.after(0, lambda s=slot, h=hwnd: self._on_hotkey_clip(s, h)) if (self._active and _sc("shortcut_hotkey_clips")) else None,
            peek_show_callback=lambda: self.root.after(0, self._peek_show) if (self._active and _sc("shortcut_peek")) else None,
            peek_dismiss_callback=lambda: self.root.after(0, self._peek_dismiss),
            peek_hide_callback=lambda: self.root.after(0, self._peek_hide),
        )
        self._add_to_startup()
        if not storage.load_settings().get("onboarding_complete"):
            from onboarding import Onboarding
            Onboarding(self).start()

    def _add_to_startup(self):
        import winreg, sys
        if not getattr(sys, "frozen", False):
            return
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        enabled  = storage.load_settings().get("auto_start", True)
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            if enabled:
                winreg.SetValueEx(key, "SmartClipboard", 0, winreg.REG_SZ,
                                  f'"{sys.executable}" --startup')
            else:
                try: winreg.DeleteValue(key, "SmartClipboard")
                except FileNotFoundError: pass
            winreg.CloseKey(key)
        except:
            pass

    def _hide_window(self):
        if self._incognito and self._incognito_clips:
            import tkinter.messagebox as mb
            if mb.askyesno("Private mode",
                           f"{len(self._incognito_clips)} private clip(s) will be lost when the app closes.\nClear them now?",
                           parent=self.root):
                self._incognito_clips.clear()
                self._refresh_list()
        self.root.withdraw()

    def _show_window(self):
        state = self.root.state()
        if state == "withdrawn":
            self.root.deiconify()
        elif state == "iconic":
            self.root.deiconify()
        self.root.after(50, self._bring_to_front)

    def _bring_to_front(self):
        import ctypes
        import os, sys
        hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
        if not hwnd:
            hwnd = self.root.winfo_id()
        # Trick Windows into allowing SetForegroundWindow by attaching to the foreground thread
        fg_hwnd   = ctypes.windll.user32.GetForegroundWindow()
        cur_tid   = ctypes.windll.kernel32.GetCurrentThreadId()
        fg_tid    = ctypes.windll.user32.GetWindowThreadProcessId(fg_hwnd, None)
        if fg_tid and fg_tid != cur_tid:
            ctypes.windll.user32.AttachThreadInput(fg_tid, cur_tid, True)
        ctypes.windll.user32.ShowWindow(hwnd, 9)   # SW_RESTORE
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.BringWindowToTop(hwnd)
        if fg_tid and fg_tid != cur_tid:
            ctypes.windll.user32.AttachThreadInput(fg_tid, cur_tid, False)
        self.root.lift()
        self.root.focus_force()
        self.listbox.focus_set()
        if self._pending_split_text:
            target = self._pending_split_text
            self._pending_split_text = None
            display = getattr(self, "_display_items", self._get_current_clips())
            for i, item in enumerate(display):
                if isinstance(item, dict) and item.get("text") == target:
                    self.listbox.selection_clear(0, tk.END)
                    self.listbox.selection_set(i)
                    self.listbox.see(i)
                    self.listbox.event_generate("<<ListboxSelect>>")
                    break
        _base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        ico = os.path.join(_base, "SmartClipboard_1.ico")
        if not os.path.exists(ico):
            ico = "SmartClipboard_1.ico"
        try:
            self.root.iconbitmap(ico)
        except:
            pass

    # ── Build UI ───────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        self._sep()
        self._build_toolbar()
        self._sep()
        self._build_main()
        self._sep()
        self._build_action_bar()
        self._refresh_list()
        self.listbox.focus_set()
        # Global key bindings (fire even when listbox doesn't have focus)
        self.root.bind("<Up>",     lambda _e: self._kb_nav(-1))
        self.root.bind("<Down>",   lambda _e: self._kb_nav(+1))
        self.root.bind("<Escape>", lambda _e: self._hide_window())

    def _sep(self, color=BORDER):
        tk.Frame(self.root, bg=color, height=1).pack(fill="x")

    def _build_header(self):
        hdr = tk.Frame(self.root, bg=HEADER_BG, height=72)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        # Left accent strip
        tk.Frame(hdr, bg=ACCENT, width=4).pack(side="left", fill="y")

        left = tk.Frame(hdr, bg=HEADER_BG)
        left.pack(side="left", padx=16, pady=0)

        tk.Label(left, text="Smart Clipboard ✨",
                 font=("Segoe UI", 15, "bold"),
                 bg=HEADER_BG, fg=TEXT_DARK).pack(side="left", pady=20)

        tk.Label(left, text="  ·  Your clipboard, organized",
                 font=("Segoe UI", 9),
                 bg=HEADER_BG, fg=TEXT_GRAY).pack(side="left", pady=22)

        # Active/Inactive toggle — starts Active
        self._active = True
        self._toggle_btn = tk.Button(
            hdr, text="● Active", font=("Segoe UI", 9, "bold"),
            bg="#27AE60", fg=TEXT_DARK, relief="flat", padx=14, pady=5,
            cursor="hand2", bd=0, command=self._toggle_active
        )
        self._toggle_btn.pack(side="left", padx=(14, 0), pady=18)
        Tooltip(self._toggle_btn, "Toggle clipboard capture  (Ctrl+Shift+E)")

        self._incognito_btn = tk.Button(
            hdr, text="👁 Private", font=("Segoe UI", 9, "bold"),
            bg=WHITE, fg=TEXT_DARK, relief="flat", padx=14, pady=5,
            cursor="hand2", bd=0, command=self._toggle_incognito
        )
        self._incognito_btn.pack(side="left", padx=(8, 0), pady=18)
        Tooltip(self._incognito_btn, "Private mode — clips are never saved to disk  (Ctrl+Shift+X)")

        # Clip counter badge on the right
        badge_outer = tk.Frame(hdr, bg=BORDER)
        badge_outer.pack(side="right", padx=18, pady=22)
        self.counter_label = tk.Label(
            badge_outer, text="0 clips",
            font=("Segoe UI", 9, "bold"),
            bg=WHITE, fg=ACCENT, padx=10, pady=3
        )
        self.counter_label.pack(padx=1, pady=1)

    def _toggle_active(self):
        self._active = not self._active
        if self._active:
            self._toggle_btn.config(text="● Active", bg="#27AE60")
            self._show_toast("Clipboard capture ON ✅")
        else:
            self._toggle_btn.config(text="○ Inactive", bg=BORDER)
            self._show_toast("Clipboard capture OFF ⏸")
        tray.set_tray_title(self.tray_icon, self._active)

    def _toggle_incognito(self):
        if self._incognito:
            self._disable_incognito_popup()
        else:
            self._incognito = True
            self._incognito_btn.config(text="🔒 Private ON", bg="#6C3483")
            self.root.configure(bg="#1E1A2E")
            self._show_toast("Private mode ON — clips not saved 🔒")

    def _disable_incognito_popup(self):
        if not self._incognito_clips:
            # Nothing was copied in private mode — skip the confirmation entirely
            self._incognito = False
            self._incognito_btn.config(text="👁 Private", bg=WHITE)
            self.root.configure(bg=BG)
            self._refresh_list()
            self._show_toast("Private mode OFF")
            return
        popup = tk.Toplevel(self.root)
        popup.title("")
        popup.overrideredirect(True)
        popup.configure(bg=BG)
        popup.attributes("-topmost", True)

        pw, ph = 360, 180
        x = self.root.winfo_x() + (self.root.winfo_width()  - pw) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - ph) // 2
        popup.geometry(f"{pw}x{ph}+{x}+{y}")

        # border frame
        outer = tk.Frame(popup, bg=BORDER, padx=1, pady=1)
        outer.pack(fill="both", expand=True)
        inner = tk.Frame(outer, bg=BG, padx=20, pady=18)
        inner.pack(fill="both", expand=True)

        tk.Label(inner, text="Turn off Private Mode?", font=("Segoe UI", 11, "bold"),
                 bg=BG, fg=TEXT_DARK).pack(anchor="w")

        n = len(self._incognito_clips)
        detail = (f"You have {n} private clip{'s' if n != 1 else ''} in memory.\nThey will be cleared when you exit private mode.")  \
                 if n else "No private clips to lose."
        tk.Label(inner, text=detail, font=("Segoe UI", 9), bg=BG, fg=TEXT_GRAY,
                 justify="left", wraplength=310).pack(anchor="w", pady=(6, 18))

        btn_row = tk.Frame(inner, bg=BG)
        btn_row.pack(anchor="e")

        def _cancel():
            popup.destroy()

        def _confirm():
            self._incognito_clips.clear()
            self._incognito = False
            self._incognito_btn.config(text="👁 Private", bg=WHITE)
            self.root.configure(bg=BG)
            self._refresh_list()
            popup.destroy()
            self._show_toast("Private mode OFF")

        tk.Button(btn_row, text="Cancel", font=("Segoe UI", 9),
                  bg=WHITE, fg=TEXT_DARK, relief="flat", padx=14, pady=6,
                  cursor="hand2", bd=0, command=_cancel).pack(side="left", padx=(0, 8))
        tk.Button(btn_row, text="Turn off", font=("Segoe UI", 9, "bold"),
                  bg=DANGER, fg="white", relief="flat", padx=14, pady=6,
                  cursor="hand2", bd=0, command=_confirm).pack(side="left")

        popup.bind("<Escape>", lambda _: _cancel())
        popup.bind("<Return>", lambda _: self.root.after(1, _confirm))
        popup.grab_set()
        popup.focus_force()

    def _build_toolbar(self):
        bar = tk.Frame(self.root, bg=HEADER_BG, padx=16, pady=9)
        bar.pack(fill="x")

        # Sort
        tk.Label(bar, text="Sort", bg=HEADER_BG, fg=TEXT_GRAY,
                 font=("Segoe UI", 9)).pack(side="left", padx=(2, 4))
        self.sort_var = tk.StringVar(value="Newest")
        sort_menu = tk.OptionMenu(bar, self.sort_var, "Newest", "Oldest", "A-Z", "Z-A")
        sort_menu.config(bg=WHITE, fg=TEXT_DARK, relief="flat", font=("Segoe UI", 9),
                         activebackground=WHITE, activeforeground=TEXT_DARK,
                         bd=0, highlightthickness=0, padx=6)
        sort_menu["menu"].config(bg=WHITE, fg=TEXT_DARK, activebackground=ACCENT,
                                  activeforeground="white", font=("Segoe UI", 9), bd=0)
        sort_menu.pack(side="left", padx=(0, 18))
        self.sort_var.trace("w", lambda *_: self._refresh_list())

        # Search box with focus border
        tk.Label(bar, text="🔍", bg=HEADER_BG, fg=TEXT_GRAY,
                 font=("Segoe UI", 10)).pack(side="left", padx=(0, 4))
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *_: self._refresh_list())
        search_wrap = tk.Frame(bar, bg=WHITE, padx=8, pady=4,
                               highlightbackground=BORDER, highlightthickness=1)
        search_wrap.pack(side="left", padx=(0, 18))
        self._search_entry = tk.Entry(search_wrap, textvariable=self.search_var, width=34,
                                font=("Segoe UI", 10), relief="flat", bd=0,
                                bg=WHITE, fg=TEXT_DARK, insertbackground=TEXT_DARK)
        self._search_entry.pack()
        self._search_entry.bind("<FocusIn>",
                          lambda _: search_wrap.config(highlightbackground=ACCENT))
        self._search_entry.bind("<FocusOut>",
                          lambda _: search_wrap.config(highlightbackground=BORDER))
        self._search_entry.bind("<Escape>", lambda _: (
            self.search_var.set(""),
            self.listbox.focus_set()
        ))
        self._search_entry.bind("<Down>", lambda _: self._search_jump_to_list())

        # Tag filter
        tk.Label(bar, text="Tag", bg=HEADER_BG, fg=TEXT_GRAY,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        self.tag_filter_var = tk.StringVar(value="all")
        self.tag_filter_btn = tk.Button(
            bar, text="all ▾",
            font=("Segoe UI", 9), bg=WHITE, fg=TEXT_DARK,
            relief="flat", padx=10, pady=4, cursor="hand2", bd=0,
            highlightthickness=1, highlightbackground=BORDER,
            command=self._show_tag_filter_menu
        )
        self.tag_filter_btn.pack(side="left")

        self._tpl_btn = tk.Button(
            bar, text="⟨⟩  Template",
            font=("Segoe UI", 9), bg=WHITE, fg=TEXT_DARK,
            relief="flat", padx=10, pady=4, cursor="hand2", bd=0,
            highlightthickness=1, highlightbackground=BORDER,
            command=self._toggle_template
        )
        self._tpl_btn.pack(side="left", padx=(8, 0))
        Tooltip(self._tpl_btn, "Mark selected clip as template — {placeholders} are filled in on copy  (M)")

        self._hotkey_btn = tk.Button(
            bar, text="⚡ Hotkey",
            font=("Segoe UI", 9), bg=WHITE, fg=TEXT_DARK,
            relief="flat", padx=10, pady=4, cursor="hand2", bd=0,
            highlightthickness=1, highlightbackground=BORDER,
            command=self._assign_hotkey_slot
        )
        self._hotkey_btn.pack(side="left", padx=(4, 0))
        Tooltip(self._hotkey_btn, "Press (H) to assign a Ctrl+Shift+1–9 hotkey to this clip")

        # Settings button (right side of toolbar)
        settings_btn = tk.Button(
            bar, text="⚙",
            font=("Segoe UI", 11), bg=HEADER_BG, fg=TEXT_GRAY,
            relief="flat", padx=8, pady=2, cursor="hand2", bd=0,
            command=self._settings_popup
        )
        settings_btn.pack(side="right", padx=(0, 2))
        _hover(settings_btn, HEADER_BG, WHITE)
        Tooltip(settings_btn, "Settings — Preferences")

    def _build_main(self):
        container = tk.Frame(self.root, bg=BG)
        container.pack(fill="both", expand=True)

        # Left – clip list
        left = tk.Frame(container, bg=BG)
        left.place(relx=0, rely=0, relwidth=0.585, relheight=1.0)

        # Custom colored scrollbar
        sb_frame = tk.Frame(left, bg=BG, width=6)
        sb_frame.pack(side="right", fill="y", pady=4)
        sb_frame.pack_propagate(False)

        sb_thumb = tk.Frame(sb_frame, bg=ACCENT, cursor="hand2")

        self.listbox = tk.Listbox(
            left,
            font=("Segoe UI", 10),
            selectmode="extended",
            activestyle="none",
            bg=WHITE, fg=TEXT_DARK,
            selectbackground=ACCENT,
            selectforeground="white",
            relief="flat", bd=0,
            highlightthickness=0,
        )
        self.listbox.pack(fill="both", expand=True, padx=(6, 0), pady=4)

        def _update_thumb(first, last):
            first, last = float(first), float(last)
            h = sb_frame.winfo_height()
            sb_thumb.place(x=0, y=int(first * h),
                           width=6, height=max(20, int((last - first) * h)))
            if last - first >= 1.0:
                sb_thumb.place_forget()

        self.listbox.config(yscrollcommand=_update_thumb)
        self.listbox.bind("<MouseWheel>",
                          lambda e: self.listbox.yview_scroll(int(-1*(e.delta/120)), "units"))
        sb_thumb.bind("<B1-Motion>",
                      lambda e: self.listbox.yview_moveto(
                          (sb_thumb.winfo_y() + e.y) / sb_frame.winfo_height()))
        self.listbox.bind("<Double-Button-1>", self._double_click_copy)
        self.listbox.bind("<Control-Button-1>", self._ctrl_click)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        self.listbox.bind("<Delete>", lambda e: self._delete_selected())
        # Keyboard shortcuts active when listbox has focus
        self.listbox.bind("<Up>",           lambda _e: self._kb_nav(-1) or "break")
        self.listbox.bind("<Down>",         lambda _e: self._kb_nav(+1) or "break")
        self.listbox.bind("<Control-Up>",   lambda _e: self._kb_nav_select(-1) or "break")
        self.listbox.bind("<Control-Down>", lambda _e: self._kb_nav_select(+1) or "break")
        self.listbox.bind("<c>",      lambda _e: self._copy_selected())
        self.listbox.bind("<p>",      lambda _e: self._toggle_pin())
        self.listbox.bind("<t>",      lambda _e: self._show_tag_menu())
        self.listbox.bind("<m>",      lambda _e: self._toggle_template())
        self.listbox.bind("<e>",      lambda _e: self._edit_selected())
        self.listbox.bind("<f>",      lambda _e: self._merge_clips())
        self.listbox.bind("<x>",      lambda _e: self._split_clip())
        self.root.bind("<x>",         lambda _e: self._split_clip() if not isinstance(self.root.focus_get(), tk.Entry) else None)
        self.listbox.bind("<h>",      lambda _e: self._assign_hotkey_slot())
        self.listbox.bind("<s>",      lambda _e: self._focus_search())
        self.listbox.bind("<b>",      lambda _e: self._settings_popup())
        self.listbox.bind("<Return>", lambda _e: self._copy_and_close())
        self.root.bind("<b>", lambda _: self._settings_popup() if not isinstance(self.root.focus_get(), tk.Entry) else None)

        # Divider
        tk.Frame(container, bg=BORDER, width=1).place(
            relx=0.585, rely=0, relwidth=0.002, relheight=1.0)

        # Right – preview
        right = tk.Frame(container, bg=BG)
        right.place(relx=0.587, rely=0, relwidth=0.413, relheight=1.0)

        # Preview accent top strip + header
        tk.Frame(right, bg=ACCENT, height=2).pack(fill="x")
        prev_hdr = tk.Frame(right, bg=HEADER_BG, padx=10, pady=7)
        prev_hdr.pack(fill="x")
        tk.Label(prev_hdr, text="PREVIEW", font=("Segoe UI", 7, "bold"),
                 bg=HEADER_BG, fg=ACCENT).pack(side="left")
        self.preview_meta = tk.Label(prev_hdr, text="",
                                     font=("Segoe UI", 8),
                                     bg=HEADER_BG, fg=TEXT_GRAY)
        self.preview_meta.pack(side="left", padx=(8, 0))

        self.preview_text = tk.Text(
            right,
            font=("Segoe UI", 10),
            bg=WHITE, fg=TEXT_DARK,
            relief="flat", bd=0,
            highlightthickness=0,
            wrap="word", state="disabled",
            padx=12, pady=10,
            spacing1=2, spacing2=2,
        )
        self.preview_text.pack(fill="both", expand=True, padx=4, pady=4)
        # Syntax highlighting tags
        self.preview_text.tag_configure("syn_keyword",  foreground="#C792EA", font=("Segoe UI", 10, "bold"))
        self.preview_text.tag_configure("syn_builtin",  foreground="#82AAFF")
        self.preview_text.tag_configure("syn_string",   foreground="#C3E88D")
        self.preview_text.tag_configure("syn_comment",  foreground="#546E7A", font=("Segoe UI", 10, "italic"))
        self.preview_text.tag_configure("syn_number",   foreground="#F78C6C")
        self.preview_text.tag_configure("syn_operator", foreground="#89DDFF")

    def _build_action_bar(self):
        bar = tk.Frame(self.root, bg=HEADER_BG, padx=12, pady=10)
        bar.pack(fill="x")

        cfg = dict(font=("Segoe UI", 9, "bold"), relief="flat",
                   padx=16, pady=7, cursor="hand2", bd=0)

        copy_btn = tk.Button(bar, text="⎘  Copy",
                             bg=ACCENT, fg="white",
                             activebackground=ACCENT_HOVER, activeforeground="white",
                             command=self._copy_selected, **cfg)
        copy_btn.pack(side="left", padx=(0, 6))
        _hover(copy_btn, ACCENT, ACCENT_HOVER, "white", "white")
        Tooltip(copy_btn, "Copy selected clip  (C or double-click)")

        del_btn = tk.Button(bar, text="✕  Delete",
                            bg=WHITE, fg=TEXT_DARK,
                            activebackground=BORDER, activeforeground=TEXT_DARK,
                            command=self._delete_selected, **cfg)
        del_btn.pack(side="left", padx=(0, 6))
        _hover(del_btn, WHITE, BORDER)
        Tooltip(del_btn, "Delete selected clip  (or press Delete key)")

        edit_btn = tk.Button(bar, text="✎  Edit",
                             bg=WHITE, fg=TEXT_DARK,
                             activebackground=BORDER, activeforeground=TEXT_DARK,
                             command=self._edit_selected, **cfg)
        edit_btn.pack(side="left", padx=(0, 6))
        _hover(edit_btn, WHITE, BORDER)
        Tooltip(edit_btn, "Edit this clip's text  (E)")

        pin_btn = tk.Button(bar, text="📌  Pin",
                            bg=PIN, fg="#1A1A2E",
                            activebackground=PIN_HOVER, activeforeground="#1A1A2E",
                            command=self._toggle_pin, **cfg)
        pin_btn.pack(side="left", padx=(0, 6))
        _hover(pin_btn, PIN, PIN_HOVER, "#1A1A2E", "#1A1A2E")
        Tooltip(pin_btn, "Pin this clip to the top  (P)")

        self._tag_btn = tk.Button(bar, text="🏷  Tag",
                                  bg=WHITE, fg=TEXT_DARK,
                                  activebackground=BORDER, activeforeground=TEXT_DARK,
                                  command=self._show_tag_menu, **cfg)
        self._tag_btn.pack(side="left", padx=(0, 6))
        _hover(self._tag_btn, WHITE, BORDER)
        Tooltip(self._tag_btn, "Add or change the tag for this clip  (T)")

        merge_btn = tk.Button(bar, text="⊕  Merge",
                              bg=BORDER, fg=TEXT_DARK,
                              activebackground=WHITE, activeforeground=TEXT_DARK,
                              command=self._merge_clips, **cfg)
        merge_btn.pack(side="left", padx=(8, 0))
        _hover(merge_btn, BORDER, WHITE)
        Tooltip(merge_btn, "Merge selected clips into one  (F)")

        # Visual separator before destructive action
        tk.Frame(bar, bg=BORDER, width=1).pack(side="left", fill="y", padx=(6, 10), pady=3)

        clear_btn = tk.Button(bar, text="🗑  Clear All",
                              bg=DANGER, fg="white",
                              activebackground=DANGER_HOVER, activeforeground="white",
                              command=self._clear_all, **cfg)
        clear_btn.pack(side="left")
        _hover(clear_btn, DANGER, DANGER_HOVER, "white", "white")
        Tooltip(clear_btn, "Delete all saved clips permanently")

        help_btn = tk.Button(bar, text="?",
                             font=("Segoe UI", 10, "bold"), bg=HEADER_BG, fg=TEXT_GRAY,
                             relief="flat", padx=8, pady=2, cursor="hand2", bd=0)
        help_btn.pack(side="right", padx=(0, 4))
        _hover(help_btn, HEADER_BG, WHITE)
        ShortcutsCard(help_btn)

    # ── Clipboard callbacks ────────────────────────────────────────────────

    def _on_clipboard_change(self, content):
        self.root.after(0, lambda: self._save_content(content))

    def _save_content(self, content):
        if self._suppress_next_capture:
            self._suppress_next_capture = False
            return
        if not self._active:
            return
        from PIL import Image
        if self._incognito:
            if not isinstance(content, Image.Image):
                if len(content) >= 3:
                    text = content
                    if not any(c["text"] == text for c in self._incognito_clips):
                        self._incognito_clips.insert(0, {"text": text, "type": "text", "incognito": True})
                    self._refresh_list()
            return
        if isinstance(content, Image.Image):
            path = storage.save_image(content)
            storage.save_clip(path, clip_type="image", source="")
            self._refresh_list()
            
        else:
            if len(content) < 3:
                return
            if not storage.load_settings().get("store_sensitive", False) \
                    and _looks_like_sensitive(content):
                self._show_toast("Sensitive content skipped 🔒")
                return
            if _is_excluded_app():
                return
            # Detect code — auto-tag, otherwise save raw
            if _looks_like_code(content):
                storage.save_clip(content, clip_type="text")
                storage.set_tag(content, "code")
                self._refresh_list()
                return
            is_new = not any(c.get("text") == content for c in storage.load_clips())
            storage.save_clip(content, clip_type="text")
            self._refresh_list()
            if is_new and _looks_like_splittable(content):
                self._pending_split_text = content
                self._show_toast("Looks like a list — open Smart Clipboard and press X to split 📋", duration=2000)

    def _on_pin_shortcut(self):
        self.root.after(0, self._copy_and_pin)

    def _copy_and_pin(self):
        import pyperclip
        import time
        from PIL import ImageGrab

        time.sleep(0.1)

        # Check for image first
        try:
            img = ImageGrab.grabclipboard()
        except:
            img = None

        if img is not None:
            path = storage.save_image(img)
            clips = storage.load_clips()
            existing = next((c for c in clips if c.get("text") == path), None)
            if existing:
                if not existing.get("pinned"):
                    storage.toggle_pin(path)
                    self._show_toast("📌 Image Pinned!")
                else:
                    storage.toggle_pin(path)
                    self._show_toast("Image Unpinned!")
            else:
                storage.save_clip(path, clip_type="image", source="")
                storage.toggle_pin(path)
                self._show_toast("📌 Image Saved & Pinned!")
            self._refresh_list()
            return

        # Fall back to text
        try:
            text = pyperclip.paste()
        except:
            text = ""

        if not text or len(text) < 3:
            self._show_toast("Nothing to pin!")
            return

        if not _looks_like_code(text):
            text = " ".join(text.split())
        clips = storage.load_clips()
        existing = next((c for c in clips if c.get("text") == text), None)

        if existing:
            if not existing.get("pinned"):
                storage.toggle_pin(text)
                self._show_toast("📌 Pinned!")
            else:
                storage.toggle_pin(text)
                self._show_toast("Unpinned!")
        else:
            storage.save_clip(text, clip_type="text")
            storage.toggle_pin(text)
            self._show_toast("📌 Saved & Pinned!")

        self._refresh_list()

    # ── Toast ──────────────────────────────────────────────────────────────

    def _show_toast(self, message, duration=6500):
        was_withdrawn = self.root.state() == "withdrawn"
        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes("-alpha", 0.0)
        toast.attributes("-topmost", True)
        # Creating a Toplevel can surface the parent on Windows — keep it hidden
        if was_withdrawn:
            self.root.withdraw()

        outer = tk.Frame(toast, bg=ACCENT, padx=1, pady=1)
        outer.pack()
        tk.Label(outer, text=message, bg=HEADER_BG, fg=TEXT_DARK,
                 font=("Segoe UI", 10), padx=14, pady=8).pack()

        toast.update_idletasks()
        if self.root.state() == "withdrawn":
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            x  = sw - toast.winfo_reqwidth() - 20
            y  = sh - toast.winfo_reqheight() - 60
        else:
            x = self.root.winfo_x() + self.root.winfo_width() - 240
            y = self.root.winfo_y() + self.root.winfo_height() - 64
        toast.geometry(f"+{x}+{y}")

        def fade(a=0.0):
            a = min(a + 0.12, 0.95)
            toast.attributes("-alpha", a)
            if a < 0.95:
                toast.after(18, lambda: fade(a))

        fade()
        toast.after(duration, toast.destroy)

    # ── List actions ───────────────────────────────────────────────────────

    # ── Keyboard navigation ────────────────────────────────────────────────

    def _kb_nav(self, direction):
        """Move listbox selection by direction (+1 or -1), skip if typing in Entry."""
        if isinstance(self.root.focus_get(), tk.Entry):
            return
        n = self.listbox.size()
        if n == 0:
            return
        sel = self.listbox.curselection()
        idx = (sel[0] if sel else -1) + direction
        # Skip over session headers
        while 0 <= idx < n and self._clip_at(idx) is None:
            idx += direction
        if idx < 0 or idx >= n or self._clip_at(idx) is None:
            return
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(idx)
        self.listbox.see(idx)
        self.listbox.focus_set()
        self.listbox.event_generate("<<ListboxSelect>>")

    def _kb_nav_select(self, direction):
        """Ctrl+Down/Up — extend selection in the given direction."""
        if isinstance(self.root.focus_get(), tk.Entry):
            return
        n = self.listbox.size()
        if n == 0:
            return
        sel = self.listbox.curselection()
        if not sel:
            self.listbox.selection_set(0)
            self.listbox.see(0)
            self.listbox.focus_set()
            return
        if direction == 1:
            new_idx = sel[-1] + 1
            while new_idx < n and self._clip_at(new_idx) is None:
                new_idx += 1
            if new_idx < n:
                self.listbox.selection_set(new_idx)
                self.listbox.see(new_idx)
        else:
            new_idx = sel[0] - 1
            while new_idx >= 0 and self._clip_at(new_idx) is None:
                new_idx -= 1
            if new_idx >= 0:
                self.listbox.selection_set(new_idx)
                self.listbox.see(new_idx)
        self.listbox.focus_set()
        self.listbox.event_generate("<<ListboxSelect>>")

    def _copy_and_close(self):
        """Copy the selected clip then hide the window — keeps you in your workflow."""
        sel  = self.listbox.curselection()
        clip = self._clip_at(sel[0]) if sel else None
        is_template = (clip and clip.get("template") and clip.get("type") != "image"
                       and clip.get("text", "").count("{") > 0)
        self._copy_selected()
        if not is_template:
            self._hide_window()

    def _highlight_merged(self, merged_text):
        storage.set_tag(merged_text, "merged")
        self._refresh_list()
        display = getattr(self, "_display_items", self._get_current_clips())
        for i, c in enumerate(display):
            if isinstance(c, dict) and c.get("text") == merged_text:
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(i)
                self.listbox.see(i)
                break

    def _focus_search(self):
        self._search_entry.focus_set()
        self._search_entry.icursor(tk.END)

    def _search_jump_to_list(self):
        if self.listbox.size() == 0:
            return
        if not self.listbox.curselection():
            self.listbox.selection_set(0)
        self.listbox.see(self.listbox.curselection()[0])
        self.listbox.focus_set()

    # ── List actions ───────────────────────────────────────────────────────

    def _copy_clip(self, clip):
        """Copy a clip — shows template fill dialog if it has {placeholders}."""
        if clip.get("template") and clip.get("type") != "image":
            import re as _re
            placeholders = list(dict.fromkeys(_re.findall(r'\{(\w+)\}', clip["text"])))
            if placeholders:
                self._fill_template_popup(clip, placeholders)
                return
            else:
                self._show_toast("Add {placeholders} to this clip to use as a template")
                return
        if clip.get("type") == "image":
            self._suppress_next_capture = True
            clipboard.set_clipboard_image(clip["text"].strip())
            self._show_toast("Image copied 🖼")
        else:
            self._suppress_next_capture = True
            clipboard.set_clipboard(clip["text"].strip())
            self._show_toast("Copied ✅")

    def _copy_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        clip = self._clip_at(sel[0])
        if clip is None:
            return
        self._copy_clip(clip)

    def _double_click_copy(self, _event):
        sel = self.listbox.curselection()
        if not sel:
            return
        clip = self._clip_at(sel[0])
        if clip is None:
            return
        self._copy_clip(clip)

    def _ctrl_click(self, event):
        idx = self.listbox.nearest(event.y)
        if idx < 0 or self._clip_at(idx) is None:
            return "break"
        if idx in self.listbox.curselection():
            self.listbox.selection_clear(idx)
        else:
            self.listbox.selection_set(idx)
        return "break"

    def _on_select(self, event):
        sel = self.listbox.curselection()
        if not sel:
            return
        clip = self._clip_at(sel[0])
        if clip is None:
            return

        date      = clip.get("date", "Unknown") if isinstance(clip, dict) else "Unknown"
        text      = clip.get("text", "")        if isinstance(clip, dict) else clip
        tag       = clip.get("tag")
        clip_type = clip.get("type", "text")

        # Update preview meta strip
        parts = []
        if clip_type == "image":
            parts.append("📸 Screenshot")
        else:
            source = clip.get("source") if isinstance(clip, dict) else None
            if source:
                parts.append(source)
        parts.append(date.replace(", ", "  ·  "))
        if tag and tag != "merged":
            parts.append(f"🏷 {tag}")
        hk_slot = clip.get("hotkey_slot")
        if hk_slot:
            parts.append(f"⚡ Ctrl+Shift+{hk_slot}")
        self.preview_meta.config(text="  ·  ".join(parts))

        self.preview_text.config(state="normal")
        self.preview_text.delete("1.0", tk.END)

        if clip_type == "image":
            try:
                from PIL import Image, ImageTk
                img = Image.open(text)
                img.thumbnail((300, 200))
                photo = ImageTk.PhotoImage(img)
                self.preview_text.image_create(tk.END, image=photo)
                self.preview_text._photo = photo
                self.preview_text.insert(tk.END, "\n")
            except:
                self.preview_text.insert(tk.END, "🖼  [Image file not found]")
        else:
            self.preview_text.insert(tk.END, text)
            if _looks_like_code(text):
                self._highlight_code(text)

        self.preview_text.config(state="disabled")

    def _highlight_code(self, text):
        """Apply syntax highlighting tags to the preview Text widget using re patterns."""
        # Rules applied in priority order — earlier rules block later ones from painting
        # the same character range (comment > string > keyword > builtin > number > operator)
        rules = [
            ("syn_comment",  r"#[^\n]*"),
            ("syn_string",   r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\''),
            ("syn_keyword",  r'\b(?:False|None|True|and|as|assert|async|await|break|class'
                             r'|continue|def|del|elif|else|except|finally|for|from|global'
                             r'|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return'
                             r'|try|while|with|yield|const|let|var|function|export|default'
                             r'|extends|interface|type|instanceof|new|typeof|void)\b'),
            ("syn_builtin",  r'\b(?:print|len|range|int|str|float|list|dict|set|tuple|bool'
                             r'|type|isinstance|hasattr|getattr|setattr|open|super|self|cls'
                             r'|map|filter|zip|enumerate|sorted|reversed|any|all|max|min|sum|abs)\b'),
            ("syn_number",   r'\b\d+\.?\d*(?:[eE][+-]?\d+)?\b'),
            ("syn_operator", r'[=+\-*/<>!&|^~%]+|->|=>'),
        ]

        w = self.preview_text
        # Track painted char offsets so higher-priority rules block lower ones
        painted = []  # list of (start, end) char offsets

        def overlaps(s, e):
            return any(s < pe and e > ps for ps, pe in painted)

        for tag, pattern in rules:
            for m in re.finditer(pattern, text, re.MULTILINE):
                s, e = m.start(), m.end()
                if overlaps(s, e):
                    continue
                painted.append((s, e))
                w.tag_add(tag, f"1.0+{s}c", f"1.0+{e}c")

    def _delete_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        for i in reversed(sel):
            clip = self._clip_at(i)
            if clip is not None:
                storage.delete_clip(clip["text"])
        self._refresh_list()

    def _edit_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            self._show_toast("Select a clip first!")
            return
        clip = self._clip_at(sel[0])
        if clip is None:
            return
        if clip.get("type") == "image":
            self._show_toast("Can't edit image clips")
            return
        self._edit_clip_popup(clip)

    def _edit_clip_popup(self, clip):
        popup = tk.Toplevel(self.root)
        popup.title("Edit Clip")
        popup.resizable(False, False)
        popup.configure(bg=BG)
        popup.grab_set()

        hdr = tk.Frame(popup, bg=HEADER_BG, padx=16, pady=10)
        hdr.pack(fill="x")
        tk.Frame(hdr, bg=ACCENT, height=2).pack(fill="x", side="bottom")
        tk.Label(hdr, text="✎  Edit Clip", font=("Segoe UI", 11, "bold"),
                 bg=HEADER_BG, fg=TEXT_DARK).pack(anchor="w")

        form = tk.Frame(popup, bg=BG, padx=16, pady=12)
        form.pack(fill="both", expand=True)
        wrap = tk.Frame(form, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        wrap.pack(fill="both", expand=True)
        text_widget = tk.Text(wrap, font=("Segoe UI", 10), bg=WHITE, fg=TEXT_DARK,
                              relief="flat", bd=0, insertbackground=ACCENT,
                              padx=8, pady=6, width=50, height=10, wrap="word")
        text_widget.pack(fill="both", expand=True)
        text_widget.insert("1.0", clip["text"])
        text_widget.focus_set()
        text_widget.bind("<FocusIn>",  lambda _e: wrap.config(highlightbackground=ACCENT))
        text_widget.bind("<FocusOut>", lambda _e: wrap.config(highlightbackground=BORDER))

        tk.Frame(popup, bg=BORDER, height=1).pack(fill="x", padx=16)

        def save():
            new_text = text_widget.get("1.0", "end-1c").strip()
            if not new_text:
                self._show_toast("Clip can't be empty!")
                return
            if new_text != clip["text"]:
                storage.update_clip_text(clip["text"], new_text)
                self._refresh_list()
                self._show_toast("Clip updated ✅")
            popup.destroy()

        btn_row = tk.Frame(popup, bg=BG, padx=16, pady=12)
        btn_row.pack(fill="x")
        tk.Label(btn_row, text="Ctrl+S to save", font=("Segoe UI", 8),
                 bg=BG, fg=TEXT_GRAY).pack(side="left")
        tk.Button(btn_row, text="Save", bg=ACCENT, fg="white",
                  font=("Segoe UI", 10, "bold"), relief="flat", padx=18, pady=7,
                  cursor="hand2", bd=0, command=save).pack(side="right")
        tk.Button(btn_row, text="Cancel", bg=WHITE, fg=TEXT_DARK,
                  font=("Segoe UI", 10), relief="flat", padx=14, pady=7,
                  cursor="hand2", bd=0, command=popup.destroy).pack(side="right", padx=(0, 8))

        popup.bind("<Escape>", lambda _e: popup.destroy())
        text_widget.bind("<Control-s>", lambda _e: save() or "break")

        popup.update_idletasks()
        pw, ph = 460, 320
        x = self.root.winfo_x() + (self.root.winfo_width()  - pw) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - ph) // 2
        popup.geometry(f"{pw}x{ph}+{x}+{y}")

    def _merge_clips(self):
        selected = self.listbox.curselection()
        if len(selected) < 2:
            self._show_toast("Select 2 or more clips to merge")
            return

        texts = []
        for i in selected:
            c = self._clip_at(i)
            if c is not None and c.get("type") != "image":
                texts.append(c["text"])

        if len(texts) < 2:
            self._show_toast("Select 2 or more text clips to merge")
            return

        popup = tk.Toplevel(self.root)
        popup.title("Merge Clips")
        popup.resizable(False, False)
        popup.configure(bg=HEADER_BG)
        popup.grab_set()
        w, h = 340, 230
        px = self.root.winfo_rootx() + (self.root.winfo_width() - w) // 2
        py = self.root.winfo_rooty() + (self.root.winfo_height() - h) // 2
        popup.geometry(f"{w}x{h}+{px}+{py}")
        popup.focus_force()

        tk.Label(popup, text=f"Merge {len(texts)} clips",
                 font=("Segoe UI", 11, "bold"),
                 bg=HEADER_BG, fg=TEXT_DARK).pack(pady=(18, 4))
        tk.Label(popup, text="Choose a separator:",
                 font=("Segoe UI", 9), bg=HEADER_BG, fg=TEXT_GRAY).pack()

        options     = ["Newline", "Comma", "Space", "Custom"]
        sep_var     = tk.StringVar(value="Newline")
        custom_var  = tk.StringVar()
        _option_idx = [0]  # mutable for closure

        options_frame = tk.Frame(popup, bg=HEADER_BG)
        options_frame.pack(pady=10)

        custom_entry = tk.Entry(options_frame, textvariable=custom_var,
                                font=("Segoe UI", 9), bg=WHITE, fg=TEXT_DARK,
                                insertbackground=TEXT_DARK, relief="flat",
                                highlightbackground=BORDER, highlightthickness=1,
                                width=14)

        def on_option_change(*_):
            if sep_var.get() == "Custom":
                custom_entry.grid(row=1, column=0, columnspan=4, pady=(6, 0))
                custom_entry.focus_set()
            else:
                custom_entry.grid_remove()

        for col, label in enumerate(options):
            rb = tk.Radiobutton(options_frame, text=label, variable=sep_var, value=label,
                                font=("Segoe UI", 9), bg=HEADER_BG, fg=TEXT_DARK,
                                selectcolor=HEADER_BG, activebackground=HEADER_BG,
                                command=on_option_change)
            rb.grid(row=0, column=col, padx=6)

        def _arrow_nav(direction):
            _option_idx[0] = (_option_idx[0] + direction) % len(options)
            sep_var.set(options[_option_idx[0]])
            on_option_change()
            if sep_var.get() != "Custom":
                popup.focus_set()

        def confirm():
            import pyperclip
            choice = sep_var.get()
            if choice == "Newline":   sep = "\n"
            elif choice == "Comma":   sep = ", "
            elif choice == "Space":   sep = " "
            else:                     sep = custom_var.get()
            merged = sep.join(texts)
            self._suppress_next_capture = True
            pyperclip.copy(merged)
            storage.save_clip(merged, clip_type="text", source="Smart Clipboard")
            popup.destroy()
            self._refresh_list()
            self._highlight_merged(merged)
            self._show_toast(f"Merged {len(texts)} clips ✅")

        tk.Button(popup, text="Merge & Copy",
                  font=("Segoe UI", 9, "bold"),
                  bg=ACCENT, fg="white", relief="flat",
                  padx=20, pady=7, cursor="hand2", bd=0,
                  command=confirm).pack(pady=(6, 0))
        popup.bind("<Return>",  lambda _: confirm())
        popup.bind("<Escape>",  lambda _: popup.destroy())
        popup.bind("<Left>",    lambda _: _arrow_nav(-1))
        popup.bind("<Right>",   lambda _: _arrow_nav(+1))

    def _split_clip(self):
        if getattr(self, '_split_window', None) and self._split_window.winfo_exists():
            self._split_window.lift()
            self._split_window.focus_force()
            return
        self._pending_split_text = None  # consumed — clear regardless of path
        sel = self.listbox.curselection()
        if not sel:
            self._show_toast("Select a clip first!")
            return
        clip = self._clip_at(sel[0])
        if clip is None:
            return
        if clip.get("type") == "image":
            self._show_toast("Can't split image clips")
            return

        text  = clip["text"]
        delim = _detect_delimiter(text)
        if delim is None:
            self._show_toast("No delimiter found (comma, semicolon or pipe)")
            return
        pieces = [p.strip() for p in text.split(delim) if p.strip()]
        if len(pieces) < 2:
            self._show_toast("Not enough pieces to split")
            return

        DELIM_NAMES = {",": "comma", ";": "semicolon", "|": "pipe"}
        delim_name  = DELIM_NAMES.get(delim, delim)

        OPTIONS = ["Separate clips", "Bullet list", "Numbered list", "One line"]
        _idx    = [0]

        def _build_preview(option):
            if option == "Separate clips":
                return "\n".join(f"  {p}" for p in pieces)
            elif option == "Bullet list":
                return "\n".join(f"• {p}" for p in pieces)
            elif option == "Numbered list":
                return "\n".join(f"{i+1}. {p}" for i, p in enumerate(pieces))
            else:  # One line
                return "  " + "  ".join(pieces)

        popup = tk.Toplevel(self.root)
        self._split_window = popup
        popup.title("Split Clip")
        popup.resizable(False, False)
        popup.configure(bg=HEADER_BG)
        popup.grab_set()
        w, h = 380, 300
        px = self.root.winfo_rootx() + (self.root.winfo_width()  - w) // 2
        py = self.root.winfo_rooty() + (self.root.winfo_height() - h) // 2
        popup.geometry(f"{w}x{h}+{px}+{py}")
        popup.focus_force()

        # Header
        tk.Label(popup, text=f"Split into {len(pieces)} parts",
                 font=("Segoe UI", 11, "bold"),
                 bg=HEADER_BG, fg=TEXT_DARK).pack(pady=(16, 2))
        tk.Label(popup, text=f"Detected delimiter: {delim_name}   •   {len(pieces)} pieces",
                 font=("Segoe UI", 8), bg=HEADER_BG, fg=TEXT_GRAY).pack()

        # Format selector
        fmt_frame = tk.Frame(popup, bg=HEADER_BG)
        fmt_frame.pack(pady=(10, 0))
        fmt_buttons = []
        for opt in OPTIONS:
            b = tk.Button(fmt_frame, text=opt,
                          font=("Segoe UI", 8, "bold"), relief="flat",
                          padx=9, pady=5, cursor="hand2", bd=0)
            b.pack(side="left", padx=3)
            fmt_buttons.append(b)

        def _repaint_btns():
            for i, b in enumerate(fmt_buttons):
                if i == _idx[0]:
                    b.config(bg=ACCENT, fg="white")
                else:
                    b.config(bg=WHITE, fg=TEXT_DARK)

        # Preview box
        preview_outer = tk.Frame(popup, bg=BORDER, padx=1, pady=1)
        preview_outer.pack(fill="both", expand=True, padx=16, pady=(8, 0))
        preview_text = tk.Text(preview_outer, font=("Segoe UI", 9),
                               bg=WHITE, fg=TEXT_DARK, relief="flat", bd=0,
                               padx=10, pady=8, state="disabled",
                               wrap="word", height=6)
        preview_text.pack(fill="both", expand=True)

        def _update_preview():
            preview_text.config(state="normal")
            preview_text.delete("1.0", tk.END)
            preview_text.insert(tk.END, _build_preview(OPTIONS[_idx[0]]))
            preview_text.config(state="disabled")
            _repaint_btns()

        def _arrow_nav(direction):
            _idx[0] = (_idx[0] + direction) % len(OPTIONS)
            _update_preview()

        for i, b in enumerate(fmt_buttons):
            b.config(command=lambda i=i: (_idx.__setitem__(0, i), _update_preview()))

        _update_preview()

        def confirm():
            option = OPTIONS[_idx[0]]
            self._split_window = None
            popup.destroy()
            if option == "Separate clips":
                for p in reversed(pieces):
                    storage.save_clip(p, clip_type="text", source="Smart Clipboard")
                self._refresh_list()
                self._show_toast(f"Split into {len(pieces)} clips ✅")
            elif option == "Bullet list":
                result = "\n".join(f"• {p}" for p in pieces)
                storage.save_clip(result, clip_type="text", source="Smart Clipboard")
                self._refresh_list()
                self._show_toast("Converted to bullet list ✅")
            elif option == "Numbered list":
                result = "\n".join(f"{i+1}. {p}" for i, p in enumerate(pieces))
                storage.save_clip(result, clip_type="text", source="Smart Clipboard")
                self._refresh_list()
                self._show_toast("Converted to numbered list ✅")
            else:
                result = " ".join(pieces)
                storage.save_clip(result, clip_type="text", source="Smart Clipboard")
                self._refresh_list()
                self._show_toast("Joined into one line ✅")

        btn_row = tk.Frame(popup, bg=HEADER_BG)
        btn_row.pack(pady=(10, 14))
        tk.Button(btn_row, text="Split",
                  font=("Segoe UI", 9, "bold"),
                  bg=ACCENT, fg="white", relief="flat",
                  padx=20, pady=7, cursor="hand2", bd=0,
                  command=confirm).pack(side="left", padx=(0, 8))
        def _close():
            self._split_window = None
            popup.destroy()

        tk.Button(btn_row, text="Cancel",
                  font=("Segoe UI", 9),
                  bg=WHITE, fg=TEXT_DARK, relief="flat",
                  padx=14, pady=7, cursor="hand2", bd=0,
                  command=_close).pack(side="left")

        popup.bind("<Return>", lambda _: confirm())
        popup.bind("<Escape>", lambda _: _close())
        popup.bind("<Left>",   lambda _: _arrow_nav(-1))
        popup.bind("<Right>",  lambda _: _arrow_nav(+1))

    def _clear_all(self):
        import tkinter.messagebox as mb, json
        if mb.askyesno("Clear All",
                       "Delete ALL saved clips?\nThis cannot be undone!"):
            with open(storage.DATA_FILE, "w") as f:
                json.dump([], f)
            self._refresh_list()
            self._show_toast("All clips cleared 🗑")

    def _toggle_pin(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        clip = self._clip_at(sel[0])
        if clip is None:
            return
        storage.toggle_pin(clip["text"])
        self._refresh_list()

    def _toggle_template(self):
        sel = self.listbox.curselection()
        if not sel:
            self._show_toast("Select a clip first!")
            return
        clip = self._clip_at(sel[0])
        if clip is None:
            return
        storage.toggle_template(clip["text"])
        is_now = not clip.get("template", False)
        self._show_toast("Marked as template ⟨⟩" if is_now else "Template removed")
        self._refresh_list()

    def _assign_hotkey_slot(self):
        sel = self.listbox.curselection()
        if not sel:
            self._show_toast("Select a clip first!")
            return
        clip = self._clip_at(sel[0])
        if clip is None:
            return

        current_slot = clip.get("hotkey_slot")

        # H on an already-assigned clip → unassign immediately, no popup
        if current_slot:
            storage.set_hotkey_slot(clip["text"], None)
            self._refresh_list()
            self._show_toast(f"Hotkey Ctrl+Shift+{current_slot} removed")
            return
        all_clips    = storage.load_clips()
        slot_map     = {c["hotkey_slot"]: c for c in all_clips if c.get("hotkey_slot")}

        popup = tk.Toplevel(self.root)
        popup.title("")
        popup.overrideredirect(True)
        popup.configure(bg=BG)
        popup.attributes("-topmost", True)

        outer = tk.Frame(popup, bg=BORDER, padx=1, pady=1)
        outer.pack(fill="both", expand=True)
        inner = tk.Frame(outer, bg=BG, padx=16, pady=14)
        inner.pack(fill="both", expand=True)

        tk.Label(inner, text="Assign Hotkey Slot",
                 font=("Segoe UI", 10, "bold"), bg=BG, fg=TEXT_DARK).pack(anchor="w")
        tk.Label(inner, text="Press Ctrl+Shift+N from anywhere to instantly paste",
                 font=("Segoe UI", 8), bg=BG, fg=TEXT_GRAY).pack(anchor="w", pady=(2, 10))

        grid     = tk.Frame(inner, bg=BG)
        grid.pack()
        buttons  = []   # tk.Button refs
        wrappers = []   # tk.Frame border rings
        cursor   = [-1] # -1 = no cursor shown yet; set on first arrow key

        def _pick(slot):
            storage.set_hotkey_slot(clip["text"], slot if slot != current_slot else None)
            self._refresh_list()
            if slot == current_slot:
                self._show_toast(f"Hotkey Ctrl+Shift+{slot} removed")
            else:
                self._show_toast(f"⚡ Ctrl+Shift+{slot} assigned!")
            popup.destroy()

        def _repaint(idx):
            if idx < 0:
                return
            slot     = idx + 1
            owner    = slot_map.get(slot)
            is_mine  = (slot == current_slot)
            is_taken = bool(owner and not is_mine)
            bg_col   = ACCENT if is_mine else (BORDER if is_taken else WHITE)
            fg_col   = "white" if is_mine else TEXT_DARK
            sub_fg   = "#CCCCFF" if is_mine else TEXT_GRAY
            cell     = buttons[idx]
            cell.config(bg=bg_col)
            for child in cell.winfo_children():
                child.config(bg=bg_col, fg=fg_col if child == cell.winfo_children()[0] else sub_fg)
            wrappers[idx].config(bg="#7B7FFF" if idx == cursor[0] else BG)

        def _move_cursor(delta):
            old = cursor[0]
            if old == -1:
                # First navigation: start at current slot or slot 1
                cursor[0] = (current_slot - 1) if current_slot else 0
            else:
                cursor[0] = (old + delta) % 9
            _repaint(old)
            _repaint(cursor[0])

        for i in range(9):
            slot     = i + 1
            r, c     = divmod(i, 3)
            owner    = slot_map.get(slot)
            is_mine  = (slot == current_slot)
            is_taken = bool(owner and not is_mine)
            bg_col   = ACCENT if is_mine else (BORDER if is_taken else WHITE)
            fg_col   = "white" if is_mine else TEXT_DARK
            sub_fg   = "#CCCCFF" if is_mine else TEXT_GRAY

            # Clip preview text for the subtitle
            sub = ""
            if is_mine:
                t = clip.get("text", "")
                sub = (t[:10] + "…") if len(t) > 10 else t
            elif is_taken:
                t = owner.get("text", "")
                sub = (t[:10] + "…") if len(t) > 10 else t

            # Cursor ring wrapper
            wrap = tk.Frame(grid, bg=BG, padx=2, pady=2)
            wrap.grid(row=r, column=c, padx=2, pady=2)

            # Cell frame holds number + subtitle
            cell = tk.Frame(wrap, bg=bg_col, cursor="hand2", width=64, height=52)
            cell.pack()
            cell.pack_propagate(False)

            tk.Label(cell, text=str(slot),
                     font=("Segoe UI", 11, "bold"),
                     bg=bg_col, fg=fg_col,
                     cursor="hand2").pack(pady=(6, 0))
            tk.Label(cell, text=sub,
                     font=("Segoe UI", 7),
                     bg=bg_col, fg=sub_fg,
                     cursor="hand2").pack()

            # Bind click on every widget in cell
            for w in (cell, *cell.winfo_children()):
                w.bind("<Button-1>", lambda _, s=slot: _pick(s))

            # Use the cell frame as the "button" for repaint
            wrappers.append(wrap)
            buttons.append(cell)

        if current_slot:
            tk.Label(inner, text=f"Currently on slot {current_slot} — click it to remove",
                     font=("Segoe UI", 8), bg=BG, fg=TEXT_GRAY).pack(pady=(8, 0))

        tk.Label(inner, text="↑ ↓ ← →  navigate    Enter  confirm    1-9  quick pick",
                 font=("Segoe UI", 7), bg=BG, fg=TEXT_GRAY).pack(pady=(6, 0))

        popup.bind("<Up>",    lambda _: _move_cursor(-3))
        popup.bind("<Down>",  lambda _: _move_cursor(+3))
        popup.bind("<Left>",  lambda _: _move_cursor(-1))
        popup.bind("<Right>", lambda _: _move_cursor(+1))
        popup.bind("<Return>", lambda _: _pick(cursor[0] + 1))
        def _on_key(e):
            if e.char in '123456789':
                _pick(int(e.char))
        popup.bind("<Key>",    _on_key)
        popup.bind("<Escape>", lambda _: popup.destroy())
        popup.update_idletasks()
        pw = popup.winfo_reqwidth()
        ph = popup.winfo_reqheight()
        x  = self.root.winfo_x() + (self.root.winfo_width()  - pw) // 2
        y  = self.root.winfo_y() + (self.root.winfo_height() - ph) // 2
        popup.geometry(f"+{x}+{y}")
        popup.grab_set()
        popup.focus_force()

    def _on_hotkey_clip(self, slot, hwnd):
        clip = storage.get_clip_by_hotkey(slot)
        if not clip:
            self._show_toast(f"No clip on slot {slot}")
            return
        self._suppress_next_capture = True
        if clip.get("type") == "image":
            clipboard.set_clipboard_image(clip["text"].strip())
        else:
            clipboard.set_clipboard(clip["text"].strip())
        try:
            import win32gui
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        self._show_toast(f"⚡ Slot {slot} pasted")
        self.root.after(80, self._simulate_paste_hotkey)

    def _simulate_paste_hotkey(self):
        try:
            from pynput.keyboard import Controller, Key
            kb = Controller()
            for mod in (Key.shift, Key.shift_l, Key.shift_r,
                        Key.ctrl,  Key.ctrl_l,  Key.ctrl_r):
                try:
                    kb.release(mod)
                except Exception:
                    pass
            # Invalidate the double-Ctrl timer so the synthetic Ctrl press below
            # cannot be mistaken for the second tap of a double-Ctrl open sequence.
            shortcut.reset_ctrl_timer()
            kb.press(Key.ctrl); kb.press('v')
            kb.release('v');    kb.release(Key.ctrl)
        except Exception:
            pass

    def _fill_template_popup(self, clip, placeholders):
        popup = tk.Toplevel(self.root)
        popup.title("Fill Template")
        popup.resizable(False, False)
        popup.configure(bg=BG)
        popup.grab_set()

        # Header
        hdr = tk.Frame(popup, bg=HEADER_BG, padx=16, pady=10)
        hdr.pack(fill="x")
        tk.Frame(hdr, bg=ACCENT, height=2).pack(fill="x", side="bottom")
        tk.Label(hdr, text="⟨⟩  Fill Template", font=("Segoe UI", 11, "bold"),
                 bg=HEADER_BG, fg=TEXT_DARK).pack(anchor="w")

        # Template preview (truncated)
        preview = clip["text"] if len(clip["text"]) <= 120 else clip["text"][:120] + "…"
        tk.Label(popup, text=preview, font=("Segoe UI", 8), bg=BG, fg=TEXT_GRAY,
                 wraplength=320, justify="left", padx=16, pady=5).pack(fill="x")

        tk.Frame(popup, bg=BORDER, height=1).pack(fill="x", padx=16)

        # One entry per placeholder
        entries = {}
        today   = __import__("datetime").date.today().strftime("%d %b %Y")
        form    = tk.Frame(popup, bg=BG, padx=16, pady=6)
        form.pack(fill="x")

        for ph in placeholders:
            row = tk.Frame(form, bg=BG)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"{{{ph}}}", font=("Segoe UI", 9, "bold"),
                     bg=BG, fg=ACCENT, width=14, anchor="w").pack(side="left")
            wrap = tk.Frame(row, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
            wrap.pack(side="left", fill="x", expand=True)
            var = tk.StringVar(value=today if ph == "date" else "")
            ent = tk.Entry(wrap, textvariable=var, font=("Segoe UI", 10),
                           bg=WHITE, fg=TEXT_DARK, relief="flat", bd=0,
                           insertbackground=ACCENT)
            ent.pack(fill="x", padx=8, pady=4)
            ent.bind("<FocusIn>",  lambda _e, w=wrap: w.config(highlightbackground=ACCENT))
            ent.bind("<FocusOut>", lambda _e, w=wrap: w.config(highlightbackground=BORDER))
            entries[ph] = var

        # Focus first field
        form.winfo_children()[0].winfo_children()[1].winfo_children()[0].focus_set()

        tk.Frame(popup, bg=BORDER, height=1).pack(fill="x", padx=16)

        def do_copy():
            result = clip["text"]
            for ph, var in entries.items():
                result = result.replace(f"{{{ph}}}", var.get())
            self._suppress_next_capture = True
            clipboard.set_clipboard(result)
            self._show_toast("Template copied ✅")
            popup.destroy()

        btn_row = tk.Frame(popup, bg=BG, padx=16, pady=8)
        btn_row.pack(fill="x")
        popup.bind("<Return>", lambda _e: do_copy())
        tk.Button(btn_row, text="Copy to Clipboard", bg=ACCENT, fg="white",
                  font=("Segoe UI", 9, "bold"), relief="flat", padx=14, pady=5,
                  cursor="hand2", bd=0, command=do_copy).pack(side="right")
        tk.Button(btn_row, text="Cancel", bg=WHITE, fg=TEXT_DARK,
                  font=("Segoe UI", 9), relief="flat", padx=10, pady=5,
                  cursor="hand2", bd=0, command=popup.destroy).pack(side="right", padx=(0, 8))

        # Size & center over main window
        popup.update_idletasks()
        pw = 540
        ph_h = popup.winfo_reqheight()
        x = self.root.winfo_x() + (self.root.winfo_width()  - pw)  // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - ph_h) // 2
        popup.geometry(f"{pw}x{ph_h}+{x}+{y}")

    def _settings_popup(self):
        if getattr(self, "_settings_win", None) and self._settings_win.winfo_exists():
            self._settings_win.lift()
            self._settings_win.focus_force()
            return
        s = storage.load_settings()
        popup = tk.Toplevel(self.root)
        self._settings_win = popup
        popup.title("Settings")
        popup.resizable(False, False)
        popup.configure(bg=BG)
        popup.grab_set()

        # Header
        hdr = tk.Frame(popup, bg=HEADER_BG, padx=16, pady=10)
        hdr.pack(fill="x")
        tk.Frame(hdr, bg=ACCENT, height=2).pack(fill="x", side="bottom")
        tk.Label(hdr, text="⚙  Settings", font=("Segoe UI", 11, "bold"),
                 bg=HEADER_BG, fg=TEXT_DARK).pack(anchor="w")

        form = tk.Frame(popup, bg=BG, padx=20, pady=16)
        form.pack(fill="x")

        # ── Helpers ──────────────────────────────────────────────────────
        CLIP_OPTIONS  = ["Unlimited", "10", "25", "50", "100", "200", "500"]
        EXPIRY_OPTIONS = {
            "Never":    None,
            "1 hour":   1,
            "6 hours":  6,
            "24 hours": 24,
            "48 hours": 48,
            "1 week": 168,
            }

        def _current_clip_label(v):
            return str(v) if v else "Unlimited"

        def _current_expiry_label(v):
            for label, hours in EXPIRY_OPTIONS.items():
                if hours == v:
                    return label
            return "Never"

        KB_CURSOR  = "#7B7FFF"   # lighter accent ring shown on keyboard-focused button

        def _option_row(parent, label, hint, choices, current):
            tk.Label(parent, text=label, font=("Segoe UI", 9, "bold"),
                     bg=BG, fg=TEXT_DARK).pack(anchor="w", pady=(14, 2))
            tk.Label(parent, text=hint, font=("Segoe UI", 8),
                     bg=BG, fg=TEXT_GRAY).pack(anchor="w", pady=(0, 6))
            btn_frame = tk.Frame(parent, bg=BG)
            btn_frame.pack(fill="x")
            var     = tk.StringVar(value=current)
            buttons = []   # list of (choice, tk.Button)

            def _repaint(selected, cursor_idx=None):
                for i, (ch, btn) in enumerate(buttons):
                    is_sel    = ch == selected
                    is_cursor = (cursor_idx is not None and i == cursor_idx)
                    btn.config(
                        bg=ACCENT if is_sel else WHITE,
                        fg="white" if is_sel else TEXT_DARK,
                        highlightthickness=2 if is_cursor else 0,
                        highlightbackground=KB_CURSOR,
                    )

            def _select(c):
                var.set(c)
                _repaint(c)

            for choice in choices:
                b = tk.Button(
                    btn_frame, text=choice,
                    font=("Segoe UI", 9),
                    bg=ACCENT if choice == current else WHITE,
                    fg="white" if choice == current else TEXT_DARK,
                    relief="flat", padx=10, pady=5,
                    cursor="hand2", bd=0,
                    command=lambda c=choice: _select(c),
                )
                b.pack(side="left", padx=(0, 4), pady=2)
                buttons.append((choice, b))

            return var, buttons, _repaint, _select

        clip_var, clip_btns, _, __ = _option_row(form,
            "Max clips to keep",
            "Pinned and tagged clips are always kept regardless of this limit.",
            CLIP_OPTIONS,
            _current_clip_label(s.get("max_clips"))
        )

        tk.Frame(form, bg=BORDER, height=1).pack(fill="x", pady=(12, 0))

        expiry_var, expiry_btns, expiry_repaint, expiry_select = _option_row(form,
            "Auto-delete clips after",
            "Pinned and tagged clips are exempt from expiry.",
            list(EXPIRY_OPTIONS.keys()),
            _current_expiry_label(s.get("max_hours"))
        )

        tk.Frame(form, bg=BORDER, height=1).pack(fill="x", pady=(12, 0))

        DEFAULTS = "keepass, bitwarden, 1password, lastpass, dashlane, nordpass"

        # Title row with live badge
        excl_hdr = tk.Frame(form, bg=BG)
        excl_hdr.pack(fill="x", pady=(14, 2))
        tk.Label(excl_hdr, text="Excluded apps", font=("Segoe UI", 9, "bold"),
                 bg=BG, fg=TEXT_DARK).pack(side="left")
        current_apps = [a.strip() for a in s.get("excluded_apps", []) if len(a.strip()) >= 5]
        badge_count  = len(current_apps)
        badge_text   = f"  {badge_count} app{'s' if badge_count != 1 else ''} excluded  "
        badge_lbl = tk.Label(excl_hdr, text=badge_text,
                             font=("Segoe UI", 8, "bold"),
                             bg="#1A6B3A", fg="#A8F0C0",
                             padx=4, pady=2)
        if badge_count:
            badge_lbl.pack(side="left", padx=(8, 0))

        tk.Label(form, text="Clips are never saved when these apps are in focus.",
                 font=("Segoe UI", 8), bg=BG, fg=TEXT_GRAY).pack(anchor="w", pady=(0, 6))

        excluded_frame = tk.Frame(form, bg=BORDER)
        excluded_frame.pack(fill="x", pady=(0, 2))

        # Placeholder behaviour — show defaults in gray when field is empty
        PLACEHOLDER_COLOR = "#505070"
        excluded_entry = tk.Entry(excluded_frame, font=("Segoe UI", 9),
                                  bg=WHITE, fg=TEXT_DARK, relief="flat",
                                  insertbackground=TEXT_DARK)
        excluded_entry.pack(fill="x", padx=1, pady=1)

        saved_val = ", ".join(s.get("excluded_apps", []))
        if saved_val:
            excluded_entry.insert(0, saved_val)
        else:
            excluded_entry.insert(0, DEFAULTS)
            excluded_entry.config(fg=PLACEHOLDER_COLOR)

        def _on_focus_in(*_):
            if excluded_entry.cget("fg") == PLACEHOLDER_COLOR:
                excluded_entry.delete(0, tk.END)
                excluded_entry.config(fg=TEXT_DARK)

        def _on_focus_out(*_):
            if not excluded_entry.get().strip():
                excluded_entry.insert(0, DEFAULTS)
                excluded_entry.config(fg=PLACEHOLDER_COLOR)

        def _update_badge(*_):
            raw = excluded_entry.get()
            if excluded_entry.cget("fg") == PLACEHOLDER_COLOR:
                count = 0
            else:
                count = len([a for a in raw.split(",") if len(a.strip()) >= 5])
            badge_lbl.config(text=f"  {count} app{'s' if count != 1 else ''} excluded  ")
            if count:
                badge_lbl.pack(side="left", padx=(8, 0))
            else:
                badge_lbl.pack_forget()

        excluded_entry.bind("<FocusIn>",  _on_focus_in)
        excluded_entry.bind("<FocusOut>", _on_focus_out)
        excluded_entry.bind("<KeyRelease>", _update_badge)

        # ── Advanced nav row (inside form, above action bar) ──────────────
        tk.Frame(form, bg=BORDER, height=1).pack(fill="x", pady=(14, 0))
        adv_nav_row = tk.Frame(form, bg=BG)
        adv_nav_row.pack(fill="x", pady=(6, 0))
        adv_nav_btn = tk.Button(adv_nav_row, text="⚙  Advanced Settings  →",
                                bg=BG, fg=TEXT_GRAY,
                                font=("Segoe UI", 9), relief="flat", padx=0, pady=4,
                                cursor="hand2", bd=0, activebackground=BG,
                                activeforeground=TEXT_DARK)
        adv_nav_btn.pack(side="left")
        _hover(adv_nav_btn, BG, BG, TEXT_GRAY, TEXT_DARK)

        # ── Popup close / save actions ────────────────────────────────────
        def _on_popup_close():
            self.root.bind("<Up>",     lambda _e: self._kb_nav(-1))
            self.root.bind("<Down>",   lambda _e: self._kb_nav(+1))
            self.root.bind("<Escape>", lambda _e: self._hide_window())
            popup.destroy()

        # ── Advanced page (hidden until user navigates to it) ─────────────
        adv_page = tk.Frame(popup, bg=BG, padx=20, pady=16)

        # Advanced page header
        adv_hdr = tk.Frame(popup, bg=HEADER_BG, padx=16, pady=10)
        tk.Frame(adv_hdr, bg=ACCENT, height=2).pack(fill="x", side="bottom")
        tk.Label(adv_hdr, text="⚙  Advanced Settings", font=("Segoe UI", 11, "bold"),
                 bg=HEADER_BG, fg=TEXT_DARK).pack(anchor="w")

        # ── Session gap ───────────────────────────────────────────────────
        SESSION_GAP_OPTIONS = {"15 min": 15, "30 min": 30, "60 min": 60}

        def _current_gap_label(v):
            for label, val in SESSION_GAP_OPTIONS.items():
                if val == v:
                    return label
            return "30 min"

        gap_var, gap_btns, *_ = _option_row(adv_page,
            "Clipboard Time Machine — session gap",
            "Groups clips into sessions in the main list. Pinned clips are always at top.",
            list(SESSION_GAP_OPTIONS.keys()),
            _current_gap_label(s.get("session_gap_minutes", 30))
        )

        tk.Frame(adv_page, bg=BORDER, height=1).pack(fill="x", pady=(12, 0))

        # ── Auto-start toggle ─────────────────────────────────────────────
        tk.Label(adv_page, text="Launch at startup", font=("Segoe UI", 9, "bold"),
                 bg=BG, fg=TEXT_DARK).pack(anchor="w", pady=(14, 2))
        tk.Label(adv_page, text="Automatically start Smart Clipboard when Windows starts.",
                 font=("Segoe UI", 8), bg=BG, fg=TEXT_GRAY).pack(anchor="w", pady=(0, 6))

        auto_start_var = tk.BooleanVar(value=s.get("auto_start", True))
        auto_row = tk.Frame(adv_page, bg=BG)
        auto_row.pack(anchor="w")
        auto_btns = []
        for label, val in [("On", True), ("Off", False)]:
            cur = auto_start_var.get() == val
            b = tk.Button(auto_row, text=label, font=("Segoe UI", 9),
                          bg=ACCENT if cur else WHITE,
                          fg="white" if cur else TEXT_DARK,
                          relief="flat", padx=14, pady=5, cursor="hand2", bd=0)
            def _set_auto(v=val, btn=b):
                auto_start_var.set(v)
                for child in auto_row.winfo_children():
                    child.config(bg=WHITE, fg=TEXT_DARK)
                btn.config(bg=ACCENT, fg="white")
            b.config(command=_set_auto)
            b.pack(side="left", padx=(0, 4))
            auto_btns.append((label, b))

        tk.Frame(adv_page, bg=BORDER, height=1).pack(fill="x", pady=(12, 0))

        # ── Global shortcuts toggle ───────────────────────────────────────
        tk.Label(adv_page, text="Enable global shortcuts", font=("Segoe UI", 9, "bold"),
                 bg=BG, fg=TEXT_DARK).pack(anchor="w", pady=(14, 2))
        tk.Label(adv_page, text="Disable if keyboard shortcuts conflict with other apps.\nChanges take effect on next launch.",
                 font=("Segoe UI", 8), bg=BG, fg=TEXT_GRAY, justify="left").pack(anchor="w", pady=(0, 6))

        gs_var = tk.BooleanVar(value=s.get("global_shortcuts", True))
        gs_row = tk.Frame(adv_page, bg=BG)
        gs_row.pack(anchor="w")
        gs_btns = []
        for label, val in [("On", True), ("Off", False)]:
            cur = gs_var.get() == val
            b = tk.Button(gs_row, text=label, font=("Segoe UI", 9),
                          bg=ACCENT if cur else WHITE,
                          fg="white" if cur else TEXT_DARK,
                          relief="flat", padx=14, pady=5, cursor="hand2", bd=0)
            def _set_gs(v=val, btn=b):
                gs_var.set(v)
                for child in gs_row.winfo_children():
                    child.config(bg=WHITE, fg=TEXT_DARK)
                btn.config(bg=ACCENT, fg="white")
            b.config(command=_set_gs)
            b.pack(side="left", padx=(0, 4))
            gs_btns.append((label, b))

        personalize_btn = tk.Button(gs_row, text="Personalize",
                                    font=("Segoe UI", 9), bg=WHITE, fg=TEXT_DARK,
                                    relief="flat", padx=12, pady=5, cursor="hand2", bd=0,
                                    command=lambda: self._shortcut_personalize_popup(popup))
        personalize_btn.pack(side="left", padx=(8, 0))
        gs_btns.append(("Personalize", personalize_btn))

        # ── Store sensitive content toggle ────────────────────────────────
        tk.Frame(adv_page, bg=BORDER, height=1).pack(fill="x", pady=(12, 0))
        tk.Label(adv_page, text="Store sensitive content", font=("Segoe UI", 9, "bold"),
                 bg=BG, fg=TEXT_DARK).pack(anchor="w", pady=(14, 2))
        tk.Label(adv_page, text="By default passwords, credit cards and SSNs are blocked.",
                 font=("Segoe UI", 8), bg=BG, fg=TEXT_GRAY).pack(anchor="w", pady=(0, 6))

        sens_var = tk.BooleanVar(value=s.get("store_sensitive", False))
        sens_row = tk.Frame(adv_page, bg=BG)
        sens_row.pack(anchor="w")

        # Container always occupies the correct slot in pack order.
        # The label is shown/hidden inside it so it never re-appends to the end.
        sens_warn_container = tk.Frame(adv_page, bg=BG)
        sens_warn_container.pack(anchor="w", fill="x")
        sens_warning = tk.Label(sens_warn_container,
                                text="⚠️ Passwords and card numbers will be saved to disk.",
                                font=("Segoe UI", 8), bg=BG, fg=TEXT_GRAY)
        if sens_var.get():
            sens_warning.pack(anchor="w", pady=(4, 0))

        sens_btns = []
        for label, val in [("On", True), ("Off", False)]:
            cur = sens_var.get() == val
            b = tk.Button(sens_row, text=label, font=("Segoe UI", 9),
                          bg=ACCENT if cur else WHITE,
                          fg="white" if cur else TEXT_DARK,
                          relief="flat", padx=14, pady=5, cursor="hand2", bd=0)
            def _set_sens(v=val, btn=b):
                sens_var.set(v)
                for child in sens_row.winfo_children():
                    child.config(bg=WHITE, fg=TEXT_DARK)
                btn.config(bg=ACCENT, fg="white")
                if v:
                    sens_warning.pack(anchor="w", pady=(4, 0))
                else:
                    sens_warning.pack_forget()
                _resize_popup()
            b.config(command=_set_sens)
            b.pack(side="left", padx=(0, 4))
            sens_btns.append((label, b))

        # ── Export clips (advanced page) ──────────────────────────────────
        tk.Frame(adv_page, bg=BORDER, height=1).pack(fill="x", pady=(12, 0))

        def _export_clips():
            import tkinter.filedialog as fd, json as _json
            clips = storage.load_clips()
            if not clips:
                self._show_toast("Nothing to export!")
                return
            path = fd.asksaveasfilename(
                parent=popup,
                title="Export clips",
                defaultextension=".json",
                filetypes=[("JSON file", "*.json"), ("Text file", "*.txt")],
                initialfile="smart_clipboard_export"
            )
            if not path:
                return
            if path.endswith(".txt"):
                with open(path, "w", encoding="utf-8") as f:
                    for c in clips:
                        f.write(c["text"] + "\n" + ("-" * 40) + "\n")
            else:
                with open(path, "w", encoding="utf-8") as f:
                    _json.dump(clips, f, indent=2, ensure_ascii=False)
            self._show_toast(f"Exported {len(clips)} clips ✅")

        export_btn = tk.Button(adv_page, text="⬆  Export clips",
                               bg=WHITE, fg=TEXT_GRAY,
                               font=("Segoe UI", 9), relief="flat", padx=12, pady=7,
                               cursor="hand2", bd=0, command=_export_clips)
        export_btn.pack(anchor="w", pady=(12, 0))

        # ── Page switching ────────────────────────────────────────────────
        def _resize_popup():
            popup.update_idletasks()
            ph = popup.winfo_reqheight()
            sw = popup.winfo_screenwidth()
            sh = popup.winfo_screenheight()
            x = (sw - 420) // 2
            y = max(0, min((sh - ph) // 2 - 60, sh - ph))
            popup.geometry(f"420x{ph}+{x}+{y}")

        def _show_adv_page():
            hdr.pack_forget()
            form.pack_forget()
            main_sep.pack_forget()
            btn_row.pack_forget()
            adv_hdr.pack(fill="x")
            adv_page.pack(fill="x")
            adv_sep.pack(fill="x", padx=20, pady=(12, 0))
            adv_btn_row.pack(fill="x")
            _resize_popup()
            _switch_page("adv")

        adv_nav_btn.config(command=_show_adv_page)

        def _show_main_page():
            adv_hdr.pack_forget()
            adv_page.pack_forget()
            adv_sep.pack_forget()
            adv_btn_row.pack_forget()
            hdr.pack(fill="x")
            form.pack(fill="x")
            main_sep.pack(fill="x", padx=20, pady=(12, 0))
            btn_row.pack(fill="x")
            _resize_popup()
            _switch_page("main")

        def save():
            mc = None if clip_var.get() == "Unlimited" else int(clip_var.get())
            mh = EXPIRY_OPTIONS[expiry_var.get()]
            apps = [a.strip() for a in excluded_entry.get().split(",") if len(a.strip()) >= 5]
            sg = SESSION_GAP_OPTIONS[gap_var.get()]
            merged = storage.load_settings()
            merged.update({"max_clips": mc, "max_hours": mh,
                           "excluded_apps": apps,
                           "auto_start": auto_start_var.get(),
                           "global_shortcuts": gs_var.get(),
                           "session_gap_minutes": sg,
                           "store_sensitive": sens_var.get()})
            storage.save_settings(merged)
            self._add_to_startup()
            self._refresh_list()
            self._show_toast("Settings saved ✅")
            _on_popup_close()

        # ── Main page action buttons ──────────────────────────────────────
        main_sep = tk.Frame(popup, bg=BORDER, height=1)
        btn_row   = tk.Frame(popup, bg=BG, padx=20, pady=12)

        def _replay_tutorial():
            _on_popup_close()
            s2 = storage.load_settings()
            s2["onboarding_complete"] = False
            storage.save_settings(s2)
            from onboarding import Onboarding
            Onboarding(self).start()

        replay_btn = tk.Button(btn_row, text="↺  Replay tutorial",
                               bg=WHITE, fg=TEXT_GRAY,
                               font=("Segoe UI", 9), relief="flat", padx=12, pady=7,
                               cursor="hand2", bd=0, command=_replay_tutorial)
        replay_btn.pack(side="left")

        def _give_feedback():
            import webbrowser
            webbrowser.open("https://github.com/ezeiq7/Smart-Clipboard/issues")

        feedback_btn = tk.Button(btn_row, text="💬  Give Feedback",
                                 bg=WHITE, fg=TEXT_GRAY,
                                 font=("Segoe UI", 9), relief="flat", padx=12, pady=7,
                                 cursor="hand2", bd=0, command=_give_feedback)
        feedback_btn.pack(side="left", padx=(8, 0))

        save_btn = tk.Button(btn_row, text="Save", bg=ACCENT, fg="white",
                             font=("Segoe UI", 9, "bold"), relief="flat", padx=14, pady=7,
                             cursor="hand2", bd=0, command=save)
        save_btn.pack(side="right")
        cancel_btn = tk.Button(btn_row, text="Cancel", bg=WHITE, fg=TEXT_DARK,
                               font=("Segoe UI", 9, "bold"), relief="flat", padx=14, pady=7,
                               cursor="hand2", bd=0, command=_on_popup_close)
        cancel_btn.pack(side="right", padx=(8, 8))

        # Pack main page
        main_sep.pack(fill="x", padx=20, pady=(12, 0))
        btn_row.pack(fill="x")

        # ── Advanced page action buttons ──────────────────────────────────
        adv_sep     = tk.Frame(popup, bg=BORDER, height=1)
        adv_btn_row = tk.Frame(popup, bg=BG, padx=20, pady=12)

        back_btn = tk.Button(adv_btn_row, text="← Back",
                             bg=WHITE, fg=TEXT_GRAY,
                             font=("Segoe UI", 9), relief="flat", padx=12, pady=7,
                             cursor="hand2", bd=0, command=_show_main_page)
        back_btn.pack(side="left")

        adv_save_btn = tk.Button(adv_btn_row, text="Save", bg=ACCENT, fg="white",
                                 font=("Segoe UI", 10, "bold"), relief="flat", padx=14, pady=7,
                                 cursor="hand2", bd=0, command=save)
        adv_save_btn.pack(side="right")
        adv_cancel_btn = tk.Button(adv_btn_row, text="Cancel", bg=WHITE, fg=TEXT_DARK,
                                   font=("Segoe UI", 10, "bold"), relief="flat", padx=14, pady=7,
                                   cursor="hand2", bd=0, command=_on_popup_close)
        adv_cancel_btn.pack(side="right", padx=(8, 8))

        # ── Keyboard navigation ───────────────────────────────────────────
        # Separate row maps per page so navigation never crosses invisible buttons.
        # A single popup-level binding drives everything; no per-button bindings.

        action_btns     = [("↺", replay_btn), ("💬", feedback_btn),
                           ("Cancel", cancel_btn), ("Save", save_btn)]
        adv_action_btns = [("← Back", back_btn), ("Cancel", adv_cancel_btn),
                           ("Save", adv_save_btn)]

        main_rows = [clip_btns, expiry_btns, [("Advanced →", adv_nav_btn)], action_btns]
        adv_rows  = [gap_btns, auto_btns, gs_btns, sens_btns, [("Export", export_btn)], adv_action_btns]

        nav = {"page": "main", "main": [0, 0], "adv": [0, 0]}

        def _cur_rows():
            return main_rows if nav["page"] == "main" else adv_rows

        def _cur_pos():
            return nav[nav["page"]]

        def _highlight():
            # Clear all highlights across both pages, then mark active cursor.
            for rows in (main_rows, adv_rows):
                for row in rows:
                    for _, b in row:
                        b.config(highlightthickness=0)
            rows = _cur_rows()
            ri, ci = _cur_pos()
            b = rows[ri][ci][1]
            b.config(highlightthickness=2, highlightbackground=KB_CURSOR)
            b.focus_set()

        def _switch_page(page):
            nav["page"] = page
            nav[page]   = [0, 0]   # reset cursor to first button on the new page
            _highlight()

        def _move(dr, dc):
            if popup.focus_get() is excluded_entry:
                return
            rows   = _cur_rows()
            pos    = _cur_pos()
            ri, ci = pos[0], pos[1]
            if dc != 0:
                pos[1] = (ci + dc) % len(rows[ri])
            else:
                new_ri = (ri + dr) % len(rows)
                pos[0] = new_ri
                pos[1] = min(ci, len(rows[new_ri]) - 1)
            _highlight()

        def _invoke():
            if popup.focus_get() is excluded_entry:
                return
            rows   = _cur_rows()
            ri, ci = _cur_pos()
            rows[ri][ci][1].invoke()

        for rows in (main_rows, adv_rows):
            for row in rows:
                for _, b in row:
                    b.config(takefocus=0)

        # Disable main window arrow keys while popup is open
        self.root.unbind("<Up>")
        self.root.unbind("<Down>")
        self.root.unbind("<Escape>")

        popup.protocol("WM_DELETE_WINDOW", _on_popup_close)
        popup.bind("<Escape>", lambda _e: _on_popup_close())
        popup.bind("<Left>",   lambda _e: (_move(0, -1), "break")[1])
        popup.bind("<Right>",  lambda _e: (_move(0, +1), "break")[1])
        popup.bind("<Up>",     lambda _e: (_move(-1, 0), "break")[1])
        popup.bind("<Down>",   lambda _e: (_move(+1, 0), "break")[1])
        popup.bind("<Return>", lambda _e: (_invoke(),    "break")[1])
        popup.bind("<space>",  lambda _e: (_invoke(),    "break")[1])

        # Size and center on screen — clamped so the popup is always fully visible
        popup.update_idletasks()
        pw = 420
        ph = popup.winfo_reqheight()
        sw = popup.winfo_screenwidth()
        sh = popup.winfo_screenheight()
        x  = (sw - pw) // 2
        y  = (sh - ph) // 2 - 60
        x  = max(0, min(x, sw - pw))
        y  = max(0, min(y, sh - ph))
        popup.geometry(f"{pw}x{ph}+{x}+{y}")

        popup.grab_set()
        popup.lift()
        popup.focus_force()

        # Focus the currently-selected clip-limit button on open
        first_focus_idx = CLIP_OPTIONS.index(_current_clip_label(s.get("max_clips")))
        nav["main"] = [0, first_focus_idx]
        popup.after(50, _highlight)

    # ── Shortcut personalisation popup ────────────────────────────────────────

    def _shortcut_personalize_popup(self, parent=None):
        SHORTCUT_DEFS = [
            ("shortcut_launcher",     "Ctrl+Shift+V",       "Quick-paste launcher"),
            ("shortcut_toggle",       "Ctrl+Shift+E",       "Toggle capture on/off"),
            ("shortcut_incognito",    "Ctrl+Shift+X",       "Private mode"),
            ("shortcut_pin",          "Ctrl+Alt+C",         "Capture and pin"),
            ("shortcut_show",         "Double-tap Ctrl",    "Open Smart Clipboard"),
            ("shortcut_peek",         "Ctrl+Shift (hold)",  "Clipboard Peek"),
            ("shortcut_hotkey_clips", "Ctrl+Shift+1–9",     "Hotkey clips"),
        ]

        s   = storage.load_settings()
        win = tk.Toplevel(self.root)
        win.title("Personalize shortcuts")
        win.resizable(False, False)
        win.configure(bg=BG)
        if parent:
            win.transient(parent)
        win.grab_set()

        # Header
        hdr = tk.Frame(win, bg=HEADER_BG, padx=16, pady=10)
        hdr.pack(fill="x")
        tk.Frame(hdr, bg=ACCENT, height=2).pack(fill="x", side="bottom")
        tk.Label(hdr, text="⌨  Personalize shortcuts",
                 font=("Segoe UI", 11, "bold"), bg=HEADER_BG, fg=TEXT_DARK).pack(anchor="w")
        tk.Label(hdr, text="Changes take effect on next launch.",
                 font=("Segoe UI", 8), bg=HEADER_BG, fg=TEXT_GRAY).pack(anchor="w", pady=(2, 0))

        form = tk.Frame(win, bg=BG, padx=20, pady=8)
        form.pack(fill="x")

        KB_CURSOR = "#7B7FFF"
        vars_     = {}   # key -> BooleanVar
        rows_     = []   # (BooleanVar, btn_row_frame) for reset
        nav_rows  = []   # list of [(label, btn), …] for arrow-key nav

        for i, (key, combo, desc) in enumerate(SHORTCUT_DEFS):
            if i > 0:
                tk.Frame(form, bg=BORDER, height=1).pack(fill="x")

            row = tk.Frame(form, bg=BG, pady=9)
            row.pack(fill="x")

            # Left column: shortcut combo + description
            left = tk.Frame(row, bg=BG)
            left.pack(side="left", fill="x", expand=True)
            tk.Label(left, text=combo, font=("Segoe UI", 9, "bold"),
                     bg=BG, fg=TEXT_DARK).pack(anchor="w")
            tk.Label(left, text=desc, font=("Segoe UI", 8),
                     bg=BG, fg=TEXT_GRAY).pack(anchor="w")

            # Right column: On / Off toggle
            right   = tk.Frame(row, bg=BG)
            right.pack(side="right")
            btn_row = tk.Frame(right, bg=BG)
            btn_row.pack()

            var = tk.BooleanVar(value=s.get(key, True))
            vars_[key] = var
            rows_.append((var, btn_row))

            row_btns = []
            for label, val in [("On", True), ("Off", False)]:
                cur = var.get() == val
                b   = tk.Button(btn_row, text=label, font=("Segoe UI", 9),
                                bg=ACCENT if cur else WHITE,
                                fg="white" if cur else TEXT_DARK,
                                relief="flat", padx=12, pady=4, cursor="hand2", bd=0)
                def _set(v=val, bv=var, br=btn_row, active=b):
                    bv.set(v)
                    for child in br.winfo_children():
                        child.config(bg=WHITE, fg=TEXT_DARK)
                    active.config(bg=ACCENT, fg="white")
                b.config(command=_set)
                b.pack(side="left", padx=(0, 4))
                row_btns.append((label, b))
            nav_rows.append(row_btns)

        # Divider + action row
        tk.Frame(win, bg=BORDER, height=1).pack(fill="x", padx=20, pady=(4, 0))
        btn_frame = tk.Frame(win, bg=BG, padx=20, pady=12)
        btn_frame.pack(fill="x")

        def _reset():
            for bv, br in rows_:
                bv.set(True)
                children = br.winfo_children()
                if len(children) >= 2:
                    children[0].config(bg=ACCENT, fg="white")
                    children[1].config(bg=WHITE,  fg=TEXT_DARK)

        def _close():
             win.destroy()
             if parent and parent.winfo_exists():
              parent.grab_set()
             parent.lift()
             parent.focus_force()
              

        def _save():
             current = storage.load_settings()
             for key, var in vars_.items():
              current[key] = var.get()
             storage.save_settings(current)
             _close()
             self.root.after(100, lambda: self._show_toast("Shortcut preferences saved ✅"))

        reset_btn  = tk.Button(btn_frame, text="Reset all", bg=WHITE, fg=TEXT_GRAY,
                               font=("Segoe UI", 9), relief="flat", padx=12, pady=7,
                               cursor="hand2", bd=0, command=_reset)
        reset_btn.pack(side="left")
        cancel_btn = tk.Button(btn_frame, text="Cancel", bg=WHITE, fg=TEXT_DARK,
                               font=("Segoe UI", 10, "bold"), relief="flat", padx=14, pady=7,
                               cursor="hand2", bd=0, command=_close)
        cancel_btn.pack(side="right", padx=(8, 0))
        save_btn   = tk.Button(btn_frame, text="Save", bg=ACCENT, fg="white",
                               font=("Segoe UI", 10, "bold"), relief="flat", padx=14, pady=7,
                               cursor="hand2", bd=0, command=_save)
        save_btn.pack(side="right")
        nav_rows.append([("Reset all", reset_btn), ("Cancel", cancel_btn), ("Save", save_btn)])

        # ── Arrow-key navigation (index-tracked at window level) ─────────
        _pos = [0, 0]   # [row, col]

        def _focus_pos(ri, ci):
            ci = max(0, min(ci, len(nav_rows[ri]) - 1))
            _pos[0], _pos[1] = ri, ci
            btn = nav_rows[ri][ci][1]
            btn.focus_set()
            for nr in nav_rows:
                for _, rb in nr:
                    rb.config(highlightthickness=0)
            btn.config(highlightthickness=2, highlightbackground=KB_CURSOR)

        def _win_nav(e):
            ri, ci = _pos
            key = e.keysym
            if key == "Left":
                _focus_pos(ri, (ci - 1) % len(nav_rows[ri]))
            elif key == "Right":
                _focus_pos(ri, (ci + 1) % len(nav_rows[ri]))
            elif key == "Up":
                new_ri  = (ri - 1) % len(nav_rows)
                src_len = len(nav_rows[ri])
                dst_len = len(nav_rows[new_ri])
                new_ci  = min(round(ci * max(dst_len - 1, 0) / max(src_len - 1, 1)), dst_len - 1)
                _focus_pos(new_ri, new_ci)
            elif key == "Down":
                new_ri  = (ri + 1) % len(nav_rows)
                src_len = len(nav_rows[ri])
                dst_len = len(nav_rows[new_ri])
                new_ci  = min(round(ci * max(dst_len - 1, 0) / max(src_len - 1, 1)), dst_len - 1)
                _focus_pos(new_ri, new_ci)
            elif key in ("Return", "space"):
                nav_rows[ri][ci][1].invoke()
            return "break"

        for seq in ("<Left>", "<Right>", "<Up>", "<Down>", "<space>"):
            win.bind(seq, _win_nav)

        # Size and centre relative to parent (or main window)
        win.update_idletasks()
        pw  = 400
        ph  = win.winfo_reqheight()
        ref = parent if parent else self.root
        x   = ref.winfo_x() + (ref.winfo_width()  - pw) // 2
        y   = ref.winfo_y() + (ref.winfo_height() - ph) // 2
        win.geometry(f"{pw}x{ph}+{x}+{y}")

        win.lift()
        win.bind("<Escape>", lambda _: _close())
        win.bind("<Return>", lambda _: nav_rows[_pos[0]][_pos[1]][1].invoke())
        win.after(50, lambda: _focus_pos(0, 0))

    def _set_tag(self, tag):
        sel = self.listbox.curselection()
        if not sel:
            self._show_toast("Select a clip first!")
            return
        for i in sel:
            clip = self._clip_at(i)
            if clip is not None:
                storage.set_tag(clip["text"], tag if tag else "none")
        self._refresh_list()
        n = len(sel)
        if n > 1:
            msg = f"Tagged {n} clips ✅" if tag else f"Removed tag from {n} clips ✅"
        else:
            msg = f"Tagged as {tag} ✅" if tag else "Tag removed ✅"
        self._show_toast(msg)

    # ── Tag menu ───────────────────────────────────────────────────────────

    def _show_tag_menu(self):
        menu = tk.Menu(self.root, tearoff=0, bg=WHITE, fg=TEXT_DARK,
                       activebackground=ACCENT, activeforeground="white",
                       font=("Segoe UI", 9), bd=0)
        for tag in tags.load_tags():
            menu.add_command(label=f"  {tag}", command=lambda t=tag: self._set_tag(t))
        menu.add_separator()
        menu.add_command(label="  ✕  Remove tag",   command=lambda: self._set_tag(None))
        menu.add_separator()
        menu.add_command(label="  +  New tag",       command=self._add_tag_popup)
        menu.add_separator()
        menu.add_command(label="  ⚙  Manage tags",   command=self._manage_tags_popup)
        x = self._tag_btn.winfo_rootx()
        y = self._tag_btn.winfo_rooty() + self._tag_btn.winfo_height()
        menu.tk_popup(x, y)

    def _add_tag_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("New Tag")
        popup.geometry("280x120")
        popup.resizable(False, False)
        popup.configure(bg=BG)
        popup.grab_set()

        tk.Label(popup, text="Tag name", bg=BG, fg=TEXT_GRAY,
                 font=("Segoe UI", 9)).pack(pady=(14, 4))

        entry_var = tk.StringVar()
        wrap = tk.Frame(popup, bg=WHITE, padx=8, pady=4,
                        highlightbackground=BORDER, highlightthickness=1)
        wrap.pack(fill="x", padx=20)
        entry = tk.Entry(wrap, textvariable=entry_var, font=("Segoe UI", 10),
                         bg=WHITE, fg=TEXT_DARK, relief="flat", bd=0,
                         insertbackground=TEXT_DARK)
        entry.pack(fill="x")
        entry.focus()
        entry.bind("<FocusIn>",  lambda _: wrap.config(highlightbackground=ACCENT))
        entry.bind("<FocusOut>", lambda _: wrap.config(highlightbackground=BORDER))

        def save():
            tag = entry_var.get().strip().lower()
            if tag:
                tags.save_tag(tag)
                self._rebuild_tag_filter()
                popup.destroy()

        entry.bind("<Return>", lambda e: save())
        tk.Button(popup, text="Add Tag", bg=ACCENT, fg="white", relief="flat",
                  padx=14, pady=5, cursor="hand2", bd=0,
                  font=("Segoe UI", 9, "bold"), command=save).pack(pady=10)

    def _manage_tags_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("Manage Tags")
        popup.geometry("320x380")
        popup.resizable(False, False)
        popup.configure(bg=BG)
        popup.grab_set()

        tk.Label(popup, text="Your Tags", bg=BG, fg=TEXT_DARK,
                 font=("Segoe UI", 12, "bold")).pack(pady=(18, 10))

        frame = tk.Frame(popup, bg=BG)
        frame.pack(fill="both", expand=True, padx=16)

        def refresh():
            for w in frame.winfo_children():
                w.destroy()
            for tag in tags.load_tags():
                row = tk.Frame(frame, bg=WHITE, padx=8, pady=5)
                row.pack(fill="x", pady=2)
                color = get_tag_color(tag)
                tk.Label(row, text=f"●  {tag}", bg=WHITE, fg=color,
                         font=("Segoe UI", 10)).pack(side="left")
                del_b = tk.Button(row, text="✕", bg=WHITE, fg=DANGER,
                                  font=("Segoe UI", 9, "bold"), relief="flat",
                                  padx=6, cursor="hand2", bd=0,
                                  command=lambda t=tag: delete(t))
                del_b.pack(side="right", padx=(4, 0))
                _hover(del_b, WHITE, "#3A1A1A", DANGER, DANGER)
                ren_b = tk.Button(row, text="✎", bg=WHITE, fg=TEXT_GRAY,
                                  font=("Segoe UI", 9), relief="flat",
                                  padx=6, cursor="hand2", bd=0,
                                  command=lambda t=tag: rename(t))
                ren_b.pack(side="right")
                _hover(ren_b, WHITE, BORDER)

        def delete(tag):
            tags.delete_tag(tag)
            self._rebuild_tag_filter()
            self.tag_filter_var.set("all")
            self._refresh_list()
            refresh()

        def rename(tag):
            rp = tk.Toplevel(popup)
            rp.title("Rename Tag")
            rp.geometry("260x100")
            rp.resizable(False, False)
            rp.configure(bg=BG)
            rp.grab_set()

            entry_var = tk.StringVar(value=tag)
            wrap = tk.Frame(rp, bg=WHITE, padx=8, pady=4,
                            highlightbackground=BORDER, highlightthickness=1)
            wrap.pack(fill="x", padx=16, pady=(16, 8))
            entry = tk.Entry(wrap, textvariable=entry_var, font=("Segoe UI", 10),
                             bg=WHITE, fg=TEXT_DARK, relief="flat", bd=0,
                             insertbackground=TEXT_DARK)
            entry.pack(fill="x")
            entry.focus()
            entry.select_range(0, tk.END)
            entry.bind("<FocusIn>",  lambda _: wrap.config(highlightbackground=ACCENT))
            entry.bind("<FocusOut>", lambda _: wrap.config(highlightbackground=BORDER))

            def save():
                new = entry_var.get().strip().lower()
                if new and new != tag:
                    tags.rename_tag(tag, new)
                    self._rebuild_tag_filter()
                    self._refresh_list()
                    refresh()
                rp.destroy()

            entry.bind("<Return>", lambda e: save())
            tk.Button(rp, text="Save", bg=ACCENT, fg="white", relief="flat",
                      padx=14, pady=5, cursor="hand2", bd=0,
                      font=("Segoe UI", 9, "bold"), command=save).pack()

        refresh()
        tk.Button(popup, text="Done", bg=ACCENT, fg="white", relief="flat",
                  padx=20, pady=6, cursor="hand2", bd=0,
                  font=("Segoe UI", 9, "bold"),
                  command=popup.destroy).pack(pady=14)

    # ── Tag filter ─────────────────────────────────────────────────────────

    def _rebuild_tag_filter(self):
        self._set_tag_filter("all")

    def _show_tag_filter_menu(self):
        menu = tk.Menu(self.root, tearoff=0, bg=WHITE, fg=TEXT_DARK,
                       activebackground=ACCENT, activeforeground="white",
                       font=("Segoe UI", 9), bd=0)
        menu.add_command(label="  all", command=lambda: self._set_tag_filter("all"))
        for tag in tags.load_tags():
            menu.add_command(label=f"  {tag}", command=lambda t=tag: self._set_tag_filter(t))
        x = self.tag_filter_btn.winfo_rootx()
        y = self.tag_filter_btn.winfo_rooty() + self.tag_filter_btn.winfo_height()
        menu.tk_popup(x, y)

    def _set_tag_filter(self, tag):
        self.tag_filter_var.set(tag)
        if tag == "all":
            self.tag_filter_btn.config(text="all ▾", fg=TEXT_DARK, bg=WHITE)
        else:
            self.tag_filter_btn.config(text=f"{tag} ▾", fg="white",
                                        bg=get_tag_color(tag))
        self._refresh_list()

    # ── Data helpers ───────────────────────────────────────────────────────

    def _get_current_clips(self):
        query      = self.search_var.get()      if hasattr(self, "search_var")      else ""
        tag_filter = self.tag_filter_var.get()  if hasattr(self, "tag_filter_var")  else "all"
        incognito  = list(self._incognito_clips) if self._incognito else []
        if query:
            base = storage.search_clips(query)
            if incognito:
                q = query.lower()
                _words = [w for w in q.split() if w]
                incognito = [c for c in incognito
                             if q in c["text"].lower()
                             or (bool(_words) and all(w in c["text"].lower() for w in _words))]
            return incognito + base
        if tag_filter != "all":
            return storage.filter_by_tag(tag_filter)
        return incognito + self._sorted_clips()

    def _sorted_clips(self):
        from datetime import datetime
        clips = storage.load_clips()
        sort  = self.sort_var.get() if hasattr(self, "sort_var") else "Newest"
        def _date_key(c):
            try:
                return datetime.strptime(c.get("date", ""), "%d %b %Y, %H:%M")
            except Exception:
                return datetime.min
        if   sort == "Newest": sc = sorted(clips, key=_date_key, reverse=True)
        elif sort == "Oldest": sc = sorted(clips, key=_date_key)
        elif sort == "A-Z":    sc = sorted(clips, key=lambda c: c["text"].lower())
        elif sort == "Z-A":    sc = sorted(clips, key=lambda c: c["text"].lower(), reverse=True)
        else:                  sc = sorted(clips, key=_date_key, reverse=True)
        return [c for c in sc if c.get("pinned")] + [c for c in sc if not c.get("pinned")]

    def _build_session_groups(self, clips, gap_minutes):
        """Insert session_header dicts between groups of clips separated by gap_minutes.
        Pinned clips are kept at the top without headers. Returns a display-items list."""
        from datetime import datetime, timedelta

        pinned   = [c for c in clips if c.get("pinned")]
        unpinned = [c for c in clips if not c.get("pinned")]

        def _parse(clip):
            try:
                return datetime.strptime(clip["date"], "%d %b %Y, %H:%M")
            except Exception:
                return None

        def _header_label(session):
            dates = [_parse(c) for c in session]
            dates = [d for d in dates if d]
            if not dates:
                return None
            earliest, latest = min(dates), max(dates)
            today     = datetime.now().date()
            yesterday = today - timedelta(days=1)
            if earliest.date() == today:
                day_str = "Today"
            elif earliest.date() == yesterday:
                day_str = "Yesterday"
            else:
                day_str = earliest.strftime("%d %b")
            if earliest == latest:
                return f"🕐  {day_str},  {earliest.strftime('%H:%M')}"
            return f"🕐  {day_str},  {earliest.strftime('%H:%M')} — {latest.strftime('%H:%M')}"

        sessions = []
        current  = []
        for clip in unpinned:
            if not current:
                current.append(clip)
            else:
                prev_dt = _parse(current[-1])
                curr_dt = _parse(clip)
                if prev_dt and curr_dt:
                    diff = abs((prev_dt - curr_dt).total_seconds()) / 60
                    if diff > gap_minutes:
                        sessions.append(current)
                        current = [clip]
                        continue
                current.append(clip)
        if current:
            sessions.append(current)

        result = list(pinned)
        for session in sessions:
            label = _header_label(session)
            if label:
                result.append({"type": "session_header", "label": label})
            result.extend(session)
        return result

    def _clip_at(self, lb_idx):
        """Return clip dict at listbox index lb_idx, or None if it's a header/out of range."""
        items = getattr(self, "_display_items", None)
        if items is None or lb_idx < 0 or lb_idx >= len(items):
            return None
        item = items[lb_idx]
        if isinstance(item, dict) and item.get("type") == "session_header":
            return None
        return item

    def _refresh_list(self):
        clips = self._get_current_clips()
        self.listbox.delete(0, tk.END)

        if not clips:
            self._display_items = []
            self.listbox.insert(tk.END, "")
            self.listbox.insert(tk.END, "")
            self.listbox.insert(tk.END, "            📋")
            self.listbox.insert(tk.END, "")
            self.listbox.insert(tk.END, "      Nothing here yet")
            self.listbox.insert(tk.END, "")
            self.listbox.insert(tk.END, "   ◦  Press Ctrl+C anywhere to capture a clip")
            self.listbox.insert(tk.END, "   ◦  Press Ctrl+Alt+C to pin directly")
            try:
                self.listbox.itemconfig(2, fg=ACCENT,     bg=WHITE)
                self.listbox.itemconfig(4, fg=TEXT_DARK,  bg=WHITE)
                self.listbox.itemconfig(6, fg=TEXT_GRAY,  bg=WHITE)
                self.listbox.itemconfig(7, fg=TEXT_GRAY,  bg=WHITE)
            except:
                pass
            total = 0
        else:
            # Decide whether to show session headers
            tag_filter = self.tag_filter_var.get() if hasattr(self, "tag_filter_var") else "all"
            sort       = self.sort_var.get()        if hasattr(self, "sort_var")       else "Newest"
            use_headers = (tag_filter == "all" and sort in ("Newest", "Oldest"))

            if use_headers:
                gap = storage.load_settings().get("session_gap_minutes", 30)
                display = self._build_session_groups(clips, gap)
            else:
                display = clips

            self._display_items = display

            for item in display:
                if isinstance(item, dict) and item.get("type") == "session_header":
                    self.listbox.insert(tk.END, f"  {item['label']}")
                else:
                    clip    = item
                    text    = clip["text"]
                    preview = text if len(text) <= 52 else text[:52] + "…"
                    pin     = "📌 " if clip.get("pinned")    else "    "
                    tpl     = "⟨⟩ " if clip.get("template")  else ""
                    priv    = "👁 " if clip.get("incognito") else ""
                    tag     = f"[{clip['tag']}] " if clip.get("tag") else ""
                    hk      = f"⚡{clip['hotkey_slot']} " if clip.get("hotkey_slot") else ""
                    if clip.get("type") == "image":
                        self.listbox.insert(tk.END, f"{pin}{tpl}{priv}{hk}{tag}{_image_label(clip)}")
                    else:
                        self.listbox.insert(tk.END, f"{pin}{tpl}{priv}{hk}{tag}{preview}")

            for i, item in enumerate(display):
                if isinstance(item, dict) and item.get("type") == "session_header":
                    self.listbox.itemconfig(i, bg=HEADER_BG, fg=ACCENT,
                                            selectbackground=HEADER_BG, selectforeground=ACCENT)
                elif item.get("incognito"):
                    self.listbox.itemconfig(i, bg="#2A1A3E", fg="#C9A0FF")
                else:
                    bg    = PINNED_ROW if item.get("pinned") else WHITE
                    tag_v = item.get("tag")
                    fg    = get_tag_color(tag_v) if tag_v else TEXT_DARK
                    self.listbox.itemconfig(i, bg=bg, fg=fg)

            total = len(storage.load_clips())

        label = f"{total} clip{'s' if total != 1 else ''}"
        self.counter_label.config(text=label)

    # ── Clipboard Peek overlay ─────────────────────────────────────────────

    _PEEK_W   = 380   # fixed overlay width  (px)
    _PEEK_MAX = 650   # max overlay height   (px)

    def _peek_render_image_body(self, parent, clip):
        """Render an image thumbnail (or fallback text) into the peek body frame."""
        try:
            from PIL import Image, ImageTk
            path = clip.get("text", "").strip()
            img  = Image.open(path)
            img.thumbnail((340, 200))
            photo = ImageTk.PhotoImage(img)
            lbl   = tk.Label(parent, image=photo, bg=HEADER_BG, cursor="arrow")
            lbl.image = photo          # keep alive on the widget
            self._peek_img_ref = photo # keep alive on self
            lbl.pack(anchor="center", pady=4)
        except Exception:
            tk.Label(parent, text="🖼  Image not found",
                     font=("Segoe UI", 10), bg=HEADER_BG, fg=TEXT_DARK).pack(anchor="w")

    def _peek_show(self):
        """Show the compact floating peek overlay with the most recent clip."""
        if self._peek_window and self._peek_window.winfo_exists():
            return

        # Load all clips — pure chronological newest-to-oldest, pinned mixed in by date
        import pyperclip
        from datetime import datetime
        def _date_key(c):
            try:
                return datetime.strptime(c.get("date", ""), "%d %b %Y, %H:%M")
            except Exception:
                return datetime.min
        stored = sorted(storage.load_clips(), key=_date_key, reverse=True)
        if self._incognito:
            base_clips = list(self._incognito_clips) + stored
        else:
            base_clips = stored

        # Prepend OS clipboard only if it is genuinely different from the most recent clip.
        # Skip comparison against image clips (their "text" is a file path, not display text).
        try:
            current_os = (pyperclip.paste() or "").strip()
        except Exception:
            current_os = ""

        if base_clips and base_clips[0].get("type") != "image":
            most_recent_text = base_clips[0].get("text", "").strip()
        else:
            most_recent_text = ""

        if current_os and current_os != most_recent_text:
            self._peek_clips = [{"text": current_os, "type": "text"}] + base_clips
        else:
            self._peek_clips = base_clips

        if not self._peek_clips:
            return

        self._peek_idx  = 0
        c0 = self._peek_clips[0]
        self._peek_is_image  = c0.get("type") == "image"
        self._peek_full_text = ("📸  Screenshot  ·  " + c0.get("date","").replace(", ","  ·  ")) if self._peek_is_image else c0.get("text", "")

        # ── Build window ───────────────────────────────────────────────
        self._peek_window = tk.Toplevel(self.root)
        win = self._peek_window
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.0)
        win.geometry("+9999+9999")   # park off-screen while building; alpha=0 keeps it invisible

        outer = tk.Frame(win, bg=ACCENT, padx=1, pady=1)
        outer.pack(fill="both", expand=True)
        self._peek_inner = tk.Frame(outer, bg=HEADER_BG, padx=12, pady=10, cursor="hand2")
        self._peek_inner.pack(fill="both", expand=True)
        inner = self._peek_inner

        # Header (drag handle)
        hdr = tk.Frame(inner, bg=HEADER_BG, cursor="fleur")
        hdr.pack(fill="x", pady=(0, 6))
        hdr_title = tk.Label(hdr, text="CLIPBOARD PEEK",
                 font=("Segoe UI", 7, "bold"), bg=HEADER_BG, fg=ACCENT, cursor="fleur")
        hdr_title.pack(side="left")
        # Nav frame: ← counter →
        nav_frame = tk.Frame(hdr, bg=HEADER_BG)
        nav_frame.pack(side="left", padx=(6, 0))
        btn_prev = tk.Label(nav_frame, text="←", font=("Segoe UI", 7, "bold"),
                            bg=HEADER_BG, fg=TEXT_GRAY, cursor="hand2")
        btn_prev.pack(side="left")
        total = len(self._peek_clips)
        self._peek_counter_lbl = tk.Label(nav_frame,
                 text=f"1 / {total}" if total else "0 / 0",
                 font=("Segoe UI", 7), bg=HEADER_BG, fg=TEXT_GRAY)
        self._peek_counter_lbl.pack(side="left", padx=3)
        btn_next = tk.Label(nav_frame, text="→", font=("Segoe UI", 7, "bold"),
                            bg=HEADER_BG, fg=TEXT_GRAY, cursor="hand2")
        btn_next.pack(side="left")
        btn_prev.bind("<Button-1>", lambda e: self._peek_nav(-1) or "break")
        btn_next.bind("<Button-1>", lambda e: self._peek_nav(+1) or "break")
        self._peek_lock_lbl = tk.Label(hdr, text="click to lock",
                 font=("Segoe UI", 7), bg=HEADER_BG, fg=TEXT_GRAY)
        self._peek_lock_lbl.pack(side="right")
        self._peek_pin_lbl = tk.Label(hdr, text=" 📌 ",
                 font=("Segoe UI", 8, "bold"), bg=ACCENT, fg="white",
                 padx=2, pady=1)
        c0_pinned = self._peek_clips[0].get("pinned") if self._peek_clips else False
        if c0_pinned:
            self._peek_pin_lbl.pack(side="right", padx=(0, 4))
        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=(0, 8))

        # Body: expands to fill available space between header and footer
        self._peek_body = tk.Frame(inner, bg=HEADER_BG)
        self._peek_body.pack(fill="both", expand=True)

        if not self._peek_is_image:
            wrap_frame = tk.Frame(self._peek_body, bg=BORDER, padx=1, pady=1)
            wrap_frame.pack(fill="both", expand=True)

            self._peek_txt = tk.Text(
                wrap_frame, font=("Segoe UI", 10),
                bg=WHITE, fg=TEXT_DARK,
                relief="flat", bd=0, wrap="word",
                padx=8, pady=6, state="normal",
                highlightthickness=0, cursor="arrow",
                height=50)
            self._peek_txt.insert("1.0", self._peek_full_text)
            self._peek_txt.config(state="disabled")
            self._peek_txt.pack(fill="both", expand=True)
            self._peek_wrap_frame = wrap_frame
        else:
            self._peek_txt = None
            self._peek_wrap_frame = None
            self._peek_render_image_body(self._peek_body, c0)

        # Footer — left hint + right resize hint
        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=(8, 4))
        footer = tk.Frame(inner, bg=HEADER_BG)
        footer.pack(fill="x")
        self._peek_hint_lbl = tk.Label(footer,
                 text="← → to browse  ·  click to lock  ·  Esc to dismiss",
                 font=("Segoe UI", 7), bg=HEADER_BG, fg=TEXT_GRAY)
        self._peek_hint_lbl.pack(side="left")
        tk.Label(footer, text="drag title to move",
                 font=("Segoe UI", 7), bg=HEADER_BG, fg=TEXT_GRAY).pack(side="right")

        # Drag-to-move bindings on header (work even with WS_EX_NOACTIVATE)
        self._peek_drag_x    = 0
        self._peek_drag_y    = 0
        self._peek_is_moving = False   # True only during header-bar drag moves

        def _drag_start(e):
            self._peek_drag_x    = e.x_root - win.winfo_x()
            self._peek_drag_y    = e.y_root - win.winfo_y()
            self._peek_is_moving = True

        def _drag_stop(_):
            self._peek_is_moving = False

        def _drag_move(e):
            if not self._peek_is_moving:
                return
            nx = e.x_root - self._peek_drag_x
            ny = e.y_root - self._peek_drag_y
            win.geometry(f"+{nx}+{ny}")
            self._peek_last_x = nx
            self._peek_last_y = ny

        for drag_widget in (hdr, hdr_title):
            drag_widget.bind("<Button-1>",        _drag_start, add="+")
            drag_widget.bind("<B1-Motion>",        _drag_move,  add="+")
            drag_widget.bind("<ButtonRelease-1>",  _drag_stop,  add="+")

        win.bind("<Button-1>", lambda _: self._peek_click())

        # Resize grips — thin frames placed over window edges via place()
        _rstate = {}

        def _resize_press(e, side):
            _rstate.clear()
            _rstate['ox']   = e.x_root
            _rstate['oy']   = e.y_root
            _rstate['wx']   = win.winfo_x()
            _rstate['wy']   = win.winfo_y()
            _rstate['ww']   = win.winfo_width()
            _rstate['wh']   = win.winfo_height()
            _rstate['side'] = side
            return "break"

        def _resize_move(e):
            if not _rstate:
                return "break"
            dx   = e.x_root - _rstate['ox']
            dy   = e.y_root - _rstate['oy']
            side = _rstate['side']
            rx, ry = _rstate['wx'], _rstate['wy']
            rw, rh = _rstate['ww'], _rstate['wh']
            min_w, min_h = 220, 80
            if 'right' in side:
                rw = max(min_w, rw + dx)
            if 'left' in side:
                delta = min(dx, rw - min_w)
                rx += delta; rw -= delta
            if 'top' in side:
                delta = min(dy, rh - min_h)
                ry += delta; rh -= delta
            nx, ny, nw, nh = int(rx), int(ry), int(rw), int(rh)
            win.geometry(f"{nw}x{nh}+{nx}+{ny}")
            self._peek_last_w = nw;  self._peek_last_h = nh
            return "break"

        # Resize grips — same HEADER_BG colour so they're invisible against the dark padding
        gs = 5  # grip thickness in pixels
        grip_defs = [
            ("size_we",    "right",     dict(relx=1.0, rely=0.0, anchor="ne", width=gs,    relheight=1.0)),
            ("size_we",    "left",      dict(x=0,      rely=0.0, anchor="nw", width=gs,    relheight=1.0)),
            ("size_ns",    "top",       dict(x=0,      y=0,      relwidth=1.0, height=gs)),
            ("size_ne_sw", "top-right", dict(relx=1.0, y=0,      anchor="ne", width=gs*2, height=gs*2)),
            ("size_nw_se", "top-left",  dict(x=0,      y=0,      width=gs*2,  height=gs*2)),
        ]
        for cur, side, place_kw in grip_defs:
            g = tk.Frame(win, bg=HEADER_BG, cursor=cur)
            g.place(**place_kw)
            g.bind("<Button-1>",  lambda e, s=side: _resize_press(e, s))
            g.bind("<B1-Motion>", lambda e: _resize_move(e))
            g.lift()

        self._peek_position_and_show(win)

    def _peek_size_text_widget(self, txt, win):
        """Measure display lines and resize txt to fit content up to _PEEK_MAX."""
        win.update_idletasks()
        try:
            n_display = int(txt.count("1.0", "end", "displaylines")[0])
        except Exception:
            n_display = len(txt.get("1.0", "end").splitlines()) + 2
        max_lines = max(5, (self._PEEK_MAX - 110) // 20)
        txt.config(height=min(n_display, max_lines))
        return n_display, max_lines

    def _peek_nav(self, direction):
        """Navigate the peek overlay by direction (+1 = older, -1 = newer)."""
        if not self._peek_clips:
            return
        self._peek_idx = (self._peek_idx + direction) % len(self._peek_clips)
        clip = self._peek_clips[self._peek_idx]
        self._peek_is_image  = clip.get("type") == "image"
        self._peek_full_text = ("📸  Screenshot  ·  " + clip.get("date","").replace(", ","  ·  ")) if self._peek_is_image else clip.get("text", "")

        # Rebuild body content when navigating
        if getattr(self, "_peek_body", None):
            try:
                for w in self._peek_body.winfo_children():
                    w.destroy()
                self._peek_txt        = None
                self._peek_wrap_frame = None
                if self._peek_is_image:
                    if self._peek_locked:
                        self._peek_build_image_canvas(self._peek_body, clip)
                    else:
                        self._peek_render_image_body(self._peek_body, clip)
                else:
                    wrap_frame = tk.Frame(self._peek_body, bg=BORDER, padx=1, pady=1)
                    wrap_frame.pack(fill="both", expand=True)
                    self._peek_txt = tk.Text(
                        wrap_frame, font=("Segoe UI", 10),
                        bg=WHITE, fg=TEXT_DARK,
                        relief="flat", bd=0, wrap="word",
                        padx=8, pady=6, state="normal",
                        highlightthickness=0, cursor="ibeam", height=50)
                    self._peek_txt.insert("1.0", self._peek_full_text)
                    self._peek_txt.config(state="disabled")
                    self._peek_txt.pack(fill="both", expand=True)
                    self._peek_wrap_frame = wrap_frame
            except Exception:
                pass

        # Update counter label
        if self._peek_counter_lbl:
            try:
                total = len(self._peek_clips)
                self._peek_counter_lbl.config(
                    text=f"{self._peek_idx + 1} / {total}", fg=TEXT_GRAY)
            except Exception:
                pass

        # Update pin indicator
        if getattr(self, "_peek_pin_lbl", None):
            try:
                if clip.get("pinned"):
                    self._peek_pin_lbl.pack(side="right", padx=(0, 4))
                else:
                    self._peek_pin_lbl.pack_forget()
            except Exception:
                pass

        # Resize window to fit new content (only in unlocked quick-peek mode)
        if not self._peek_locked:
            win = self._peek_window
            if win and win.winfo_exists():
                try:
                    if self._peek_is_image:
                        win.update_idletasks()
                        oh = min(win.winfo_reqheight(), self._PEEK_MAX)
                    else:
                        if getattr(self, "_peek_txt", None):
                            self._peek_size_text_widget(self._peek_txt, win)
                        win.update_idletasks()
                        oh = min(win.winfo_reqheight(), self._PEEK_MAX)
                    sh = self.root.winfo_screenheight()
                    cx = win.winfo_x()
                    cy = min(win.winfo_y(), sh - oh - 48)
                    win.geometry(f"{self._PEEK_W}x{oh}+{cx}+{cy}")
                except Exception:
                    pass

    def _peek_position_and_show(self, win):
        """Calculate geometry, apply WS_EX_NOACTIVATE, fade in."""
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()

        if self._peek_last_w is not None and self._peek_last_h is not None:
            # Use the saved size exactly — text widget will fill via expand=True
            ow = self._peek_last_w
            oh = self._peek_last_h
        else:
            # No saved size — compute from content
            if getattr(self, "_peek_txt", None):
                self._peek_size_text_widget(self._peek_txt, win)
            win.update_idletasks()
            ow = self._PEEK_W
            oh = min(win.winfo_reqheight(), self._PEEK_MAX)

        if self._peek_last_x is not None and self._peek_last_y is not None:
            x = self._peek_last_x
            y = self._peek_last_y
        else:
            x = sw - ow - 24
            y = sh - oh - 64
        # Always clamp so the window never falls off the bottom of the screen
        y = min(y, sh - oh - 48)
        win.geometry(f"{ow}x{oh}+{x}+{y}")

        # Prevent focus theft on show and on click
        try:
            import ctypes
            GWL_EXSTYLE      = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TOOLWINDOW = 0x00000080
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
            cur  = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, cur | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
        except Exception:
            pass

        def _fade(a=0.0):
            if not (self._peek_window and self._peek_window.winfo_exists()):
                return
            a = min(a + 0.15, 0.96)
            win.attributes("-alpha", a)
            if a < 0.96:
                win.after(16, lambda: _fade(a))
        _fade()

    def _peek_build_image_canvas(self, parent, clip):
        """Build the zoom/pan canvas viewer for an image clip inside `parent`."""
        try:
            from PIL import Image, ImageTk
            path = clip.get("text", "").strip()
            orig = Image.open(path)

            canvas_w = self._PEEK_W - 24
            canvas_h = self._PEEK_MAX - 120

            canvas = tk.Canvas(parent, bg="#1A1A2E",
                               width=canvas_w, height=canvas_h,
                               highlightthickness=0, cursor="fleur")
            canvas.pack(fill="both", expand=True)

            work = orig.copy()
            work.thumbnail((canvas_w, canvas_h), Image.LANCZOS)
            work_scale = work.width / orig.width

            _state = {"zoom": 1.0, "pan_x": 0, "pan_y": 0,
                      "drag_x": 0, "drag_y": 0,
                      "item": None, "settle_id": None,
                      "cw": canvas_w, "ch": canvas_h}

            def _place():
                if _state["item"] is None:
                    return
                canvas.coords(_state["item"],
                              _state["cw"] // 2 + _state["pan_x"],
                              _state["ch"] // 2 + _state["pan_y"])

            def _render_work():
                rel   = _state["zoom"] / work_scale
                w     = max(1, int(work.width  * rel))
                h     = max(1, int(work.height * rel))
                photo = ImageTk.PhotoImage(work.resize((w, h), Image.NEAREST))
                if _state["item"] is None:
                    _state["item"] = canvas.create_image(
                        _state["cw"] // 2, _state["ch"] // 2,
                        anchor="center", image=photo)
                else:
                    canvas.itemconfig(_state["item"], image=photo)
                    _place()
                canvas._photo = photo
                self._peek_img_ref = photo

            def _render_hq():
                w     = max(1, int(orig.width  * _state["zoom"]))
                h     = max(1, int(orig.height * _state["zoom"]))
                photo = ImageTk.PhotoImage(orig.resize((w, h), Image.LANCZOS))
                if _state["item"] is None:
                    _state["item"] = canvas.create_image(
                        _state["cw"] // 2, _state["ch"] // 2,
                        anchor="center", image=photo)
                else:
                    canvas.itemconfig(_state["item"], image=photo)
                    _place()
                canvas._photo = photo
                self._peek_img_ref = photo

            def _on_wheel(e):
                factor   = 1.1 if e.delta > 0 else 0.9
                fit      = _state.get("fit_zoom", 0.01)
                new_zoom = _state["zoom"] * factor
                max_zoom = max(3.0, fit)
                if new_zoom <= fit:
                    # Snap to original fit — works for any image size
                    _state["zoom"]  = fit
                    _state["pan_x"] = 0
                    _state["pan_y"] = 0
                else:
                    _state["zoom"] = min(max_zoom, new_zoom)
                _render_work()
                if _state["settle_id"]:
                    canvas.after_cancel(_state["settle_id"])
                _state["settle_id"] = canvas.after(220, _render_hq)

            def _drag_start(e):
                _state["drag_x"] = e.x
                _state["drag_y"] = e.y

            def _drag_move(e):
                _state["pan_x"] += e.x - _state["drag_x"]
                _state["pan_y"] += e.y - _state["drag_y"]
                _state["drag_x"] = e.x
                _state["drag_y"] = e.y
                _place()

            canvas.bind("<MouseWheel>", _on_wheel)
            canvas.bind("<Button-1>",   _drag_start)
            canvas.bind("<B1-Motion>",  _drag_move)

            def _init_render():
                cw = canvas.winfo_width()
                ch = canvas.winfo_height()
                _state["cw"] = cw if cw > 1 else canvas_w
                _state["ch"] = ch if ch > 1 else canvas_h
                # Fit image fully inside canvas — no 1.0 cap so small images scale up to fill
                scale_x = _state["cw"] / orig.width
                scale_y = _state["ch"] / orig.height
                fit_zoom = min(scale_x, scale_y)
                _state["zoom"]     = fit_zoom
                _state["fit_zoom"] = fit_zoom
                _render_hq()

            canvas.after(10, _init_render)

        except Exception:
            tk.Label(parent, text="🖼  Image not found",
                     font=("Segoe UI", 10), bg=HEADER_BG, fg=TEXT_DARK).pack(anchor="w")

    def _peek_expand_to_full(self):
        """Replace the compact body with a scrollable Text widget (locked state)."""
        win = self._peek_window
        if not (win and win.winfo_exists()):
            return

        # Clear compact body
        for w in self._peek_body.winfo_children():
            w.destroy()

        text = self._peek_full_text

        if self._peek_is_image:
            clip = self._peek_clips[self._peek_idx] if self._peek_clips else {}
            self._peek_build_image_canvas(self._peek_body, clip)
        else:
            wrap_frame = tk.Frame(self._peek_body, bg=BORDER, padx=1, pady=1)
            wrap_frame.pack(fill="both", expand=True)

            # Start with a large height so all content is rendered and measurable
            txt = tk.Text(wrap_frame, font=("Segoe UI", 10),
                          bg=WHITE, fg=TEXT_DARK,
                          relief="flat", bd=0, wrap="word",
                          padx=8, pady=6, state="normal",
                          highlightthickness=0, cursor="ibeam",
                          height=50)
            txt.insert("1.0", text)

            # Measure actual display lines (accounts for word-wrap at current width)
            win.update_idletasks()
            try:
                n_display = int(txt.count("1.0", "end", "displaylines")[0])
            except Exception:
                n_display = len(text.splitlines()) + 2

            # How many lines fit before we hit _PEEK_MAX?
            # Header + footer ≈ 110px; each line ≈ 20px
            max_lines = max(5, (self._PEEK_MAX - 110) // 20)
            needs_scroll = n_display > max_lines
            txt.config(height=min(n_display, max_lines))

            # Pack scrollbar BEFORE text so it gets space on the right
            sb = tk.Scrollbar(wrap_frame, width=12)
            if needs_scroll:
                sb.pack(side="right", fill="y")
                txt.config(yscrollcommand=sb.set)
                sb.config(command=txt.yview)
                txt.bind("<MouseWheel>",
                         lambda e: txt.yview_scroll(int(-1 * (e.delta / 120)), "units"))
            txt.pack(side="left", fill="both", expand=True)
            self._peek_txt = txt  # keep reference current so _peek_nav can update it

            txt.bind("<Key>", lambda _: "break")

            # Auto-copy on mouse-release (Ctrl+C can't reach non-active window)
            self._peek_copied_lbl = tk.Label(
                self._peek_body, text="",
                font=("Segoe UI", 7), bg=HEADER_BG, fg="#27AE60")
            self._peek_copied_lbl.pack(anchor="e", pady=(2, 0))

            def _on_mouse_release(_=None):
                try:
                    selected = txt.get(tk.SEL_FIRST, tk.SEL_LAST)
                except tk.TclError:
                    return
                if selected:
                    import pyperclip
                    pyperclip.copy(selected)
                    self._peek_copied_lbl.config(text="✔ copied")
                    self._peek_copied_lbl.after(
                        1500, lambda: self._peek_copied_lbl.config(text="")
                        if self._peek_copied_lbl.winfo_exists() else None)

            txt.bind("<ButtonRelease-1>", _on_mouse_release)

        # Update labels
        self._peek_lock_lbl.config(text="🔒 locked")
        self._peek_hint_lbl.config(text="Esc to dismiss")

        # Resize window: measure actual required height after layout is settled
        win.update_idletasks()
        oh = self._PEEK_MAX if self._peek_is_image else min(win.winfo_reqheight(), self._PEEK_MAX)
        cx = win.winfo_x()
        cy = win.winfo_y()
        # Clamp Y so the expanded window never falls off the bottom of the screen
        sh = self.root.winfo_screenheight()
        cy = min(cy, sh - oh - 48)
        win.geometry(f"{self._PEEK_W}x{oh}+{cx}+{cy}")

    def _peek_hide(self):
        """Fade and dismiss unless locked."""
        if self._peek_locked:
            return
        self._peek_dismiss()

    def _peek_click(self):
        """Click locks the overlay and expands to full view. Only Esc dismisses."""
        if not self._peek_locked:
            self._peek_locked = True
            shortcut.set_peek_locked(True)
            self._peek_expand_to_full()

    def _peek_dismiss(self):
        """Destroy the overlay regardless of lock state."""
        self._peek_locked = False
        shortcut.set_peek_locked(False)
        self._peek_clips       = []
        self._peek_idx         = 0
        # Release all widget references so destroyed Tk objects don't keep
        # their event-binding tables and callback registrations alive across cycles.
        self._peek_counter_lbl = None
        self._peek_lock_lbl    = None
        self._peek_hint_lbl    = None
        self._peek_txt         = None
        self._peek_wrap_frame  = None
        self._peek_body        = None
        self._peek_copied_lbl  = None
        self._peek_pin_lbl     = None
        if self._peek_window:
            try:
                # Position is saved live during header drag only (_drag_move).
                # Just reset size so next open auto-sizes to content.
                self._peek_last_w = None
                self._peek_last_h = None
                self._peek_window.destroy()
            except Exception:
                pass
            self._peek_window = None

    def run(self):
        self.root.mainloop()
