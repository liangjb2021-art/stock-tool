"""Keep it simple: terminal bell, plus an optional best-effort desktop notification."""
from __future__ import annotations

import shutil
import subprocess
import sys


def bell() -> None:
    sys.stdout.write("\a")
    sys.stdout.flush()


def desktop_notify(title: str, message: str) -> bool:
    """Try notify-send (Linux) or osascript (macOS). Returns True if a command ran OK."""
    try:
        if shutil.which("notify-send"):
            cmd = ["notify-send", title, message]
        elif sys.platform == "darwin" and shutil.which("osascript"):
            esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')  # noqa: E731
            cmd = ["osascript", "-e", f'display notification "{esc(message)}" with title "{esc(title)}"']
        else:
            return False
        return subprocess.run(cmd, timeout=5, capture_output=True).returncode == 0
    except Exception:  # noqa: BLE001 - notifications must never break watching
        return False
