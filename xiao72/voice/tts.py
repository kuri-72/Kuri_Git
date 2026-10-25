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
import time
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


import re

_SENT_END = re.compile(r'(?<=[。！？!?；;\n])')


def split_text(text: str, max_len: int = 40) -> list:
    """按标点切句，过长再硬切。用于「边合成边播」。"""
    text = (text or "").strip()
    if not text:
        return []

    parts = [p.strip() for p in _SENT_END.split(text) if p.strip()]

    out, buf = [], ""
    for p in parts:
        # 单句超长：按逗号再分，仍超长就硬切
        while len(p) > max_len:
            cut = p.rfind("，", 0, max_len)
            if cut <= 0:
                cut = max_len
            head, p = p[:cut + 1], p[cut + 1:]
            if head.strip():
                out.append(head.strip())
            p = p.strip()
        if not p:
            continue
        if len(buf) + len(p) <= max_len:
            buf += p
        else:
            if buf:
                out.append(buf)
            buf = p
    if buf:
        out.append(buf)
    return out or [text]


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
        # 单线程池：合成在后台跑，主线程可以先把文字发出去
        from concurrent.futures import ThreadPoolExecutor
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tts")

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

    def apply_config(self, voice=None, rate=None, volume=None) -> None:
        """热切换音色/语速/音量：只重建引擎，不重启进程。"""
        if voice:
            self.cfg.voice = str(voice)
        if rate:
            self.cfg.rate = str(rate)
        if volume:
            self.cfg.volume = str(volume)
        self.engine = make_engine(self.cfg)

    def _play(self, data, sr: int, stop_event=None) -> bool:
        if not self._ensure_audio_out():
            return False
        try:
            self._sd.play(data, sr)
        except Exception as e:
            self.last_error = f"播放失败：{e}"
            return False

        dur = float(len(data)) / float(sr or 24000)
        t0 = time.time()
        while time.time() - t0 < dur + 0.3:
            if stop_event is not None and stop_event.is_set():
                try:
                    self._sd.stop()
                except Exception:
                    pass
                return False
            try:
                stream = self._sd.get_stream()
                if stream is None or not stream.active:
                    return True
            except Exception:
                pass
            time.sleep(0.05)
        return True

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

    # -- 分句流水线 --
    def prepare_chunks(self, text: str, max_len: int = 40):
        """把长句切成短句，逐句提交后台合成。

        返回 [(句子, future), ...]。第一句合成完就能开播，
        后面的在播放期间继续合成，避免「等整段合成完」的空白。
        """
        if not text or not self.cfg.enabled:
            return []
        return [(c, self._pool.submit(self._synth_or_cached, c))
                for c in split_text(text, max_len)]

    def play_chunks(self, items, stop_event=None) -> int:
        """按顺序播放；每句就绪即播。返回成功播出的句数。"""
        n = 0
        for _, job in items:
            if stop_event is not None and stop_event.is_set():
                break
            if self.play(job, stop_event):
                n += 1
        return n

    # -- 对外 --
    def prepare(self, text: str):
        """后台开始合成，立刻返回 future。UI 可以先把文字打出来，声音随后到。

        返回 None 表示这句不需要发声（静音 / 空文本）。
        """
        text = (text or "").strip()
        if not text or not self.cfg.enabled:
            return None
        return self._pool.submit(self._synth_or_cached, text)

    def _synth_or_cached(self, text: str):
        if not self.engine.available():
            if self.cfg.engine != "sapi":
                self.last_error = f"引擎 {self.cfg.engine} 不可用（缺依赖）"
            return None

        # sapi 自己会播，不缓存
        if self.engine.name == "sapi":
            return ("sapi", text)

        path = self._cache_path(text)
        if path.exists():
            cached = self._load_cache(path)
            if cached is not None:
                return ("audio", cached[0], cached[1])

        out = self.engine.synth(text)
        if out is None:
            if self.cfg.engine != "sapi":
                self.last_error = "edge 合成失败"
            return None
        data, sr = out
        self._save_cache(path, data, sr)
        return ("audio", data, sr)

    def play(self, job, stop_event=None) -> bool:
        """等 prepare 的结果并播放。stop_event 被 set 时立刻停声。"""
        if job is None:
            return False
        try:
            out = job.result(timeout=30)
        except Exception:
            return False
        if out is None:
            # edge 失败 → 退 sapi（若可用）
            if self.cfg.engine != "sapi":
                alt = SapiEngine()
                if alt.available():
                    self.last_error = "edge 失败，已降级到 sapi"
                    return alt.synth(str(getattr(job, "_text", ""))) == "played"
            return False

        if isinstance(out, tuple) and out and out[0] == "sapi":
            return self.engine.synth(out[1]) == "played"
        if isinstance(out, tuple) and out and out[0] == "audio":
            return self._play(out[1], out[2], stop_event)
        return False

    def speak(self, text: str, stop_event=None) -> bool:
        """合成 + 播放（同步版，给没有 UI 的场景用）。"""
        return self.play(self.prepare(text), stop_event)

    def close(self) -> None:
        try:
            if self._sd is not None:
                self._sd.stop()
        except Exception:
            pass
        try:
            self._pool.shutdown(wait=False)
        except Exception:
            pass
