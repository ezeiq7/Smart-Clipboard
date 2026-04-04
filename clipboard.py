# clipboard.py
import pyperclip
from PIL import ImageGrab

def get_clipboard():
    """Returns (type, content) where type is 'text' or 'image'"""
    # Try image first
    try:
        img = ImageGrab.grabclipboard()
        if img is not None:
            return ('image', img)
    except:
        pass

    # Fall back to text
    try:
        text = pyperclip.paste()
        if text:
            return ('text', text)
    except:
        pass

    return (None, None)

def set_clipboard(text):
    pyperclip.copy(text)

def set_clipboard_image(path):
    """Copy an image file back to clipboard"""
    try:
        from PIL import Image
        import win32clipboard
        import io
        img = Image.open(path)
        output = io.BytesIO()
        img.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:]
        output.close()
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        win32clipboard.CloseClipboard()
        return True
    except:
        return False