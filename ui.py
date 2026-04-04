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
        "\n    ",      # indented lines (Python style)
        "\n\t",        # tab indented
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
    return any(hint in text for hint in code_hints)

def _hover(btn, normal_bg, hover_bg, normal_fg=TEXT_DARK, hover_fg=TEXT_DARK):
    btn.bind("<Enter>", lambda _e: btn.config(bg=hover_bg, fg=hover_fg))
    btn.bind("<Leave>", lambda _e: btn.config(bg=normal_bg, fg=normal_fg))


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
            ("Ctrl+C",         "Capture to clipboard"),
            ("Ctrl+Alt+C",     "Capture & pin"),
            ("Ctrl+Shift+V",   "Open quick-paste launcher"),
            ("Ctrl+Shift+E",   "Toggle capture on / off"),
            ("Ctrl+Shift+X",   "Toggle private mode"),
        ]),
        ("List",  [
            ("C",  "Copy selected"),
            ("P",  "Pin / unpin"),
            ("T",  "Tag selected"),
            ("M",  "Mark / unmark template"),
            ("E",  "Edit selected"),
            ("Del","Delete selected"),
            ("↑ ↓","Navigate"),
            ("↵",  "Copy & close"),
        ]),
        ("Launcher",  [
            ("#tag",   "Filter by tag"),
            ("↑ ↓",    "Navigate"),
            ("↵",      "Paste into app"),
            ("Esc",    "Dismiss"),
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
        self.root.title("Smart Clipboard ")
        self.root.geometry("820x520")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)

        import os, sys
        _base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        ico = os.path.join(_base, "SmartClipboard_1.ico")
        if not os.path.exists(ico):
            ico = "SmartClipboard_1.ico"

        def _apply_icon():
            try:
                self.root.iconbitmap(default=ico)
                self.root.iconbitmap(ico)
            except Exception:
                pass

        _apply_icon()
        self.root.after(0, _apply_icon)

        self._incognito       = False
        self._incognito_clips = []
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._hide_window)
        self.tray_icon = tray.start_tray(
            show_callback=self._show_window,
            quit_callback=self.root.quit
        )
        tray.set_tray_title(self.tray_icon, self._active)
        from launcher import QuickPasteLauncher
        self._launcher = QuickPasteLauncher(self.root)
        shortcut.start_listener(
            self._on_clipboard_change,
            self._on_pin_shortcut,
            launcher_callback=lambda hwnd: self.root.after(0, lambda: self._launcher.open(hwnd)) if storage.load_settings().get("global_shortcuts", True) else None,
            toggle_callback=lambda: self.root.after(0, self._toggle_active) if storage.load_settings().get("global_shortcuts", True) else None,
            incognito_callback=lambda: self.root.after(0, self._toggle_incognito) if storage.load_settings().get("global_shortcuts", True) else None,
        )
        self._add_to_startup()
        if not storage.load_settings().get("onboarding_complete"):
            from onboarding import Onboarding
            Onboarding(self).start()

        if startup:
            self.root.withdraw()

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
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.listbox.focus_set()
        import os, sys
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
        search_entry = tk.Entry(search_wrap, textvariable=self.search_var, width=34,
                                font=("Segoe UI", 10), relief="flat", bd=0,
                                bg=WHITE, fg=TEXT_DARK, insertbackground=TEXT_DARK)
        search_entry.pack()
        search_entry.bind("<FocusIn>",
                          lambda _: search_wrap.config(highlightbackground=ACCENT))
        search_entry.bind("<FocusOut>",
                          lambda _: search_wrap.config(highlightbackground=BORDER))

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
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        self.listbox.bind("<Delete>", lambda e: self._delete_selected())
        # Keyboard shortcuts active when listbox has focus
        self.listbox.bind("<Up>",     lambda _e: self._kb_nav(-1) or "break")
        self.listbox.bind("<Down>",   lambda _e: self._kb_nav(+1) or "break")
        self.listbox.bind("<c>",      lambda _e: self._copy_selected())
        self.listbox.bind("<p>",      lambda _e: self._toggle_pin())
        self.listbox.bind("<t>",      lambda _e: self._show_tag_menu())
        self.listbox.bind("<m>",      lambda _e: self._toggle_template())
        self.listbox.bind("<e>",      lambda _e: self._edit_selected())
        self.listbox.bind("<Return>", lambda _e: self._copy_and_close())

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
        self.preview_meta.pack(side="right")

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
        Tooltip(copy_btn, "Copy selected clip  (double-click for instant copy)")

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
        if not self._active:
            return
        from PIL import Image
        if self._incognito:
            if not isinstance(content, Image.Image):
                if len(content) >= 3:
                    text = content if _looks_like_code(content) else " ".join(content.split())
                    if not any(c["text"] == text for c in self._incognito_clips):
                        self._incognito_clips.insert(0, {"text": text, "type": "text", "incognito": True})
                    self._refresh_list()
            return
        if isinstance(content, Image.Image):
            path = storage.save_image(content)
            storage.save_clip(path, clip_type="image")
            self._refresh_list()
            self._show_toast("Image saved 🖼")
        else:
            if len(content) < 3:
                return
            if _looks_like_sensitive(content):
                self._show_toast("Sensitive content skipped 🔒")
                return
            if _is_excluded_app():
                return
            # Detect code — preserve formatting, otherwise normalize
            if _looks_like_code(content):
                text = content
            else:
                text = " ".join(content.split())
            storage.save_clip(text, clip_type="text")
            self._refresh_list()
        if self.root.state() == "withdrawn":
            self.root.iconify()

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
                storage.save_clip(path, clip_type="image")
                storage.toggle_pin(path)
                self._show_toast("📌 Image Saved & Pinned!")
            self._refresh_list()
            if self.root.state() == "withdrawn":
                self.root.iconify()
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
        if self.root.state() == "withdrawn":
            self.root.iconify()

    # ── Toast ──────────────────────────────────────────────────────────────

    def _show_toast(self, message):
        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes("-alpha", 0.0)
        toast.attributes("-topmost", True)

        outer = tk.Frame(toast, bg=ACCENT, padx=1, pady=1)
        outer.pack()
        tk.Label(outer, text=message, bg=HEADER_BG, fg=TEXT_DARK,
                 font=("Segoe UI", 10), padx=14, pady=8).pack()

        self.root.update_idletasks()
        x = self.root.winfo_x() + self.root.winfo_width() - 240
        y = self.root.winfo_y() + self.root.winfo_height() - 64
        toast.geometry(f"+{x}+{y}")

        def fade(a=0.0):
            a = min(a + 0.12, 0.95)
            toast.attributes("-alpha", a)
            if a < 0.95:
                toast.after(18, lambda: fade(a))

        fade()
        toast.after(1800, toast.destroy)

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
        idx = max(0, min(n - 1, (sel[0] if sel else -1) + direction))
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(idx)
        self.listbox.see(idx)
        self.listbox.focus_set()
        self.listbox.event_generate("<<ListboxSelect>>")

    def _copy_and_close(self):
        """Copy the selected clip then hide the window — keeps you in your workflow."""
        self._copy_selected()
        self._hide_window()

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
            clipboard.set_clipboard_image(clip["text"].strip())
            self._show_toast("Image copied 🖼")
        else:
            clipboard.set_clipboard(clip["text"].strip())
            self._show_toast("Copied ✅")

    def _copy_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        self._copy_clip(self._get_current_clips()[sel[0]])

    def _double_click_copy(self, _event):
        sel = self.listbox.curselection()
        if not sel:
            return
        self._copy_clip(self._get_current_clips()[sel[0]])

    def _on_select(self, event):
        sel = self.listbox.curselection()
        if not sel:
            return
        clips = self._get_current_clips()
        clip  = clips[sel[0]]

        date      = clip.get("date", "Unknown") if isinstance(clip, dict) else "Unknown"
        text      = clip.get("text", "")        if isinstance(clip, dict) else clip
        tag       = clip.get("tag")
        clip_type = clip.get("type", "text")

        # Update preview meta strip
        parts = [f"📅 {date}"]
        if tag:
            parts.append(f"🏷 {tag}")
        self.preview_meta.config(text="  •  ".join(parts))

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
        clips = self._get_current_clips()
        for i in reversed(sel):
            storage.delete_clip(clips[i]["text"])
        self._refresh_list()

    def _edit_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            self._show_toast("Select a clip first!")
            return
        clip = self._get_current_clips()[sel[0]]
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
        clips = self._get_current_clips()
        storage.toggle_pin(clips[sel[0]]["text"])
        self._refresh_list()

    def _toggle_template(self):
        sel = self.listbox.curselection()
        if not sel:
            self._show_toast("Select a clip first!")
            return
        clips = self._get_current_clips()
        clip  = clips[sel[0]]
        storage.toggle_template(clip["text"])
        is_now = not clip.get("template", False)
        self._show_toast("Marked as template ⟨⟩" if is_now else "Template removed")
        self._refresh_list()

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
        tk.Label(popup, text=preview, font=("Segoe UI", 9), bg=BG, fg=TEXT_GRAY,
                 wraplength=360, justify="left", padx=16, pady=8).pack(fill="x")

        tk.Frame(popup, bg=BORDER, height=1).pack(fill="x", padx=16)

        # One entry per placeholder
        entries = {}
        today   = __import__("datetime").date.today().strftime("%d %b %Y")
        form    = tk.Frame(popup, bg=BG, padx=16, pady=10)
        form.pack(fill="x")

        for ph in placeholders:
            row = tk.Frame(form, bg=BG)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=f"{{{ph}}}", font=("Segoe UI", 9, "bold"),
                     bg=BG, fg=ACCENT, width=14, anchor="w").pack(side="left")
            wrap = tk.Frame(row, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
            wrap.pack(side="left", fill="x", expand=True)
            var = tk.StringVar(value=today if ph == "date" else "")
            ent = tk.Entry(wrap, textvariable=var, font=("Segoe UI", 10),
                           bg=WHITE, fg=TEXT_DARK, relief="flat", bd=0,
                           insertbackground=ACCENT, width=28)
            ent.pack(padx=8, pady=5)
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
            clipboard.set_clipboard(result)
            self._show_toast("Template copied ✅")
            popup.destroy()

        btn_row = tk.Frame(popup, bg=BG, padx=16, pady=12)
        btn_row.pack(fill="x")
        popup.bind("<Return>", lambda _e: do_copy())
        tk.Button(btn_row, text="Copy to Clipboard", bg=ACCENT, fg="white",
                  font=("Segoe UI", 10, "bold"), relief="flat", padx=18, pady=7,
                  cursor="hand2", bd=0, command=do_copy).pack(side="right")
        tk.Button(btn_row, text="Cancel", bg=WHITE, fg=TEXT_DARK,
                  font=("Segoe UI", 10), relief="flat", padx=14, pady=7,
                  cursor="hand2", bd=0, command=popup.destroy).pack(side="right", padx=(0, 8))

        # Size & center over main window
        popup.update_idletasks()
        pw = 540
        ph_h = popup.winfo_reqheight()
        x = self.root.winfo_x() + (self.root.winfo_width()  - pw)  // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - ph_h) // 2
        popup.geometry(f"{pw}x{ph_h}+{x}+{y}")

    def _settings_popup(self):
        s = storage.load_settings()
        popup = tk.Toplevel(self.root)
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
            "1 week":   168,
            "2 weeks":  336,
            "30 days":  720,
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

        tk.Frame(form, bg=BORDER, height=1).pack(fill="x", pady=(12, 0))

        # ── Auto-start toggle ─────────────────────────────────────────────
        tk.Label(form, text="Launch at startup", font=("Segoe UI", 9, "bold"),
                 bg=BG, fg=TEXT_DARK).pack(anchor="w", pady=(14, 2))
        tk.Label(form, text="Automatically start Smart Clipboard when Windows starts.",
                 font=("Segoe UI", 8), bg=BG, fg=TEXT_GRAY).pack(anchor="w", pady=(0, 6))

        auto_start_var = tk.BooleanVar(value=s.get("auto_start", True))
        auto_row = tk.Frame(form, bg=BG)
        auto_row.pack(anchor="w")
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

        tk.Frame(form, bg=BORDER, height=1).pack(fill="x", pady=(12, 0))

        # ── Global shortcuts toggle ───────────────────────────────────────
        tk.Label(form, text="Enable global shortcuts", font=("Segoe UI", 9, "bold"),
                 bg=BG, fg=TEXT_DARK).pack(anchor="w", pady=(14, 2))
        tk.Label(form, text="Disable if keyboard shortcuts conflict with other apps.\nChanges take effect on next launch.",
                 font=("Segoe UI", 8), bg=BG, fg=TEXT_GRAY, justify="left").pack(anchor="w", pady=(0, 6))

        gs_var = tk.BooleanVar(value=s.get("global_shortcuts", True))
        gs_row = tk.Frame(form, bg=BG)
        gs_row.pack(anchor="w")
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

        # ── Popup close / save actions ────────────────────────────────────
        def _on_popup_close():
            self.root.bind("<Up>",     lambda _e: self._kb_nav(-1))
            self.root.bind("<Down>",   lambda _e: self._kb_nav(+1))
            self.root.bind("<Escape>", lambda _e: self._hide_window())
            popup.destroy()

        def save():
            mc = None if clip_var.get() == "Unlimited" else int(clip_var.get())
            mh = EXPIRY_OPTIONS[expiry_var.get()]
            apps = [a.strip() for a in excluded_entry.get().split(",") if len(a.strip()) >= 5]
            storage.save_settings({"max_clips": mc, "max_hours": mh,
                                   "excluded_apps": apps,
                                   "auto_start": auto_start_var.get(),
                                   "global_shortcuts": gs_var.get()})
            self._add_to_startup()
            self._refresh_list()
            self._show_toast("Settings saved ✅")
            _on_popup_close()

        # ── Action buttons (created before nav so they join the grid) ────
        tk.Frame(popup, bg=BORDER, height=1).pack(fill="x", padx=20, pady=(12, 0))
        btn_row = tk.Frame(popup, bg=BG, padx=20, pady=12)
        btn_row.pack(fill="x")

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

        export_btn = tk.Button(btn_row, text="⬆  Export clips",
                               bg=WHITE, fg=TEXT_GRAY,
                               font=("Segoe UI", 9), relief="flat", padx=12, pady=7,
                               cursor="hand2", bd=0, command=_export_clips)
        export_btn.pack(side="left", padx=(8, 0))

        save_btn = tk.Button(btn_row, text="Save", bg=ACCENT, fg="white",
                             font=("Segoe UI", 10, "bold"), relief="flat", padx=14, pady=7,
                             cursor="hand2", bd=0, command=save)
        save_btn.pack(side="right")
        cancel_btn = tk.Button(btn_row, text="Cancel", bg=WHITE, fg=TEXT_DARK,
                               font=("Segoe UI", 10, "bold"), relief="flat", padx=14, pady=7,
                               cursor="hand2", bd=0, command=_on_popup_close)
        cancel_btn.pack(side="right", padx=(18, 7))


        # ── Keyboard navigation ───────────────────────────────────────────
        # Rows: clip options, expiry options, then [Cancel, Save] action row
        action_btns = [("Cancel", cancel_btn), ("Save", save_btn)]
        all_rows  = [clip_btns, expiry_btns, action_btns]
        row_of    = {}   # btn → row index
        idx_of    = {}   # btn → index within its row
        for ri, row in enumerate(all_rows):
            for ci, (_, b) in enumerate(row):
                row_of[b] = ri
                idx_of[b] = ci

        def _focus_btn(b):
            b.focus_set()
            ri  = row_of[b]
            ci  = idx_of[b]
            row = all_rows[ri]
            for i, (_, rb) in enumerate(row):
                rb.config(
                    highlightthickness=2 if i == ci else 0,
                    highlightbackground=KB_CURSOR,
                )

        def _on_btn_key(event, btn):
            key = event.keysym
            ri  = row_of[btn]
            ci  = idx_of[btn]

            if key == "Left":
                new_ci = (ci - 1) % len(all_rows[ri])
                _focus_btn(all_rows[ri][new_ci][1])
                return "break"
            if key == "Right":
                new_ci = (ci + 1) % len(all_rows[ri])
                _focus_btn(all_rows[ri][new_ci][1])
                return "break"
            if key == "Up":
                new_ri = (ri - 1) % len(all_rows)
                new_ci = min(ci, len(all_rows[new_ri]) - 1)
                _focus_btn(all_rows[new_ri][new_ci][1])
                return "break"
            if key == "Down":
                new_ri = (ri + 1) % len(all_rows)
                new_ci = min(ci, len(all_rows[new_ri]) - 1)
                _focus_btn(all_rows[new_ri][new_ci][1])
                return "break"
            if key in ("Return", "space"):
                btn.invoke()
                return "break"

        all_btns_flat = [b for row in all_rows for _, b in row]
        for _, b in [(c, btn) for row in all_rows for (c, btn) in row]:
            b.config(takefocus=1)
            b.bind("<Left>",   lambda e, btn=b: _on_btn_key(e, btn))
            b.bind("<Right>",  lambda e, btn=b: _on_btn_key(e, btn))
            b.bind("<Up>",     lambda e, btn=b: _on_btn_key(e, btn))
            b.bind("<Down>",   lambda e, btn=b: _on_btn_key(e, btn))
            b.bind("<Return>", lambda e, btn=b: _on_btn_key(e, btn))
            b.bind("<space>",  lambda e, btn=b: _on_btn_key(e, btn))

        # Disable main window keys while popup is open
        self.root.unbind("<Up>")
        self.root.unbind("<Down>")
        self.root.unbind("<Escape>")

        popup.protocol("WM_DELETE_WINDOW", _on_popup_close)
        popup.bind("<Escape>", lambda _e: _on_popup_close())
        popup.bind("<Return>", lambda _e: save())

        def _route_key(e):
            focused = popup.focus_get()
            if focused and focused in all_btns_flat:
                _on_btn_key(e, focused)
            return "break"

        popup.bind("<Left>",  _route_key)
        popup.bind("<Right>", _route_key)
        popup.bind("<Up>",    _route_key)
        popup.bind("<Down>",  _route_key)

        # Size and center
        popup.update_idletasks()
        pw = 420
        ph = popup.winfo_reqheight()
        x = self.root.winfo_x() + (self.root.winfo_width()  - pw) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - ph) // 2
        popup.geometry(f"{pw}x{ph}+{x}+{y}")

        popup.grab_set()
        popup.lift()
        popup.focus_force()

        # Focus correct button after window is visible
        first_focus_idx = CLIP_OPTIONS.index(_current_clip_label(s.get("max_clips")))
        popup.after(50, lambda: _focus_btn(clip_btns[first_focus_idx][1]))

        
    def _set_tag(self, tag):
        sel = self.listbox.curselection()
        if not sel:
            self._show_toast("Select a clip first!")
            return
        clips = self._get_current_clips()
        for i in sel:
            if i < len(clips):
                storage.set_tag(clips[i]["text"], tag if tag else "none")
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
                incognito = [c for c in incognito if q in c["text"].lower()]
            return incognito + base
        if tag_filter != "all":
            return storage.filter_by_tag(tag_filter)
        return incognito + self._sorted_clips()

    def _sorted_clips(self):
        clips = storage.load_clips()
        sort  = self.sort_var.get() if hasattr(self, "sort_var") else "Newest"
        if   sort == "Newest": sc = clips
        elif sort == "Oldest": sc = list(reversed(clips))
        elif sort == "A-Z":    sc = sorted(clips, key=lambda c: c["text"].lower())
        elif sort == "Z-A":    sc = sorted(clips, key=lambda c: c["text"].lower(), reverse=True)
        else:                  sc = clips
        return [c for c in sc if c.get("pinned")] + [c for c in sc if not c.get("pinned")]

    def _refresh_list(self):
        clips = self._get_current_clips()
        self.listbox.delete(0, tk.END)

        if not clips:
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
            for clip in clips:
                text    = clip["text"]
                preview = text if len(text) <= 52 else text[:52] + "…"
                pin     = "📌 " if clip.get("pinned")    else "    "
                tpl     = "⟨⟩ " if clip.get("template")  else ""
                priv    = "👁 " if clip.get("incognito") else ""
                tag     = f"[{clip['tag']}] " if clip.get("tag") else ""
                if clip.get("type") == "image":
                    self.listbox.insert(tk.END, f"{pin}{tpl}{priv}{tag}🖼  Image")
                else:
                    self.listbox.insert(tk.END, f"{pin}{tpl}{priv}{tag}{preview}")

            for i, clip in enumerate(clips):
                if clip.get("incognito"):
                    self.listbox.itemconfig(i, bg="#2A1A3E", fg="#C9A0FF")
                else:
                    bg    = PINNED_ROW if clip.get("pinned") else WHITE
                    tag_v = clip.get("tag")
                    fg    = get_tag_color(tag_v) if tag_v else TEXT_DARK
                    self.listbox.itemconfig(i, bg=bg, fg=fg)

            total = len(storage.load_clips())

        label = f"{total} clip{'s' if total != 1 else ''}"
        self.counter_label.config(text=label)

    def run(self):
        self.root.mainloop()
