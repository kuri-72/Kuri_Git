"""
语音识别 · faster-whisper 实现
================================
基于 CTranslate2 的 Whisper 重实现，同精度下比原版快约 4 倍。

配置要点：
  device        "cpu" | "cuda"
  compute_type  "int8"（CPU 推荐）/ "float16"（GPU 推荐）/ "int8_float16"
  model_size    tiny / base / small / medium / large-v3

本机（RTX 4070 Laptop 8GB / 31.6GB RAM）实测：
  small + CPU(int8)：10 秒音频约 2.6 秒，实时率 ~3.9x
  显存没用到，完全够用

关于 hallucination：
  Whisper 在"几乎全是静音/噪声"的音频上会**编造出连贯的句子**。
  这不是 bug，是训练数据导致的固有行为。
  对策：
    1. 交给它的音频必须是真人说话（配合 VAD 切句）
    2. 打开 vad_filter=True，让它先滤掉静音再识别
    3. 音频过短（< 0.3 秒）直接返回空，不要调模型
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np

from .base import AsrProvider, AsrResult

def _default_model_dir() -> str:
    """模型目录：优先 LOCALAPPDATA，不写死盘符。"""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "xiao72", "models")


DEFAULT_MODEL_DIR = os.environ.get("X72_MODEL_DIR") or _default_model_dir()

# 领域提示词：告诉 Whisper "你接下来听到的基本都是这些词"。
#
# 为什么这一步性价比最高：
#   Whisper 在无提示时会自由发挥，把「亮度」听成「量都」，把「五十」听成「是」。
#   给了词表之后，解码器会强烈倾向这些词形，中文短指令的准确率提升明显，
#   而且是**零额外成本**（不换模型、不加延迟）。
#
# 注意：prompt 不要太长（超过 ~200 字会占用上下文并可能反效果），
#      也**不要**写完整句子当例子（Whisper 可能把例子复读出来）。
DEFAULT_PROMPT = (
    "以下是智能灯控语音指令的中文转写。"
    "常见词汇：灯、灯光、亮度、调暗、调亮、暗一点、亮一点、太亮、太暗、刺眼、"
    "呼吸、呼吸模式、呼吸灯、闪烁、闪、慢一点、快一点、"
    "关灯、开灯、打开、关闭、睡觉、晚安、最亮、最暗、"
    "百分之十、百分之二十、百分之三十、百分之四十、百分之五十、"
    "百分之六十、百分之七十、百分之八十、百分之九十、一百。"
)


class FasterWhisperProvider(AsrProvider):
    name = "faster-whisper"

    def __init__(self,
                 model_size: str = "small",
                 device: str = "cpu",
                 compute_type: str = "int8",
                 model_dir: str | None = None,
                 beam_size: int = 5,
                 vad_filter: bool = True,
                 num_workers: int = 1,
                 initial_prompt: str | None = DEFAULT_PROMPT):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.model_dir = model_dir or DEFAULT_MODEL_DIR
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self.num_workers = num_workers
        self.initial_prompt = initial_prompt
        self._model = None

    # ---------------------------------------------------------- 加载
    def _ensure_model(self):
        if self._model is not None:
            return self._model

        from faster_whisper import WhisperModel

        Path(self.model_dir).mkdir(parents=True, exist_ok=True)
        self._model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type,
            download_root=self.model_dir,
            num_workers=self.num_workers,
        )
        return self._model

    # ---------------------------------------------------------- 识别
    def transcribe(self, audio: np.ndarray | str,
                   language: str | None = "zh") -> AsrResult:
        # 极短音频直接返回，避免模型编造内容
        if isinstance(audio, np.ndarray):
            if audio.size < 16000 * 0.3:
                return AsrResult(text="", duration=audio.size / 16000)

        model = self._ensure_model()

        t0 = time.time()
        segments, info = model.transcribe(
            audio,
            language=language,
            beam_size=self.beam_size,
            vad_filter=self.vad_filter,
            initial_prompt=self.initial_prompt,  # 领域提示词：显著提升短指令准确率
            condition_on_previous_text=False,   # 降低复读/编造概率
        )
        seg_list = list(segments)               # 必须消费生成器才会真正计算
        elapsed = time.time() - t0

        text = "".join(s.text for s in seg_list).strip()

        return AsrResult(
            text=text,
            language=getattr(info, "language", "") or "",
            language_probability=float(getattr(info, "language_probability", 0.0) or 0.0),
            duration=float(getattr(info, "duration", 0.0) or 0.0),
            elapsed=elapsed,
            segments=[{"start": s.start, "end": s.end, "text": s.text} for s in seg_list],
        )

    def close(self) -> None:
        self._model = None


class MockAsrProvider(AsrProvider):
    """离线测试用：不加载模型，返回固定文本。"""

    name = "mock"

    def __init__(self, text: str = "灯亮一点"):
        self.text = text

    def transcribe(self, audio, language: str | None = "zh") -> AsrResult:
        dur = 0.0
        if isinstance(audio, np.ndarray):
            dur = audio.size / 16000
        return AsrResult(text=self.text, language="zh",
                         language_probability=1.0, duration=dur, elapsed=0.0)
