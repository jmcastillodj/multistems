"""App de escritorio: servidor local + ventana nativa (WKWebView en macOS)."""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _setup_env():
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "MultiStems"
    else:
        base = Path.home() / ".multistems"
    base.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MULTISTEMS_DATA", str(base / "data"))
    os.environ.setdefault("MULTISTEMS_MODELS", str(base / "models"))
    # ffmpeg incluido en la app (imageio-ffmpeg) → lo exponemos como "ffmpeg" en el PATH
    try:
        import imageio_ffmpeg
        exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
        link = base / "bin" / "ffmpeg"
        link.parent.mkdir(exist_ok=True)
        if not link.exists() or link.resolve() != exe.resolve():
            link.unlink(missing_ok=True)
            link.symlink_to(exe)
        os.environ["PATH"] = f"{link.parent}{os.pathsep}{os.environ.get('PATH', '')}"
    except Exception:
        pass


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    _setup_env()
    import uvicorn
    from .server import app

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.1)
    url = f"http://127.0.0.1:{port}"
    try:
        import webview
        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.create_window("MultiStems", url, width=1280, height=860, min_size=(900, 600))
        webview.start()
    except ImportError:
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    server.should_exit = True
