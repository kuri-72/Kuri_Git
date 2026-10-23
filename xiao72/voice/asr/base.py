"""
语音识别层 · 抽象接口
=======================
参照 xiaozhi-esp32-server 的 Provider 模式：
每种 ASR 后端实现同一个接口，上层（语音链路）只认这个接口，不认具体实现。

好处：
  · 以后想换 FunASR / 云端接口，只加一个实现文件，上层一行不改
  · 可以写一个 MockProvider 做离线测试
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np


@dataclass
class AsrResult:
    """一次识别的结果。"""
    text: str                          # 识别出的文字（已 strip）
    language: str = ""                 # 识别出的语言代码
    language_probability: float = 0.0  # 语言判定置信度
    duration: float = 0.0              # 音频时长（秒）
    elapsed: float = 0.0               # 识别耗时（秒）
    segments: list = field(default_factory=list)  # 原始分段（调试用）

    @property
    def realtime_factor(self) -> float:
        """实时率 = 音频时长 / 识别耗时。>1 表示比实时快。"""
        if self.elapsed <= 0:
            return 0.0
        return self.duration / self.elapsed

    def __str__(self) -> str:
        return (f"{self.text}  "
                f"[{self.language} {self.language_probability:.2f}, "
                f"{self.elapsed:.2f}s, {self.realtime_factor:.1f}x]")


class AsrProvider(ABC):
    """语音识别后端基类。

    输入统一是 **单声道 16kHz float32** 的 numpy 数组（或 wav 路径）。
    输出统一是 AsrResult。
    """

    name: str = "base"

    @abstractmethod
    def transcribe(self, audio: np.ndarray | str,
                   language: str | None = "zh") -> AsrResult:
        """把音频转成文字。

        audio: np.ndarray（float32，16k，单声道）或 wav 文件路径
        language: 语言代码；None 表示自动检测
        """

    def close(self) -> None:
        """释放资源（显存/句柄）。默认不做事。"""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
