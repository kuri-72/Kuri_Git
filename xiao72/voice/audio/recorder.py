"""
小72 · 录音器
===============
职责：从指定（或系统默认）麦克风采集音频，统一成 ASR 要的格式：
    单声道 / 16 kHz / float32 [-1, 1]

三个设计点：
  1. **设备组合自动探测**
     Windows 下同一个麦克风会以多个接口暴露，其中可能有"死"的。
     构造时调用 devices.pick_input()，得到一个真正能收到声音的
     (设备索引, 采样率) 组合。

  2. **采集率与目标率分离**
     若探测结果不是 16k，先按该率采集，再降采样到 16k。

  3. **自动增益**
     实测耳机麦克风说话时 RMS 约 -31 dBFS，偏低。
     ASR 在 -20 附近更准，这里做软件增益并加软限幅防削波。
"""
from __future__ import annotations

import time
import wave
from math import gcd
from pathlib import Path

import numpy as np
import sounddevice as sd

from . import devices

TARGET_SR = 16000
TARGET_DBFS = -20.0
MAX_GAIN_DB = 40.0


def resample_to_16k(x: np.ndarray, src_sr: int) -> np.ndarray:
    """把任意采样率转换成 16k。

    优先 scipy（带抗混叠）；否则降采样前先做 3 点滑动平均压低混叠，
    再用线性插值。语音识别对轻微插值误差不敏感。
    """
    if src_sr == TARGET_SR:
        return x.astype(np.float32)

    try:
        from scipy.signal import resample_poly  # type: ignore

        g = gcd(int(src_sr), TARGET_SR)
        return resample_poly(x, TARGET_SR // g, int(src_sr) // g).astype(np.float32)
    except ImportError:
        if src_sr > TARGET_SR:
            k = np.array([1 / 3, 1 / 3, 1 / 3], dtype=np.float32)
            x = np.convolve(x, k, mode="same").astype(np.float32)
        n_out = int(round(len(x) * TARGET_SR / src_sr))
        if n_out <= 0:
            return np.zeros(0, dtype=np.float32)
        idx = np.linspace(0, len(x) - 1, n_out)
        return np.interp(idx, np.arange(len(x)), x).astype(np.float32)


def normalize_gain(x: np.ndarray, target_dbfs: float = TARGET_DBFS) -> tuple[np.ndarray, float]:
    """把 RMS 拉到目标电平，返回 (处理后音频, 增益 dB)。"""
    rms = float(np.sqrt(np.mean(x ** 2)))
    if rms <= 1e-8:
        return x, 0.0

    cur_db = 20 * np.log10(rms)
    gain_db = max(-MAX_GAIN_DB, min(MAX_GAIN_DB, target_dbfs - cur_db))
    if abs(gain_db) < 1.0:
        return x, 0.0

    y = x * (10 ** (gain_db / 20))
    peak = float(np.max(np.abs(y)))
    if peak > 1.0:
        y = np.tanh(y) * 0.95
    return y.astype(np.float32), gain_db


class Recorder:
    """录音器。device=None 时跟随系统默认输入。

    设计要点：
      · 默认尊重系统默认设备，不擅自换成"电平更高"的内置麦克风
      · 只有当录到**数字零**（设备真没数据）时才自动回退到同名其它接口
      · 静音时电平低是正常的（噪声抑制门限），不作为失败条件
    """

    def __init__(self, device: int | str | None = None,
                 sr: int | None = None, verbose: bool = False):
        self.requested = device
        self.device_index, auto_sr = devices.pick_input(device, verbose=verbose)
        self.sr = int(sr) if sr else int(auto_sr)
        self._fallback_tried = False
        self.last_db = -999.0
        self.last_silent = False

    # ---------------------------------------------------------- 自检
    def self_check(self, duration: float = 0.5) -> tuple[bool, float]:
        """检查设备是否有数据（不是检查电平高低）。

        返回 (是否非数字零, RMS dBFS)。
        """
        ok, db = devices.measure_rms(self.device_index, self.sr, duration)
        if not ok:
            raise RuntimeError(f"设备 {self.info()} 无法以 {self.sr}Hz 打开")
        return (db > devices.DEAD_DEVICE_DBFS, db)

    # ---------------------------------------------------------- 录音
    def _capture(self, seconds: float) -> np.ndarray:
        n = int(seconds * self.sr)
        audio = sd.rec(n, samplerate=self.sr, channels=1,
                       dtype="float32", device=self.device_index, blocking=True)
        return audio.flatten().astype(np.float32)

    def _try_fallback(self) -> bool:
        """当前设备录到数字零时，换同名设备的其它接口试一次。"""
        if self._fallback_tried or self.requested is not None:
            return False
        self._fallback_tried = True
        for alt in devices.find_alternatives(self.device_index):
            if alt["index"] == self.device_index and alt["sr"] == self.sr:
                continue
            self.device_index, self.sr = alt["index"], alt["sr"]
            return True
        return False

    def record(self, seconds: float, gain: bool = True) -> np.ndarray:
        x = self._capture(seconds)

        # 数字零 → 尝试回退（只尝试一次）
        if devices.is_dead_signal(x) and self._try_fallback():
            x = self._capture(seconds)

        self.last_silent = devices.is_dead_signal(x)
        rms = float(np.sqrt(np.mean(x ** 2)))
        self.last_db = 20 * np.log10(rms + 1e-12)

        x = resample_to_16k(x, self.sr)
        if gain:
            x, _ = normalize_gain(x)
        return x

    def record_raw(self, seconds: float) -> np.ndarray:
        return self.record(seconds, gain=False)

    # ---------------------------------------------------------- 自动切句
    def record_utterance(self,
                         segmenter=None,
                         timeout: float = 30.0,
                         gain: bool = True,
                         silence_end_ms: int = 1200,
                         max_utterance_ms: int = 10000) -> np.ndarray:
        """一直听，等你说完一句就返回（VAD 自动判断）。

        与 record(seconds) 的区别：
          · 不固定时长，你说多久就录多久
          · 说完（静音 silence_end_ms 毫秒）自动结束
          · pre-roll 避免丢开头，VAD 避免切掉结尾
          · max_utterance_ms：硬上限。VAD 没判出句尾时也不会一直录到 timeout，
            否则会长音频送进 Whisper，解码时间随长度线性增长（实测 30s 音频 ~20s）

        返回 float32 / 16k / 单声道；超时无语音则返回空数组。
        """
        from .vad import FRAME_SIZE, VadSegmenter

        if segmenter is None:
            segmenter = VadSegmenter(end_silence_ms=silence_end_ms)
        else:
            segmenter.reset()
        segmenter.end_silence_ms = silence_end_ms

        # 采集率可能是 44.1k/48k，统一转 16k 后再喂 VAD
        if self.sr == 16000:
            blocksize = FRAME_SIZE
        else:
            blocksize = int(round(FRAME_SIZE * self.sr / 16000))

        buf16 = np.zeros(0, dtype=np.float32)
        deadline = time.time() + timeout
        max_samples = int(TARGET_SR * max_utterance_ms / 1000) if max_utterance_ms else 0
        captured = 0

        with sd.InputStream(samplerate=self.sr, channels=1, dtype="float32",
                            blocksize=blocksize, device=self.device_index) as stream:
            while time.time() < deadline:
                block, _overflowed = stream.read(blocksize)
                x = block.flatten().astype(np.float32)
                if self.sr != 16000:
                    x = resample_to_16k(x, self.sr)

                buf16 = np.concatenate([buf16, x])

                while buf16.size >= FRAME_SIZE:
                    frame = buf16[:FRAME_SIZE]
                    buf16 = buf16[FRAME_SIZE:]
                    utt = segmenter.push(frame)
                    if utt is not None:
                        if gain:
                            utt, _ = normalize_gain(utt)
                        return utt.astype(np.float32)

                captured += x.size
                if max_samples and captured >= max_samples:
                    # 说太久 / VAD 没判出句尾：强制收尾，别让 ASR 解几十秒音频
                    break

        # 超时：如果正在说话，强制输出已录到的部分
        tail = segmenter.flush()
        if tail is not None:
            if gain:
                tail, _ = normalize_gain(tail)
            return tail.astype(np.float32)

        return np.zeros(0, dtype=np.float32)

        return np.zeros(0, dtype=np.float32)

    # ---------------------------------------------------------- 输出
    @staticmethod
    def save_wav(path: str | Path, x: np.ndarray, sr: int = TARGET_SR) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = np.clip(x, -1.0, 1.0)
        int16 = (data * 32767).astype(np.int16)
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(int16.tobytes())
        return p

    @staticmethod
    def play(x: np.ndarray, sr: int = TARGET_SR,
             device: int | str | None = None, volume: float = 0.6) -> None:
        idx = devices.resolve_output(device)
        sd.play(np.clip(x * volume, -1.0, 1.0), samplerate=sr, device=idx)
        sd.wait()

    def info(self) -> str:
        return f"{devices.describe(self.device_index)} @ {self.sr}Hz"
