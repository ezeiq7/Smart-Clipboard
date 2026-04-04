# tray.py
import threading
import pystray
from PIL import Image, ImageDraw

def _create_icon():
    # Draw a simple clipboard icon
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle([16, 8, 48, 56], fill="#5B5FEF", outline="#4347C9", width=2)
    draw.rectangle([24, 4, 40, 16], fill="#2A2A3D", outline="#4347C9", width=2)
    return img

def start_tray(show_callback, quit_callback):
    icon_image = _create_icon()

    menu = pystray.Menu(
        pystray.MenuItem("Open Smart Clipboard", show_callback, default=True),
        pystray.MenuItem("Quit", quit_callback)
    )

    icon = pystray.Icon("SmartClipboard", icon_image, "Smart Clipboard — Inactive", menu)

    thread = threading.Thread(target=icon.run, daemon=True)
    thread.start()

    return icon

def set_tray_title(icon, active: bool):
    icon.title = "Smart Clipboard — Active" if active else "Smart Clipboard — Inactive"