"""UI 版本的小72：语音闭环 + 本地监控窗口。

结构：
    主线程      pywebview 窗口（Windows 上必须在主线程）
    线程 A      Flask（SSE 推事件）
    线程 B      语音流水线（阻塞式：录音 / ASR / TTS）

启动：
    python run_ui.py            带窗口
    python run_ui.py --browser  只用浏览器打开（调试用）
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PORT = 8720
HOST = "127.0.0.1"


# ---------------------------------------------------------------- 运行时

class Runtime:
    """UI 与流水线之间的共享状态。"""

    def __init__(self, bus):
        self.bus = bus
        self.state = "idle"
        self.settings = {}
        self._cancel = threading.Event()
        self._interrupt = threading.Event()
        self._pending_press = threading.Event()
        self.pipeline = None

    # -- 来自 UI --
    def apply_settings(self, data: dict) -> None:
        self.settings = dict(data)
        p = self.pipeline
        if p is not None and p.tts is not None:
            try:
                p.tts.apply_config(
                    voice=data.get("tts_voice"),
                    rate=data.get("tts_rate"),
                    volume=data.get("tts_volume"),
                )
            except Exception:
                pass
        self.bus.publish({"t": "toast", "text": "已保存，下一句生效"})

    def request_cancel(self) -> None:
        self._cancel.set()

    def request_interrupt(self) -> None:
        """播报中按空格：停声，文字照旧全显。"""
        self._interrupt.set()

    def mark_press(self) -> None:
        self._pending_press.set()

    # -- 来自流水线 --
    def set_state(self, v: str) -> None:
        self.state = v
        self.bus.publish({"t": "state", "v": v})

    def emit(self, event: dict) -> None:
        self.bus.publish(event)

    # -- 给流水线看的标志 --
    @property
    def cancel_flag(self) -> threading.Event:
        return self._cancel

    @property
    def interrupt_flag(self) -> threading.Event:
        return self._interrupt


def start_pipeline(runtime, dry_run: bool) -> None:
    """流水线线程：等按住 → 录音 → ASR → 路由 → 播报。"""
    from voice.pipeline import VoiceAssistant
    from voice.trigger import PushToTalkTrigger

    a = VoiceAssistant(port=None if dry_run else "auto",
                       trigger=PushToTalkTrigger(), use_llm=True)
    a.runtime = runtime
    runtime.pipeline = a

    try:
        a.setup()
    except Exception as e:
        runtime.emit({"t": "toast", "text": "启动失败：%s" % e})
        return

    runtime.emit({"t": "serial", "port": a.port if a.link is not None else None})
    runtime.emit({"t": "led", "brightness": a.state.brightness,
                  "period": a.state.period_ms})

    while True:
        runtime.cancel_flag.clear()
        runtime.interrupt_flag.clear()
        runtime.set_state("waiting")
        if not a.trigger.wait():
            break

        r = a.handle_once()
        if r is not None:
            a.turns += 1
        runtime.emit({"t": "led", "brightness": a.state.brightness,
                      "period": a.state.period_ms})
        runtime.emit({"t": "stats", "turns": a.turns, "ok": a.ok,
                      "unknown": a.unknown, "errors": a.errors,
                      "degraded": a.degraded_count})
        runtime.set_state("idle")

    a.close()


def start_watcher(runtime) -> None:
    """轮询 Esc（取消）和播报中的空格（打断）。"""
    try:
        import ctypes
        user32 = ctypes.windll.user32
    except Exception:
        return

    VK_ESC, VK_SPACE = 0x1B, 0x20
    while True:
        try:
            if user32.GetAsyncKeyState(VK_ESC) & 0x8000:
                runtime.request_cancel()
                time.sleep(0.3)
                continue
            if runtime.state == "speaking" and (user32.GetAsyncKeyState(VK_SPACE) & 0x8000):
                runtime.request_interrupt()
                time.sleep(0.2)
                continue
        except Exception:
            pass
        time.sleep(0.03)


# ---------------------------------------------------------------- 入口

def main() -> int:
    ap = argparse.ArgumentParser(description="小72 监控窗口")
    ap.add_argument("--browser", action="store_true", help="不启 pywebview，直接用浏览器")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--dry-run", action="store_true", help="不发串口")
    args = ap.parse_args()

    from ui import settings as st
    from ui.events import Bus
    from ui.server import create_app

    bus = Bus()
    runtime = Runtime(bus)
    runtime.settings = st.load()

    # 用 UI 的配置覆盖环境变量（TTS 那边读 env）
    os.environ["X72_TTS_VOICE"] = runtime.settings.get("tts_voice", "")
    os.environ["X72_TTS_RATE"] = runtime.settings.get("tts_rate", "")
    os.environ["X72_TTS_VOLUME"] = runtime.settings.get("tts_volume", "")

    app = create_app(bus, runtime)

    def serve():
        app.run(host=HOST, port=args.port, threaded=True, use_reloader=False)

    threading.Thread(target=serve, daemon=True, name="flask").start()
    threading.Thread(target=start_watcher, args=(runtime,), daemon=True,
                     name="watcher").start()
    threading.Thread(target=start_pipeline, args=(runtime, args.dry_run),
                     daemon=True, name="pipeline").start()
    time.sleep(0.8)

    url = "http://%s:%d/" % (HOST, args.port)
    print("[UI] %s" % url)

    if args.browser:
        import webbrowser
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return 0

    import webview

    window = webview.create_window(
        "小72", url, width=1200, height=760, min_size=(900, 600),
        background_color="#0B0B0D",
    )
    print("[UI] 窗口已创建，进入事件循环…", flush=True)
    webview.start()
    print("[UI] 窗口关闭", flush=True)
    # pywebview 在 Windows 上关闭窗口后可能返回非 0 退出码，这里统一成 0
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
