# main.py
import sys
from ui import App

if __name__ == "__main__":
    startup = "--startup" in sys.argv
    app = App(startup=startup)
    app.run()