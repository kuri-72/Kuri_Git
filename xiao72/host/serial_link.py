"""
小72 · 串口发送（可选）
=========================
没有 USB-TTL 时不需要这个模块 —— 用 --dry-run 看帧就行。
插上模块后，把帧写到串口即可。

依赖：pip install pyserial
"""
from __future__ import annotations

import time


class SerialLink:
    """一行一帧，\n 结尾。带重试与读应答。"""

    def __init__(self, port: str, baud: int = 115200, timeout: float = 0.5,
                 ack: bool = False):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.ack = ack
        self._ser = None

    def open(self):
        try:
            import serial  # type: ignore
        except ImportError as e:
            raise RuntimeError("缺少 pyserial。执行：pip install pyserial") from e
        self._ser = serial.Serial(self.port, self.baud, timeout=self.timeout)
        time.sleep(0.1)      # 等 DTR 稳定，很多 CH340 需要
        return self

    def send(self, frame: str) -> str:
        if self._ser is None:
            self.open()
        assert self._ser is not None
        self._ser.write((frame + "\n").encode("ascii"))
        self._ser.flush()
        if not self.ack:
            return ""
        line = self._ser.readline().decode("ascii", errors="replace").strip()
        return line

    def close(self):
        if self._ser is not None:
            self._ser.close()
            self._ser = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()
        return False


def list_ports() -> list[str]:
    try:
        from serial.tools import list_ports as lp  # type: ignore
    except ImportError:
        return []
    return [p.device for p in lp.comports()]
