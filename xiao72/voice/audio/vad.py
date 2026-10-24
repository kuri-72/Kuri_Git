"""
语音活动检测（VAD）
=====================
作用：判断"现在有没有人在说话"，把连续音频流切成一句一句。

为什么不用固定时长录音：
    实测 5 秒固定录音会把结尾的字切掉（"百分之五十" → "百分之五"）。
    VAD 能做到"你说多久就录多久"。

技术：Silero VAD（ONNX 版）
    模型 2.2 MB，输入 16kHz / 512 采样点（32ms）一帧，
    输出 0~1 的"人声概率"。

    ⚠ 不要用 `pip install silero-vad`：它会拉 torch（2.5GB）。
      我们把 .onnx 模型直接喂给 onnxruntime 就够了。

模型文件：D:\\AI_Cache\\models\\silero_vad.onnx
下载地址：https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

# Silero VAD v5 的接口约定
FRAME_SIZE = 512          # 16kHz 下 = 32ms
SAMPLE_RATE = 16000


def default_model_dir() -> Path:
    """模型目录：优先 LOCALAPPDATA，不写死盘符。"""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / "xiao72" / "models"


def default_vad_model() -> Path:
    """VAD 模型路径：X72_VAD_MODEL > X72_MODEL_DIR/silero_vad.onnx > 默认目录。"""
    explicit = os.environ.get("X72_VAD_MODEL")
    if explicit:
        return Path(explicit)
    model_dir = os.environ.get("X72_MODEL_DIR")
    base = Path(model_dir) if model_dir else default_model_dir()
    return base / "silero_vad.onnx"


class SileroVad:
    """单帧人声概率评估器（有内部状态，必须按顺序喂帧）。"""

    def __init__(self, model_path: str | None = None, sr: int = SAMPLE_RATE):
        path = Path(model_path) if model_path else default_vad_model()
        if not path.exists():
            raise FileNotFoundError(
                f"找不到 VAD 模型：{path}\n"
                "下载：https://github.com/snakers4/silero-vad/raw/master/"
                "src/silero_vad/data/silero_vad.onnx\n"
                "放到上面这个路径，或在 .env 里设 X72_VAD_MODEL=<完整路径>"
            )
        if sr not in (8000, 16000):
            raise ValueError("Silero VAD 只支持 8k 或 16k 采样率")

        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.log_severity_level = 3
        self._sess = ort.InferenceSession(
            str(path), sess_options=opts, providers=["CPUExecutionProvider"]
        )
        self.sr = sr
        self.reset()

    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        # ★ Silero v5 需要额外 64 个采样点作为"上下文"，
        #   每帧实际输入是 context(64) + frame(512) = 576。
        #   少喂这 64 点会导致概率恒低（实测只能到 0.08，永远触不了 0.5）。
        ctx = 64 if self.sr == 16000 else 32
        self._context = np.zeros((1, ctx), dtype=np.float32)

    def probability(self, frame: np.ndarray) -> float:
        """返回这一帧是人声的概率 0~1。

        frame 必须是 float32、长度 512（16k）或 256（8k）。
        长度不对会自动补零/截断，不报错。
        """
        need = FRAME_SIZE if self.sr == 16000 else 256
        x = np.asarray(frame, dtype=np.float32).flatten()

        if x.size < need:
            x = np.pad(x, (0, need - x.size))
        elif x.size > need:
            x = x[:need]

        frame2d = x.reshape(1, -1)
        inp = np.concatenate([self._context, frame2d], axis=1)   # 576 点
        sr_arr = np.array(self.sr, dtype=np.int64)

        out, state = self._sess.run(
            None, {"input": inp, "state": self._state, "sr": sr_arr}
        )
        self._state = state
        self._context = inp[:, -self._context.shape[1]:]         # 更新上下文
        return float(np.asarray(out).reshape(-1)[0])


class VadSegmenter:
    """把持续的音频流切成"一句一句"。

    状态机：
        IDLE     ——持续的 32ms 帧进来，只统计概率，保留最近 pre_roll 的帧
        SPEAKING ——检出人声后一直累积，直到静音够久或超过最长时长

    用法：
        seg = VadSegmenter()
        for frame in frames:            # 每帧 512 个 16k 采样点
            utt = seg.push(frame)
            if utt is not None:
                print("说完一句，长度", len(utt))
    """

    def __init__(self,
                 model_path: str | None = None,
                 threshold: float = 0.5,
                 end_silence_ms: int = 1200,
                 min_speech_ms: int = 250,
                 max_speech_s: float = 15.0,
                 pre_roll_ms: int = 800,
                 start_frames: int = 2,
                 sr: int = SAMPLE_RATE):
        self.sr = sr
        self.frame_size = FRAME_SIZE if sr == 16000 else 256
        self.frame_ms = self.frame_size * 1000 // sr

        self.vad = SileroVad(model_path, sr)
        self.threshold = threshold
        self.end_silence_ms = end_silence_ms
        self.min_speech_ms = min_speech_ms
        self.max_speech_s = max_speech_s
        self.pre_roll_ms = pre_roll_ms
        self.start_frames = start_frames

        self._pre_roll_frames = max(1, pre_roll_ms // self.frame_ms)
        self.reset()

    # ---------------------------------------------------------- 状态
    def reset(self) -> None:
        self.vad.reset()
        self._speaking = False
        self._frames: list[np.ndarray] = []      # 当前这一句
        self._ring: list[np.ndarray] = []        # IDLE 时的 pre-roll
        self._silence_ms = 0.0
        self._speech_ms = 0.0
        self._hit = 0                            # 连续超阈值的帧数
        self.last_prob = 0.0

    @property
    def speaking(self) -> bool:
        return self._speaking

    # ---------------------------------------------------------- 主逻辑
    def push(self, frame: np.ndarray) -> np.ndarray | None:
        """喂一帧。返回完整的一句音频，或 None（还没说完）。"""
        frame = np.asarray(frame, dtype=np.float32).flatten()
        if frame.size != self.frame_size:
            # 长度不符：补齐或截断，保证 VAD 状态机连续
            if frame.size < self.frame_size:
                frame = np.pad(frame, (0, self.frame_size - frame.size))
            else:
                frame = frame[: self.frame_size]

        prob = self.vad.probability(frame)
        self.last_prob = prob
        is_speech = prob >= self.threshold

        if not self._speaking:
            # ---- IDLE：维护 pre-roll 环形缓冲 ----
            self._ring.append(frame)
            if len(self._ring) > self._pre_roll_frames:
                self._ring.pop(0)

            self._hit = self._hit + 1 if is_speech else 0
            if self._hit >= self.start_frames:
                # 起录：把 pre-roll 补到开头，避免丢首字
                self._speaking = True
                self._frames = list(self._ring)
                self._speech_ms = self._hit * self.frame_ms
                self._silence_ms = 0.0
                self._ring.clear()
            return None

        # ---- SPEAKING：累积 ----
        self._frames.append(frame)
        if is_speech:
            self._speech_ms += self.frame_ms
            self._silence_ms = 0.0
        else:
            self._silence_ms += self.frame_ms

        total_ms = len(self._frames) * self.frame_ms

        finished = False
        if self._silence_ms >= self.end_silence_ms:
            finished = True
        elif total_ms >= self.max_speech_s * 1000:
            finished = True                       # 保护：防止无限录音

        if not finished:
            return None

        audio = np.concatenate(self._frames) if self._frames else np.zeros(0, np.float32)
        speech_ms = self._speech_ms
        self.reset()

        # 太短视为噪声（咳嗽/关门/键盘）
        if speech_ms < self.min_speech_ms:
            return None
        return audio

    def flush(self) -> np.ndarray | None:
        """强制结束当前这一句（用于录音流结束/超时）。

        场景：说话中途流被切断（比如固定时长录音结束、网络中断），
        这时不会有"静音尾巴"，等不到 end_silence 判定。
        """
        if not self._speaking or not self._frames:
            return None

        audio = np.concatenate(self._frames)
        speech_ms = self._speech_ms
        self.reset()

        if speech_ms < self.min_speech_ms:
            return None
        return audio
