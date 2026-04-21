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
_peek_active    = False
_peek_locked    = False  # True while overlay is pinned (survives Ctrl+Shift release)
_peek_timer     = None   # threading.Timer for the hold delay

def set_peek_locked(val: bool):
    """Called by ui.py to tell the pynput listener whether the overlay is locked."""
    global _peek_locked
    _peek_locked = val

def reset_ctrl_timer():
    """Invalidate the double-Ctrl timer so a synthetic Ctrl press cannot trigger show_callback."""
    global _last_ctrl_time
    _last_ctrl_time = 0.0

# ── Unified RegisterHotKey thread ────────────────────────────────────────

def _unified_hotkey_thread(registrations, dispatch):
    """Single thread owning ALL RegisterHotKey calls and ONE message loop.
    registrations : list of (hotkey_id, mod, vk) tuples
    dispatch      : dict of {hotkey_id: callable}  — callables take no args
    """
    WM_HOTKEY = 0x0312
    user32    = ctypes.windll.user32

    # Pump once so Windows creates this thread's message queue BEFORE
    # RegisterHotKey posts WM_HOTKEY messages to it.
    msg = ctypes.wintypes.MSG()
    user32.PeekMessageA(ctypes.byref(msg), None, 0, 0, 0)

    for hid, mod, vk in registrations:
        if not user32.RegisterHotKey(None, hid, mod, vk):
            # NOREPEAT not supported on older Windows — retry without it
            user32.RegisterHotKey(None, hid, mod & ~0x4000, vk)

    while True:
        result = user32.GetMessageA(ctypes.byref(msg), None, 0, 0)
        if result == 0:      # WM_QUIT — clean exit
            break
        if result == -1:     # Win32 error — skip, don't spin
            continue
        if msg.message == WM_HOTKEY:
            # Cast to plain Python int — ctypes WPARAM type won't hash-match
            # dict integer keys, causing dispatch.get() to silently miss every hit.
            hid = int(msg.wParam)
            cb  = dispatch.get(hid)
            if cb:
                try:
                    cb()
                except Exception:
                    pass
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageA(ctypes.byref(msg))

    for hid, *_ in registrations:
        user32.UnregisterHotKey(None, hid)

# ── Ctrl+Alt+C via pynput ─────────────────────────────────────────────────

_MODIFIERS = frozenset((
    keyboard.Key.ctrl,   keyboard.Key.ctrl_l,   keyboard.Key.ctrl_r,
    keyboard.Key.shift,  keyboard.Key.shift_l,  keyboard.Key.shift_r,
    keyboard.Key.alt,    keyboard.Key.alt_l,    keyboard.Key.alt_r,
    keyboard.Key.cmd,    keyboard.Key.caps_lock,
))

