# storage.py
import json
import os
import sys
from datetime import datetime

def _data_dir():
    base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) \
           else os.path.dirname(os.path.abspath(__file__))
    d = os.path.join(base, "data")
    os.makedirs(d, exist_ok=True)
    return d

DATA_FILE     = os.path.join(_data_dir(), "clips.json")
SETTINGS_FILE = os.path.join(_data_dir(), "settings.json")

# ── Settings ───────────────────────────────────────────────────────────────

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return {"max_clips": 200, "max_hours": None, "excluded_apps": [], "auto_start": True, "global_shortcuts": True, "session_gap_minutes": 30}
    try:
        s = json.load(open(SETTINGS_FILE))
    except (json.JSONDecodeError, ValueError):
        s = {}
    # migrate old max_days → max_hours
    if "max_days" in s and "max_hours" not in s:
        s["max_hours"] = s.pop("max_days") * 24 if s["max_days"] else None
    s.setdefault("max_clips", 200)
    s.setdefault("max_hours", None)
    s.setdefault("excluded_apps", [])
    s.setdefault("auto_start", True)
    s.setdefault("global_shortcuts", True)
    s.setdefault("session_gap_minutes", 30)
    s.setdefault("shortcut_launcher",     True)
    s.setdefault("shortcut_toggle",       True)
    s.setdefault("shortcut_incognito",    True)
    s.setdefault("shortcut_pin",          True)
    s.setdefault("shortcut_show",         True)
    s.setdefault("shortcut_peek",         True)
    s.setdefault("shortcut_hotkey_clips", True)
    s.setdefault("store_sensitive",       False)
    return s

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)
    # Apply limits immediately to existing clips
    clips = load_clips()
    clips = _apply_limits(clips)
    with open(DATA_FILE, "w") as f:
        json.dump(clips, f, indent=2)

# ── Clips ──────────────────────────────────────────────────────────────────

def _ensure_file():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            json.dump([], f)

def load_clips():
    _ensure_file()
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, ValueError):
        # Corrupted file — back it up and start fresh
        import shutil
        shutil.copy(DATA_FILE, DATA_FILE + ".bak")
        with open(DATA_FILE, "w") as f:
            json.dump([], f)
        data = []
    converted = []
    for item in data:
        if isinstance(item, str):
            converted.append({"text": item, "date": "Unknown", "pinned": False,
                               "tag": None, "template": False, "hotkey_slot": None})
        else:
            item.setdefault("pinned",      False)
            item.setdefault("tag",         None)
            item.setdefault("template",    False)
            item.setdefault("hotkey_slot", None)
            converted.append(item)
    return converted

def _apply_limits(clips):
    """Purge unprotected clips exceeding max_clips or older than max_hours.
    Protected = pinned OR tagged. Returns the trimmed list (does not save)."""
    s         = load_settings()
    max_clips = s.get("max_clips")
    max_hours = s.get("max_hours")

    def _protected(c):
        return c.get("pinned") or bool(c.get("tag"))

    if max_hours:
        now = datetime.now()
        def _too_old(c):
            if _protected(c):
                return False
            try:
                dt      = datetime.strptime(c["date"], "%d %b %Y, %H:%M")
                elapsed = (now - dt).total_seconds() / 3600
                return elapsed >= max_hours
            except Exception:
                return False
        clips = [c for c in clips if not _too_old(c)]

    if max_clips and max_clips > 0:
        protected   = [c for c in clips if     _protected(c)]
        unprotected = [c for c in clips if not _protected(c)]
        unprotected = unprotected[:max_clips]
        clips = protected + unprotected

    return clips

def save_image(img):
    img_dir = os.path.join(_data_dir(), "images")
    os.makedirs(img_dir, exist_ok=True)
    filename = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
    path = os.path.join(img_dir, filename)
    img.save(path)
    return path

APP_NAMES = {
    "chrome.exe":    "Google Chrome",
    "firefox.exe":   "Firefox",
    "msedge.exe":    "Microsoft Edge",
    "winword.exe":   "Microsoft Word",
    "excel.exe":     "Microsoft Excel",
    "powerpnt.exe":  "PowerPoint",
    "code.exe":      "VS Code",
    "notepad.exe":   "Notepad",
    "outlook.exe":   "Outlook",
    "slack.exe":     "Slack",
    "discord.exe":   "Discord",
    "teams.exe":     "Microsoft Teams",
    "acrobat.exe":              "Adobe Acrobat",
    "applicationframehost.exe": "Windows App",
}

