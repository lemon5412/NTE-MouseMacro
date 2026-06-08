"""
Entry point for the macro tool.
Sets DPI awareness on Windows before creating any tkinter windows.
"""
import sys
import os

# Windows DPI awareness — must be set before tkinter is imported
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# Ensure the project root is on sys.path so `core` and `ui` are importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.main_panel import MainPanel


def main() -> None:
    app = MainPanel()
    app.run()


if __name__ == "__main__":
    main()