def _on_press(key, pin_callback=None, show_callback=None,
              peek_show_callback=None,
              peek_dismiss_callback=None, peek_hide_callback=None):
    global _last_ctrl_time, _peek_active, _peek_timer, _pressed
    try:
        # Compute was_fresh before any mutation so all guards below are consistent
        was_fresh = key not in _pressed

        # ── Fix 1: reset stale _peek_active if the overlay no longer exists ──
        # Only on a genuine fresh key press — NOT key-repeat.  Key-repeat events
        # for Ctrl/Shift arrive constantly while held; without this guard they
        # would flip _peek_active=False while the overlay is still visible,
        # causing _on_release to skip the hide call and leaving the overlay stuck.
        if was_fresh and _peek_active and not _peek_locked:
            if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
                       keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
                _peek_active = False
                if _peek_timer is not None:
                    _peek_timer.cancel()
                    _peek_timer = None

        # ── Fix 2: corrupted _pressed — clear if unrealistically large ──────
        if len(_pressed) > 4:
            _pressed.clear()

        is_ctrl = key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r)
        # Only count a fresh tap — ignore key-repeat events while holding
        if is_ctrl and was_fresh:
            now = time.time()
            # Check if Shift or Alt is already held — if so this is a hotkey combo
            # (Ctrl+Shift+1, Ctrl+Shift+V etc.), never a double-Ctrl open
            shift_held = any(k in _pressed for k in (
                keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r))
            alt_held   = any(k in _pressed for k in (
                keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r))
            if not shift_held and not alt_held and now - _last_ctrl_time < 0.3:
                if show_callback:
                    show_callback()
                _last_ctrl_time = 0.0
            else:
                _last_ctrl_time = now

        _pressed.add(key)
        ctrl  = keyboard.Key.ctrl   in _pressed or keyboard.Key.ctrl_l  in _pressed or keyboard.Key.ctrl_r  in _pressed
        shift = keyboard.Key.shift  in _pressed or keyboard.Key.shift_l in _pressed or keyboard.Key.shift_r in _pressed
        alt   = keyboard.Key.alt    in _pressed or keyboard.Key.alt_l   in _pressed or keyboard.Key.alt_r   in _pressed
        c     = any((hasattr(k, 'vk') and k.vk == 67) or (hasattr(k, 'char') and k.char in ('c', 'C')) for k in _pressed)

        if ctrl and alt and c and was_fresh:
            if pin_callback:
                pin_callback()

        # ── Clipboard Peek: Ctrl+Shift held for 300ms ────────────────────
        # Fix 3: only count a non-modifier as blocking if it is the KEY BEING
        # PRESSED RIGHT NOW — stale ghost keys already in _pressed are ignored.
        has_non_modifier = key not in _MODIFIERS

        if ctrl and shift and not alt and not has_non_modifier and not _peek_active:
            # Start hold timer — show after 300ms of uninterrupted hold
            if _peek_timer is None:
                def _fire():
                    global _peek_active, _peek_timer
                    _peek_timer = None
                    # Always show if not already active — be aggressive, not cautious
                    if not _peek_active and peek_show_callback:
                        _peek_active = True
                        peek_show_callback()
                t = threading.Timer(0.3, _fire)
                t.daemon = True
                t.start()
                _peek_timer = t
        elif not (ctrl and shift) or has_non_modifier:
            # Ctrl or Shift dropped, or a non-modifier key pressed — cancel pending timer
            if _peek_timer is not None:
                _peek_timer.cancel()
                _peek_timer = None

        # Esc dismisses the overlay whether it is in peek-active state or locked
        if key == keyboard.Key.esc and (_peek_active or _peek_locked):
            _peek_active = False
            _peek_timer = None
            if peek_dismiss_callback:
                peek_dismiss_callback()
        elif _peek_active:
            if has_non_modifier and was_fresh:
                # A non-modifier key was pressed (e.g. V in Ctrl+Shift+V) — cancel peek
                _peek_active = False
                if peek_hide_callback:
                    peek_hide_callback()

    except:
        pass

def _on_release(key, peek_hide_callback=None):
    global _peek_active, _peek_timer
    try:
        _pressed.discard(key)
        is_ctrl  = key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r)
        is_shift = key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r)
        if is_ctrl or is_shift:
            # Cancel pending hold timer if Ctrl/Shift released before it fires
            if _peek_timer is not None:
                _peek_timer.cancel()
                _peek_timer = None
            if _peek_active:
                _peek_active = False
                if peek_hide_callback:
                    peek_hide_callback()
    except Exception:
        pass

