"""事件总线：流水线线程 →（队列）→ SSE 推送线程。

只做单向广播，简单到不需要锁的花活：
每个订阅者一个 Queue，满了就丢最旧的（UI 卡住时不能拖垮流水线）。
"""
from __future__ import annotations

import queue
import threading
from typing import Any


class Bus:
    def __init__(self) -> None:
        self._subs: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._last: dict[str, Any] = {}

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=256)
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def publish(self, event: dict) -> None:
        # 记住最后一次「状态类」事件，新连上的客户端立刻能拿到当前画面
        t = event.get("t")
        if t in ("state", "led", "serial", "stats"):
            self._last[t] = event
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(event)
            except queue.Full:
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    pass

    def snapshot(self) -> list[dict]:
        return list(self._last.values())