def _get_source_app():
    try:
        import ctypes, ctypes.wintypes, psutil
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = ctypes.wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe = psutil.Process(pid.value).name().lower()
        if exe in APP_NAMES:
            return APP_NAMES[exe]
        return exe.replace(".exe", "").capitalize()
    except Exception:
        return None

def save_clip(text_or_path, clip_type="text", source=None):
    clips = load_clips()
    if clip_type == "text" and any(c.get("text") == text_or_path for c in clips):
        return clips
    clips.insert(0, {
        "text":     text_or_path,
        "type":     clip_type,
        "date":     datetime.now().strftime("%d %b %Y, %H:%M"),
        "pinned":   False,
        "tag":      None,
        "template": False,
        "source":   source if source is not None else _get_source_app(),
    })
    clips = _apply_limits(clips)
    with open(DATA_FILE, "w") as f:
        json.dump(clips, f, indent=2)
    return clips

def delete_clip(text):
    clips = [c for c in load_clips() if c["text"] != text]
    with open(DATA_FILE, "w") as f:
        json.dump(clips, f, indent=2)
    return clips

def update_clip_text(old_text, new_text):
    clips = load_clips()
    for c in clips:
        if c["text"] == old_text:
            c["text"] = new_text
            break
    with open(DATA_FILE, "w") as f:
        json.dump(clips, f, indent=2)
    return clips

def toggle_pin(text):
    clips = load_clips()
    for c in clips:
        if c["text"] == text:
            c["pinned"] = not c["pinned"]
            break
    with open(DATA_FILE, "w") as f:
        json.dump(clips, f, indent=2)
    return clips

def toggle_template(text):
    clips = load_clips()
    for c in clips:
        if c["text"] == text:
            c["template"] = not c.get("template", False)
            break
    with open(DATA_FILE, "w") as f:
        json.dump(clips, f, indent=2)
    return clips

def set_tag(text, tag):
    clips = load_clips()
    for c in clips:
        if c["text"] == text:
            c["tag"] = tag if tag != "none" else None
            break
    with open(DATA_FILE, "w") as f:
        json.dump(clips, f, indent=2)
    return clips

def filter_by_tag(tag):
    clips = load_clips()
    if tag == "all":
        return clips
    return [c for c in clips if c.get("tag") == tag]

def _image_search_label(clip):
    """Generate a searchable string for image clips: 'Screenshot 19 Apr 14:46'."""
    try:
        from datetime import datetime
        dt = datetime.strptime(clip.get("date", ""), "%d %b %Y, %H:%M")
        return f"Screenshot {dt.strftime('%d %b %H:%M')}"
    except Exception:
        return "Screenshot"

def search_clips(query):
    clips = load_clips()
    q = query.lower()
    words = [w for w in q.split() if w]
    wants_template = any("template".startswith(w) for w in words if len(w) >= 3)
    wants_hotkey   = any("hotkey".startswith(w)   for w in words if len(w) >= 3)
    def _matches(c):
        if wants_template and c.get("template"):
            return True
        if wants_hotkey and c.get("hotkey_slot") is not None:
            return True
        tag = c.get("tag") or ""
        if tag and q in tag.lower():
            return True
        if c.get("type") == "image":
            target = _image_search_label(c).lower()
            return q in target or (bool(words) and all(w in target for w in words))
        t = c["text"].lower()
        if q in t:
            return True
        return bool(words) and all(w in t for w in words)
    return [c for c in clips if _matches(c)]

def set_hotkey_slot(text, slot):
    """Assign hotkey slot (1–9) to a clip. Pass slot=None to unassign.
    Clears any other clip that currently holds the same slot."""
    clips = load_clips()
    if slot is not None:
        for c in clips:
            if c.get("hotkey_slot") == slot:
                c["hotkey_slot"] = None
    for c in clips:
        if c["text"] == text:
            c["hotkey_slot"] = slot
            break
    with open(DATA_FILE, "w") as f:
        json.dump(clips, f, indent=2)
    return clips

def get_clip_by_hotkey(slot):
    """Return the clip assigned to the given hotkey slot (1–9), or None."""
    for c in load_clips():
        if c.get("hotkey_slot") == slot:
            return c
    return None