# ── Clipboard event listener ──────────────────────────────────────────────

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
    """Event-driven clipboard listener via AddClipboardFormatListener.
    Creates a hidden message-only window; WM_CLIPBOARDUPDATE fires immediately
    on every clipboard change — no polling, no missed copies."""
    global _last_clip
    

    WM_CLIPBOARDUPDATE = 0x031D
    user32   = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    WNDPROCTYPE = ctypes.WINFUNCTYPE(
        ctypes.c_long,
        ctypes.wintypes.HWND, ctypes.c_uint,
        ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
    )

    def _do_read():
        global _last_clip
        try:
            # Text takes priority — apps like OneNote put both text and image
            # on the clipboard simultaneously; we want the text.
            current = pyperclip.paste()
            if current and current != _last_clip:
                _last_clip = current
                if callback:
                    callback(current)
                return
            # No text (or same as last) — check for a pure image (e.g. Snipping Tool)
            from PIL import ImageGrab
            img = ImageGrab.grabclipboard()
            if img is not None:
                img_id = str(img.size)
                if img_id != _last_clip:
                    _last_clip = img_id
                    if callback:
                        callback(img)
        except Exception:
            pass

    WNDPROCTYPE = ctypes.WINFUNCTYPE(
        ctypes.c_long,
        ctypes.wintypes.HWND, ctypes.c_uint,
        ctypes.c_size_t, ctypes.c_size_t,  # wparam, lparam as size_t
    )

    user32.DefWindowProcW.restype  = ctypes.c_long
    user32.DefWindowProcW.argtypes = [
        ctypes.wintypes.HWND, ctypes.c_uint,
        ctypes.c_size_t, ctypes.c_size_t,
    ]

    def _wnd_proc(hwnd, msg, wparam, lparam):
        if msg == WM_CLIPBOARDUPDATE:
            try:
                owner = _get_clipboard_owner_name()
                if owner in _SNIPPING_TOOLS:
                    def _delayed():
                        time.sleep(1.5)
                        _do_read()
                    threading.Thread(target=_delayed, daemon=True).start()
                else:
                    _do_read()
            except Exception:
                pass
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # Keep wnd_proc alive for the lifetime of this function (GC guard)
    _proc_ref = WNDPROCTYPE(_wnd_proc)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style",         ctypes.c_uint),
            ("lpfnWndProc",   WNDPROCTYPE),
            ("cbClsExtra",    ctypes.c_int),
            ("cbWndExtra",    ctypes.c_int),
            ("hInstance",     ctypes.wintypes.HANDLE),
            ("hIcon",         ctypes.wintypes.HANDLE),
            ("hCursor",       ctypes.wintypes.HANDLE),
            ("hbrBackground", ctypes.wintypes.HANDLE),
            ("lpszMenuName",  ctypes.wintypes.LPCWSTR),
            ("lpszClassName", ctypes.wintypes.LPCWSTR),
        ]

    class_name = f"SmartClipboardListener_{int(time.time())}"

    wc               = WNDCLASSW()
    wc.lpfnWndProc   = _proc_ref
    wc.hInstance     = kernel32.GetModuleHandleW(None)
    wc.lpszClassName = class_name

    user32.RegisterClassW(ctypes.byref(wc))

    HWND_MESSAGE = ctypes.c_void_p(-3)  # -3 as pointer-sized int, works on 32 and 64-bit
    user32.CreateWindowExW.restype = ctypes.wintypes.HWND
    user32.CreateWindowExW.argtypes = [
    ctypes.wintypes.DWORD, ctypes.wintypes.LPCWSTR, ctypes.wintypes.LPCWSTR,
    ctypes.wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_size_t, ctypes.wintypes.HMENU, ctypes.wintypes.HINSTANCE, ctypes.wintypes.LPVOID
]
    HWND_MESSAGE = ctypes.c_size_t(-3).value
    hwnd = user32.CreateWindowExW(
    0, class_name, "SmartClipboard", 0,
    0, 0, 0, 0,
    HWND_MESSAGE,
    None, wc.hInstance, None,
)


    if not hwnd:
       
        return

    user32.AddClipboardFormatListener(hwnd)

    try:
        msg = ctypes.wintypes.MSG()
        while user32.GetMessageA(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageA(ctypes.byref(msg))
    except Exception as e:
        print(f"[clipboard] listener crashed: {e}")
    finally:
        try:
            user32.RemoveClipboardFormatListener(hwnd)
        except Exception:
            pass
        

# ── Entry point ───────────────────────────────────────────────────────────

_pynput_listener  = None  # module-level ref so the watchdog can check and replace it
_clipboard_thread = None  # module-level ref for clipboard listener watchdog


def _make_pynput_listener(pin_callback, show_callback,
                          peek_show_callback, peek_dismiss_callback, peek_hide_callback):
    """Create and start a new keyboard.Listener with guarded callbacks."""
    def on_press(key):
        try:
            _on_press(key, pin_callback, show_callback,
                      peek_show_callback, peek_dismiss_callback, peek_hide_callback)
        except Exception:
            pass

    def on_release(key):
        try:
            _on_release(key, peek_hide_callback)
        except Exception:
            pass

    listener = keyboard.Listener(on_press=on_press, on_release=on_release, suppress=False)
    listener.daemon = True
    listener.start()
    return listener


def start_listener(save_callback, pin_callback=None, launcher_callback=None, toggle_callback=None, incognito_callback=None, show_callback=None, hotkey_clip_callback=None,
                   peek_show_callback=None, peek_dismiss_callback=None, peek_hide_callback=None):
    global _pynput_listener, _clipboard_thread

    def _start_clipboard_thread():
        global _clipboard_thread
        t = threading.Thread(target=_clipboard_listener, args=(save_callback,), daemon=True)
        t.start()
        _clipboard_thread = t

    _start_clipboard_thread()

    def _clipboard_watchdog():
        while True:
            time.sleep(1)
            try:
                if _clipboard_thread is None or not _clipboard_thread.is_alive():
                    
                    _start_clipboard_thread()
            except Exception:
                pass

    threading.Thread(target=_clipboard_watchdog, daemon=True).start()

    _pynput_listener = _make_pynput_listener(
        pin_callback, show_callback,
        peek_show_callback, peek_dismiss_callback, peek_hide_callback,
    )

    def _watchdog():
        global _pynput_listener
        while True:
            time.sleep(1)
            try:
                if _pynput_listener is None or not _pynput_listener.is_alive():
                    _pynput_listener = _make_pynput_listener(
                        pin_callback, show_callback,
                        peek_show_callback, peek_dismiss_callback, peek_hide_callback,
                    )
            except Exception:
                pass

    threading.Thread(target=_watchdog, daemon=True).start()

    # ── Build one unified hotkey thread for ALL RegisterHotKey shortcuts ──
    import win32gui
    MOD_CTRL     = 0x0002
    MOD_SHIFT    = 0x0004
    MOD_NOREPEAT = 0x4000

    registrations = []
    dispatch       = {}

    if launcher_callback:
        registrations.append((1, MOD_CTRL | MOD_SHIFT, 0x56))          # Ctrl+Shift+V
        def _cb_launcher():
            hwnd = win32gui.GetForegroundWindow()
            launcher_callback(hwnd)
        dispatch[1] = _cb_launcher

    if toggle_callback:
        registrations.append((2, MOD_CTRL | MOD_SHIFT, 0x45))          # Ctrl+Shift+E
        dispatch[2] = toggle_callback

    if incognito_callback:
        registrations.append((3, MOD_CTRL | MOD_SHIFT, 0x58))          # Ctrl+Shift+X
        dispatch[3] = incognito_callback

    if hotkey_clip_callback:
        for i in range(9):
            hid  = 10 + i
            slot = i + 1
            registrations.append((hid, MOD_CTRL | MOD_SHIFT | MOD_NOREPEAT, 0x31 + i))
            def _cb_clip(s=slot):
                hwnd = win32gui.GetForegroundWindow()
                hotkey_clip_callback(s, hwnd)
            dispatch[hid] = _cb_clip

    if registrations:
        threading.Thread(
            target=_unified_hotkey_thread,
            args=(registrations, dispatch),
            daemon=True,
        ).start()


