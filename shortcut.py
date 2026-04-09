# shortcut.py
import threading
import time
import ctypes
import ctypes.wintypes
import pyperclip
from pynput import keyboard

_pressed        = set()
_last_clip      = ""
_last_ctrl_time = 0.0

# ── RegisterHotKey helpers ────────────────────────────────────────────────

def _hotkey_thread(mod, vk, hotkey_id, callback):
    """Generic OS-level hotkey via RegisterHotKey."""
    WM_HOTKEY = 0x0312
    ctypes.windll.user32.RegisterHotKey(None, hotkey_id, mod, vk)
    msg = ctypes.wintypes.MSG()
    while ctypes.windll.user32.GetMessageA(ctypes.byref(msg), None, 0, 0) != 0:
        if msg.message == WM_HOTKEY and msg.wParam == hotkey_id:
            callback()
        ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
        ctypes.windll.user32.DispatchMessageA(ctypes.byref(msg))
    ctypes.windll.user32.UnregisterHotKey(None, hotkey_id)


def _launcher_hotkey_thread(launcher_callback):
    """Register Ctrl+Shift+V as a system hotkey.
    RegisterHotKey natively blocks the combo from reaching other apps."""
    import win32gui
    MOD_CONTROL = 0x0002
    MOD_SHIFT   = 0x0004
    VK_V        = 0x56
    HOTKEY_ID   = 1
    WM_HOTKEY   = 0x0312

    ctypes.windll.user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_SHIFT, VK_V)

    msg = ctypes.wintypes.MSG()
    while ctypes.windll.user32.GetMessageA(ctypes.byref(msg), None, 0, 0) != 0:
        if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
            hwnd = win32gui.GetForegroundWindow()
            launcher_callback(hwnd)
        ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
        ctypes.windll.user32.DispatchMessageA(ctypes.byref(msg))

    ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)

# ── Ctrl+Alt+C via pynput ─────────────────────────────────────────────────

def _on_press(key, pin_callback=None, show_callback=None):
    global _last_ctrl_time
    try:
        is_ctrl = key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r)
        # Only count a fresh tap — ignore key-repeat events while holding
        if is_ctrl and key not in _pressed:
            now = time.time()
            if now - _last_ctrl_time < 0.3:
                if show_callback:
                    show_callback()
                _last_ctrl_time = 0.0
            else:
                _last_ctrl_time = now

        _pressed.add(key)
        ctrl = keyboard.Key.ctrl   in _pressed or keyboard.Key.ctrl_l  in _pressed or keyboard.Key.ctrl_r  in _pressed
        alt  = keyboard.Key.alt    in _pressed or keyboard.Key.alt_l   in _pressed or keyboard.Key.alt_r   in _pressed
        c    = any((hasattr(k, 'vk') and k.vk == 67) or (hasattr(k, 'char') and k.char in ('c', 'C')) for k in _pressed)

        if ctrl and alt and c:
            if pin_callback:
                pin_callback()
    except:
        pass

def _on_release(key):
    try:
        _pressed.discard(key)
    except Exception:
        pass

# ── Clipboard polling ─────────────────────────────────────────────────────

_SNIPPING_TOOLS = {"snippingtool.exe", "screenclippinghost.exe", "screensketch.exe"}

def _get_clipboard_owner_name():
    """Return the exe name of the process that last wrote to the clipboard."""
    try:
        import psutil
        hwnd = ctypes.windll.user32.GetClipboardOwner()
        if not hwnd:
            return ""
        pid = ctypes.wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return psutil.Process(pid.value).name().lower()
    except Exception:
        return ""

def _clipboard_listener(callback):
    global _last_clip
    while True:
        try:
            # Check who owns the clipboard BEFORE reading it
            owner = _get_clipboard_owner_name()
            if owner in _SNIPPING_TOOLS:
                # Let Snipping Tool finish showing its popup, then read
                time.sleep(1.5)

            from PIL import ImageGrab
            img = ImageGrab.grabclipboard()
            if img is not None:
                img_id = str(img.size)
                if img_id != _last_clip:
                    _last_clip = img_id
                    if callback:
                        callback(img)
            else:
                current = pyperclip.paste()
                if current and current != _last_clip:
                    _last_clip = current
                    if callback:
                        callback(current)
        except Exception:
            pass
        time.sleep(0.3)

# ── Entry point ───────────────────────────────────────────────────────────

def start_listener(save_callback, pin_callback=None, launcher_callback=None, toggle_callback=None, incognito_callback=None, show_callback=None):
    threading.Thread(target=_clipboard_listener, args=(save_callback,), daemon=True).start()

    def run_pynput():
        with keyboard.Listener(
            on_press=lambda key: _on_press(key, pin_callback, show_callback),
            on_release=_on_release,
            suppress=False,
        ) as listener:
            listener.join()

    threading.Thread(target=run_pynput, daemon=True).start()

    if launcher_callback:
        threading.Thread(
            target=_launcher_hotkey_thread, args=(launcher_callback,), daemon=True
        ).start()

    if toggle_callback:
        # Ctrl+Shift+E — toggle clipboard capture on/off globally
        MOD_CONTROL = 0x0002
        MOD_SHIFT   = 0x0004
        VK_E        = 0x45
        threading.Thread(
            target=_hotkey_thread,
            args=(MOD_CONTROL | MOD_SHIFT, VK_E, 2, toggle_callback),
            daemon=True
        ).start()

    if incognito_callback:
        # Ctrl+Shift+X — toggle private/incognito mode
        MOD_CONTROL = 0x0002
        MOD_SHIFT   = 0x0004
        VK_X        = 0x58
        threading.Thread(
            target=_hotkey_thread,
            args=(MOD_CONTROL | MOD_SHIFT, VK_X, 3, incognito_callback),
            daemon=True
        ).start()
