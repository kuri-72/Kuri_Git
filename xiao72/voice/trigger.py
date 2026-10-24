"""语音触发层：决定「什么时候开始录音」。

现在默认按空格；以后换成注视检测（K230）或唤醒词（open_kws）时，
只需要新增一个 Trigger 子类，主循环一行都不用改。

接口只有一个方法：

    wait() -> bool      True = 现在开始录，False = 退出程序

约定：`timeout_hint` 表示「开始录音后最多等多久没声音就放弃」。
"""
from __future__ import annotations

import sys


class Trigger:
    """触发器基类。"""

    name = "base"
    timeout_hint = 30.0        # 开始录音后，多久没听到语音就放弃

    def wait(self) -> bool:
        raise NotImplementedError

    def describe(self) -> str:
        """开始等待前打印的提示（返回空串表示不打印）。"""
        return ""


class AutoTrigger(Trigger):
    """旧行为：一直听着，不等触发。用 `--trigger auto` 启用。"""

    name = "auto"
    timeout_hint = 30.0

    def wait(self) -> bool:
        return True

    def describe(self) -> str:
        return "  正在听……（最多等 %.0f 秒）" % self.timeout_hint


class SpaceTrigger(Trigger):
    """按空格开始，q 或 Esc 退出。"""

    name = "space"
    timeout_hint = 8.0         # 按下后 8 秒没说话就放弃，回到等待

    def __init__(self, prompt: str = "[按空格说话   q 退出]"):
        self.prompt = prompt

    def wait(self) -> bool:
        try:
            import msvcrt                     # Windows 专有，读键不回显
        except ImportError:
            return self._wait_stdin()

        sys.stdout.write(self.prompt + "\n")
        sys.stdout.flush()
        while True:
            try:
                ch = msvcrt.getwch()
            except KeyboardInterrupt:
                return False
            if ch == "\x03":                  # Ctrl+C
                return False
            low = ch.lower()
            if low in ("q", "\x1b"):          # q 或 Esc
                return False
            if ch in (" ", "\r"):             # 空格或回车都算「开始」
                return True
            # 其他键忽略，继续等

    def _wait_stdin(self) -> bool:
        """非 Windows 兜底：用 input() 等一行。"""
        try:
            s = input(self.prompt + " ")
        except (EOFError, KeyboardInterrupt):
            return False
        return s.strip().lower() not in ("q", "quit", "exit")


def make_trigger(name: str) -> Trigger:
    """按名字建触发器。未知名字一律回退到 space。"""
    n = (name or "space").strip().lower()
    if n in ("auto", "always", "continuous"):
        return AutoTrigger()
    return SpaceTrigger()
