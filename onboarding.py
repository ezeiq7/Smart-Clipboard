# onboarding.py
import tkinter as tk
import random
import storage

HEADER_BG = "#252537"
WHITE     = "#2A2A3D"
ACCENT    = "#5B5FEF"
TEXT_DARK = "#E0E0F0"
TEXT_GRAY = "#7070A0"
BORDER    = "#3A3A5C"
BTN_BG    = "#32324A"
BTN_HOVER = "#3D3D5C"


def _ease_out_cubic(t):
    return 1 - (1 - t) ** 3


def _hex_lerp(c1, c2, t):
    c1 = c1.lstrip("#"); c2 = c2.lstrip("#")
    r1,g1,b1 = int(c1[0:2],16), int(c1[2:4],16), int(c1[4:6],16)
    r2,g2,b2 = int(c2[0:2],16), int(c2[2:4],16), int(c2[4:6],16)
    r = int(r1 + (r2-r1)*t); g = int(g1 + (g2-g1)*t); b = int(b1 + (b2-b1)*t)
    return f"#{r:02x}{g:02x}{b:02x}"


class Onboarding:
    def __init__(self, app):
        self.app     = app
        self.root    = app.root
        self.overlay = None
        self.card    = None
        self._after_ids = []

    # ── Infrastructure ────────────────────────────────────────────────────

    def start(self):
        self.root.unbind("<Escape>")
        self.app._incognito_btn.pack_forget()
        self._show_step_1()

    def _schedule(self, delay, fn, *args):
        aid = self.root.after(delay, fn, *args)
        self._after_ids.append(aid)
        return aid

    def _clear(self):
        for aid in self._after_ids:
            try: self.root.after_cancel(aid)
            except: pass
        self._after_ids.clear()
        if self.overlay and self.overlay.winfo_exists():
            self.overlay.destroy()
        if self.card and self.card.winfo_exists():
            self.card.destroy()
        self.overlay = None
        self.card    = None

    def _make_card(self, width=460, height=300, overlay_y=0):
        self.overlay = tk.Frame(self.root, bg="#0D0D1A")
        # overlay_y lets step 2 leave the header exposed
        self.overlay.place(x=0, y=overlay_y, relwidth=1, relheight=1)
        self.overlay.lift()
        card = tk.Frame(self.root, bg=HEADER_BG,
                        highlightbackground=ACCENT, highlightthickness=1)
        card.place(relx=0.5, rely=0.60, anchor="center",
                   width=width, height=height)
        card.lift()
        self.card = card
        self._slide_up(card, width, height)
        return card

    def _slide_up(self, card, w, h, frame=0, total=18):
        if not (card and card.winfo_exists()):
            return
        t = _ease_out_cubic(frame / total)
        rely = 0.60 - 0.10 * t
        card.place(relx=0.5, rely=rely, anchor="center", width=w, height=h)
        if frame < total:
            self._schedule(13, self._slide_up, card, w, h, frame + 1, total)

    # ── Shared widgets ────────────────────────────────────────────────────

    def _progress(self, card, current, total=6):
        row = tk.Frame(card, bg=HEADER_BG)
        row.place(relx=0.5, rely=0.0, anchor="n", y=8)
        for i in range(total):
            active     = i < current
            is_current = (i == current - 1)
            size       = 11 if is_current else 7
            color      = ACCENT if active else BORDER
            pad        = (14 - size) // 2
            c = tk.Canvas(row, width=14, height=14, bg=HEADER_BG,
                          highlightthickness=0)
            c.pack(side="left", padx=3)
            c.create_oval(pad, pad, 14-pad, 14-pad, fill=color, outline="")
            if is_current:
                self._pulse_dot(c, pad, size)

    def _pulse_dot(self, canvas, pad, size, phase=0):
        if not (canvas and canvas.winfo_exists()):
            return
        t = (1 + __import__("math").sin(phase * 0.4)) / 2
        color = _hex_lerp(ACCENT, "#8A8EF8", t)
        canvas.delete("all")
        canvas.create_oval(pad, pad, 14-pad, 14-pad, fill=color, outline="")
        self._schedule(60, self._pulse_dot, canvas, pad, size, phase + 1)

    def _typewriter(self, label, text, speed=30, delay=250):
        def tick(i):
            if not (label and label.winfo_exists()):
                return
            label.config(text=text[:i])
            if i <= len(text):
                self._schedule(speed, tick, i + 1)
        label.config(text="")
        self._schedule(delay, tick, 1)

    def _skip_btn(self, card, cmd, label="Skip  →"):
        b = tk.Button(card, text=label,
                      font=("Segoe UI", 9, "bold"),
                      bg=BTN_BG, fg=TEXT_DARK,
                      relief="flat", bd=0, cursor="hand2",
                      padx=12, pady=5,
                      activebackground=BTN_HOVER,
                      activeforeground=TEXT_DARK,
                      command=cmd)
        b.place(relx=1.0, rely=1.0, anchor="se", x=-14, y=-12)
        b.bind("<Enter>", lambda _: b.config(bg=BTN_HOVER))
        b.bind("<Leave>", lambda _: b.config(bg=BTN_BG))

    def _accent_btn(self, parent, text, cmd):
        hover = _hex_lerp(ACCENT, "#ffffff", 0.12)
        b = tk.Button(parent, text=text,
                      font=("Segoe UI", 10, "bold"),
                      bg=ACCENT, fg="white",
                      relief="flat", bd=0, cursor="hand2",
                      padx=22, pady=9,
                      activebackground=hover,
                      activeforeground="white",
                      command=cmd)
        b.bind("<Enter>", lambda _: b.config(bg=hover))
        b.bind("<Leave>", lambda _: b.config(bg=ACCENT))
        return b

    def _icon_label(self, card, emoji, rely):
        tk.Label(card, text=emoji, font=("Segoe UI Emoji", 32),
                 bg=HEADER_BG, fg=TEXT_DARK).place(relx=0.5, rely=rely, anchor="center")

    # ── Step 1 — Welcome ──────────────────────────────────────────────────

    def _show_step_1(self):
        self._clear()
        card = self._make_card(500, 340)
        self._progress(card, 1)

        self._icon_label(card, "🗂️", 0.22)

        title = tk.Label(card, text="",
                         font=("Segoe UI", 17, "bold"),
                         bg=HEADER_BG, fg=TEXT_DARK)
        title.place(relx=0.5, rely=0.42, anchor="center")
        self._typewriter(title, "Smart Clipboard")

        tk.Label(card, text="Your clipboard has a memory now.\nEverything you copy is saved and searchable.",
                 font=("Segoe UI", 10), bg=HEADER_BG, fg=TEXT_GRAY,
                 justify="center").place(relx=0.5, rely=0.62, anchor="center")

        b = self._accent_btn(card, "Let's go  →", self._show_step_2)
        b.place(relx=0.5, rely=0.83, anchor="center")
        self._skip_btn(card, self._finish, label="Skip setup")

    # ── Step 2 — Activate ─────────────────────────────────────────────────

    def _show_step_2(self):
        self._clear()

        # Force inactive so the button reads "○ Inactive" for the user to click
        if self.app._active:
            self.app._active = False
            self.app._toggle_btn.config(text="○ Inactive", bg="#3A3A5C")

        # overlay_y=63 leaves the header (height=62) fully exposed and clickable
        card = self._make_card(500, 270, overlay_y=73)
        self._progress(card, 2)

        self._icon_label(card, "💡", 0.26)

        title = tk.Label(card, text="",
                         font=("Segoe UI", 13, "bold"),
                         bg=HEADER_BG, fg=TEXT_DARK)
        title.place(relx=0.5, rely=0.40, anchor="center")
        self._typewriter(title, "First — turn on clipboard capture.")

        tk.Label(card, text="Click the  ○ Inactive  button in the top bar to start.",
                 font=("Segoe UI", 9), bg=HEADER_BG, fg=TEXT_GRAY
                 ).place(relx=0.5, rely=0.57, anchor="center")

        tk.Label(card, text="or press  Ctrl + Shift + E",
                 font=("Segoe UI", 8), bg=HEADER_BG, fg=TEXT_GRAY
                 ).place(relx=0.5, rely=0.72, anchor="center")

        # Pulse the toggle button border to draw the eye
        self._pulse_widget_border(self.app._toggle_btn)

        # Intercept the toggle — restore original after one click then advance
        original_toggle = self.app._toggle_active
        def _watch_toggle():
            self.app._toggle_active = original_toggle
            self.app._toggle_btn.config(command=original_toggle)
            original_toggle()
            self._schedule(400, self._show_step_3)

        self.app._toggle_active = _watch_toggle
        self.app._toggle_btn.config(command=_watch_toggle)

        self._skip_btn(card, self._skip_activate)

    def _skip_activate(self):
        self.app._toggle_btn.config(command=self.app._toggle_active)
        if not self.app._active:
            self.app._toggle_active()
        self._show_step_3()

    def _pulse_widget_border(self, widget, phase=0):
        if not (self.card and self.card.winfo_exists()):
            return
        color = ACCENT if phase % 2 == 0 else HEADER_BG
        try:
            widget.config(highlightbackground=color, highlightthickness=2)
        except Exception:
            pass
        self._schedule(500, self._pulse_widget_border, widget, phase + 1)

    # ── Step 3 — Copy ─────────────────────────────────────────────────────

    def _show_step_3(self):
        self._clear()
        card = self._make_card(500, 330)
        self._progress(card, 3)

        self._icon_label(card, "📝", 0.22)

        title = tk.Label(card, text="",
                         font=("Segoe UI", 13, "bold"),
                         bg=HEADER_BG, fg=TEXT_DARK)
        title.place(relx=0.5, rely=0.38, anchor="center")
        self._typewriter(title, "Copy anything right now.")

        tk.Label(card, text="Select the text below and press  Ctrl + C",
                 font=("Segoe UI", 9), bg=HEADER_BG, fg=TEXT_GRAY
                 ).place(relx=0.5, rely=0.51, anchor="center")

        entry_frame = tk.Frame(card, bg=BORDER)
        entry_frame.place(relx=0.5, rely=0.67, anchor="center",
                          width=314, height=36)
        demo = tk.Entry(entry_frame, font=("Segoe UI", 10),
                        bg=WHITE, fg=TEXT_DARK,
                        relief="flat", bd=0, justify="center",
                        insertbackground=TEXT_DARK)
        demo.pack(fill="both", expand=True, padx=1, pady=1)
        demo.insert(0, "Hello from Smart Clipboard!")
        demo.select_range(0, tk.END)
        demo.focus_set()

        self._pulse_border(entry_frame)
        demo.bind("<Control-c>", lambda *_: self._schedule(350, self._show_step_4))

        self._skip_btn(card, self._show_step_4)

    def _pulse_border(self, frame, phase=0, cycles=10):
        if not (frame and frame.winfo_exists()):
            return
        if phase >= cycles * 2:
            return
        color = ACCENT if phase % 2 == 0 else BORDER
        frame.config(bg=color)
        self._schedule(650, self._pulse_border, frame, phase + 1, cycles)

    # ── Step 4 — Launcher ─────────────────────────────────────────────────

    def _show_step_4(self):
        self._clear()
        card = self._make_card(500, 325)
        self._progress(card, 4)

        self._icon_label(card, "🚀", 0.22)

        title = tk.Label(card, text="",
                         font=("Segoe UI", 13, "bold"),
                         bg=HEADER_BG, fg=TEXT_DARK)
        title.place(relx=0.5, rely=0.36, anchor="center")
        self._typewriter(title, "Now the magic. Press this anywhere:")

        keys_frame = tk.Frame(card, bg=HEADER_BG)
        keys_frame.place(relx=0.5, rely=0.60, anchor="center")
        self._build_keys(keys_frame)

        tk.Label(card, text="Your clips appear instantly — no app switching.",
                 font=("Segoe UI", 9), bg=HEADER_BG, fg=TEXT_GRAY
                 ).place(relx=0.5, rely=0.82, anchor="center")

        self._skip_btn(card, self._show_step_5, label="Next  →")

    def _build_keys(self, frame):
        key_boxes = []
        for item in ["Ctrl", "+", "Shift", "+", "V"]:
            if item == "+":
                tk.Label(frame, text="+", bg=HEADER_BG,
                         fg=TEXT_GRAY, font=("Segoe UI", 13)).pack(side="left", padx=5)
            else:
                box = tk.Frame(frame, bg=WHITE,
                               highlightbackground=BORDER,
                               highlightthickness=1)
                box.pack(side="left", padx=5)
                lbl = tk.Label(box, text=item, bg=WHITE,
                               fg=TEXT_DARK, font=("Segoe UI", 10, "bold"),
                               padx=11, pady=7)
                lbl.pack()
                key_boxes.append((box, lbl))

        def pop(i):
            if i >= len(key_boxes):
                return
            box, lbl = key_boxes[i]
            box.config(highlightbackground=ACCENT)
            lbl.config(fg=ACCENT)
            self._schedule(180, lambda b=box, l=lbl: (
                b.config(highlightbackground=ACCENT) if b.winfo_exists() else None,
                l.config(fg=TEXT_DARK)              if l.winfo_exists() else None,
            ))
            self._schedule(i * 160 + 480, pop, i + 1)

        self._schedule(350, pop, 0)

    # ── Step 5 — Private mode ─────────────────────────────────────────────

    def _show_step_5(self):
        self._clear()
        card = self._make_card(480, 340)
        self._progress(card, 5)

        self._icon_label(card, "🔒", 0.22)

        title = tk.Label(card, text="",
                         font=("Segoe UI", 13, "bold"),
                         bg=HEADER_BG, fg=TEXT_DARK)
        title.place(relx=0.5, rely=0.38, anchor="center")
        self._typewriter(title, "👁  Private mode")

        # Mini preview of the button
        preview_frame = tk.Frame(card, bg=HEADER_BG)
        preview_frame.place(relx=0.5, rely=0.56, anchor="center")
        tk.Label(preview_frame, text="🔒 Private ON",
                 font=("Segoe UI", 10, "bold"),
                 bg="#6C3483", fg="white",
                 padx=20, pady=8).pack()

        tk.Label(card, text="Purple button — clips stay in memory only,\nnever written to disk.",
                 font=("Segoe UI", 9), bg=HEADER_BG, fg=TEXT_GRAY,
                 justify="center").place(relx=0.5, rely=0.78, anchor="center")

        self._skip_btn(card, self._show_step_6, label="Next  →")

    # ── Step 6 — Done ─────────────────────────────────────────────────────

    def _show_step_6(self):
        self._clear()
        card = self._make_card(500, 340)
        self._progress(card, 6)

        title = tk.Label(card, text="",
                         font=("Segoe UI", 16, "bold"),
                         bg=HEADER_BG, fg=TEXT_DARK)
        title.place(relx=0.5, rely=0.14, anchor="center")
        self._typewriter(title, "You're all set! 🎉", speed=40)

        shortcuts = [
            ("Ctrl + C",         "saves clips automatically"),
            ("Ctrl + Alt + C",   "copies and pins instantly"),
            ("Ctrl + Shift + V", "opens quick launcher"),
            ("Double Ctrl",      "opens Smart Clipboard"),
        ]

        ref = tk.Frame(card, bg=WHITE,
                       highlightbackground=BORDER, highlightthickness=1)
        ref.place(relx=0.5, rely=0.52, anchor="center", width=385, height=138)

        for key, desc in shortcuts:
            row = tk.Frame(ref, bg=WHITE)
            row.pack(fill="x", padx=14, pady=6)
            tk.Label(row, text=key, font=("Segoe UI", 9, "bold"),
                     bg=WHITE, fg=ACCENT, width=16, anchor="w").pack(side="left")
            tk.Label(row, text=desc, font=("Segoe UI", 9),
                     bg=WHITE, fg=TEXT_DARK, anchor="w").pack(side="left")

        b = self._accent_btn(card, "Start using it  →", self._finish)
        b.place(relx=0.5, rely=0.88, anchor="center")

        self._schedule(500, self._confetti)

    def _confetti(self):
        if not (self.overlay and self.overlay.winfo_exists()):
            return
        colors = [ACCENT, "#FF6B6B", "#FFD93D", "#6BCEFF", "#A8FF78", "#FF9FF3"]
        canvas = tk.Canvas(self.overlay, highlightthickness=0, bg="#0D0D1A")
        canvas.place(x=0, y=0, relwidth=1, relheight=1)

        w = self.root.winfo_width() or 800
        dots = []
        for _ in range(40):
            x  = random.randint(0, w)
            sz = random.randint(5, 11)
            dot = canvas.create_oval(x, -14, x+sz, -14+sz,
                                     fill=random.choice(colors), outline="")
            dots.append([dot, random.uniform(4.5, 9.0), random.uniform(-1.5, 1.5)])

        def fall(step):
            if not (canvas and canvas.winfo_exists()):
                return
            for d in dots:
                canvas.move(d[0], d[2], d[1])
            if step < 80:
                self._schedule(16, fall, step + 1)
            else:
                if canvas.winfo_exists():
                    canvas.destroy()

        fall(0)

    # ── Finish ────────────────────────────────────────────────────────────

    def _finish(self):
        self._clear()
        self.app._incognito_btn.pack(side="left", padx=(8, 0), pady=18)
        self.root.bind("<Escape>", lambda *_: self.app._hide_window())
        s = storage.load_settings()
        s["onboarding_complete"] = True
        storage.save_settings(s)
