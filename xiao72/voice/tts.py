"""TTS（文字转语音）层：引擎与音色分离，全部配置驱动。

换音色 = 改 .env 一行，不动代码。

    引擎（怎么合成）   edge  = 微软在线，音色自然（默认）
                       sapi  = Windows 离线，机械音（需系统装有中文语音）
    音色（哪个嗓子）   zh-CN-XiaoxiaoNeural / zh-CN-YunxiNeural / ...
    语速 / 音量        +0% / -10% 这类百分比

设计约束
--------
1. **不能拖慢对话**：先合成再播放，播放期间主循环阻塞；失败立即降级，不重试。
2. **同一句话不重复请求**：按 (文本, 音色, 语速) 做 key 缓存 wav。
3. **失败不抛异常**：TTS 是锦上添花，坏了也不能让语音链路崩。
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"


# ---------------------------------------------------------------- 配置

@dataclass
class TtsConfig:
    engine: str = "edge"          # edge | sapi | none
    voice: str = DEFAULT_VOICE
    rate: str = "+0%"             # 语速，如 +10% / -10%
    volume: str = "+0%"           # 音量
    enabled: bool = True

    @classmethod
    def from_env(cls) -> "TtsConfig":
        mute = os.environ.get("X72_TTS_MUTE", "0").strip().lower()
        return cls(
            engine=os.environ.get("X72_TTS_ENGINE", "edge").strip().lower(),
            voice=os.environ.get("X72_TTS_VOICE", DEFAULT_VOICE).strip() or DEFAULT_VOICE,
            rate=os.environ.get("X72_TTS_RATE", "+0%").strip() or "+0%",
            volume=os.environ.get("X72_TTS_VOLUME", "+0%").strip() or "+0%",
            enabled=mute not in ("1", "true", "yes", "on"),
        )

    def describe(self) -> str:
        if not self.enabled:
            return "关闭（--mute 或 X72_TTS_MUTE=1）"
        return "%s / %s / rate %s" % (self.engine, self.voice, self.rate)


def cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = Path(base) / "xiao72" / "tts_cache"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


# ---------------------------------------------------------------- 引擎

class BaseEngine:
    name = "base"

    def available(self) -> bool:
        return False

    def synth(self, text: str):
        """返回 (samples: np.ndarray float32, samplerate: int)，失败返回 None。"""
        raise NotImplementedError


class EdgeEngine(BaseEngine):
    """微软在线 TTS。需要 edge-tts + soundfile（用来解 mp3）。"""

    name = "edge"

    def __init__(self, voice: str, rate: str = "+0%", volume: str = "+0%"):
        self.voice = voice
        self.rate = rate
        self.volume = volume

    def available(self) -> bool:
        try:
            import edge_tts  # noqa: F401
            import soundfile  # noqa: F401
        except ImportError:
            return False
        return True

    async def _fetch(self, text: str) -> bytes:
        import edge_tts
        buf = bytearray()
        comm = edge_tts.Communicate(
            text, self.voice, rate=self.rate, volume=self.volume,
        )
        async for chunk in comm.stream():
            if chunk.get("type") == "audio":
                buf.extend(chunk["data"])
        return bytes(buf)

    def synth(self, text: str):
        try:
            import soundfile as sf
            import numpy as np
        except ImportError:
            return None
        try:
            mp3 = asyncio.run(self._fetch(text))
        except Exception:
            return None
        if not mp3:
            return None
        try:
            data, sr = sf.read(io.BytesIO(mp3), dtype="float32")
            return np.asarray(data, dtype="float32"), int(sr)
        except Exception:
            return None


class SapiEngine(BaseEngine):
    """Windows 离线语音（System.Speech）。

    注意：**必须系统装有中文语音**才读得对，否则会用英文嗓子念中文。
    装法：设置 → 时间和语言 → 语音 → 添加语音 → 中文（简体）。
    这里通过 PowerShell 调用，避免引入 pywin32。
    """

    name = "sapi"

    def available(self) -> bool:
        return sys.platform.startswith("win")

    def synth(self, text: str):
        # SAPI 直接播报，不走 wav 缓存
        safe = text.replace("'", "''")
        cmd = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.Rate = 0; "
            "$s.Speak('%s'); "
            "$s.Dispose()" % safe
        )
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                timeout=120, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return "played"
        except Exception:
            return None


class NullEngine(BaseEngine):
    name = "none"

    def available(self) -> bool:
        return True

    def synth(self, text: str):
        return None


def make_engine(cfg: TtsConfig) -> BaseEngine:
    if cfg.engine == "sapi":
        return SapiEngine()
    if cfg.engine in ("edge", "auto", ""):
        return EdgeEngine(cfg.voice, cfg.rate, cfg.volume)
    return NullEngine()


# ---------------------------------------------------------------- 服务

class TtsService:
    """对外只暴露 speak(text)。"""

    def __init__(self, cfg: TtsConfig | None = None):
        self.cfg = cfg or TtsConfig.from_env()
        self.engine = make_engine(self.cfg)
        self._sd = None
        self.last_error = ""

    # -- 播放 --
    def _ensure_audio_out(self) -> bool:
        if self._sd is not None:
            return True
        try:
            import sounddevice as sd
        except ImportError:
            self.last_error = "缺 sounddevice，无法播放"
            return False
        self._sd = sd
        return True

    def _play(self, data, sr: int) -> bool:
        if not self._ensure_audio_out():
            return False
        try:
            self._sd.play(data, sr)
            self._sd.wait()
            return True
        except Exception as e:
            self.last_error = f"播放失败：{e}"
            return False

    # -- 缓存 --
    def _cache_path(self, text: str) -> Path:
        key = "%s|%s|%s" % (text, self.cfg.voice, self.cfg.rate)
        h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        return cache_dir() / ("%s.wav" % h)

    def _load_cache(self, path: Path):
        try:
            import soundfile as sf
            data, sr = sf.read(str(path), dtype="float32")
            return data, int(sr)
        except Exception:
            return None

    def _save_cache(self, path: Path, data, sr: int) -> None:
        try:
            import soundfile as sf
            sf.write(str(path), data, sr, format="WAV")
        except Exception:
            pass

    # -- 对外 --
    def speak(self, text: str) -> bool:
        """合成并播放。成功返回 True；任何失败都静默返回 False。"""
        text = (text or "").strip()
        if not text or not self.cfg.enabled:
            return False
        if not self.engine.available():
            if self.cfg.engine != "sapi":
                self.last_error = f"引擎 {self.cfg.engine} 不可用（缺依赖）"
            return False

        # sapi 自己会播，不缓存
        if self.engine.name == "sapi":
            return self.engine.synth(text) == "played"

        path = self._cache_path(text)
        cached = self._load_cache(path) if path.exists() else None
        if cached is not None:
            return self._play(cached[0], cached[1])

        out = self.engine.synth(text)
        if out is None:
            # edge 失败 → 退 sapi（若可用）
            if self.cfg.engine != "sapi":
                alt = SapiEngine()
                if alt.available() and alt.synth(text) == "played":
                    self.last_error = "edge 失败，已降级到 sapi"
                    return True
            self.last_error = "合成失败（网络或引擎问题）"
            return False

        data, sr = out
        self._save_cache(path, data, sr)
        return self._play(data, sr)

    def close(self) -> None:
        try:
            if self._sd is not None:
                self._sd.stop()
        except Exception:
            pass
