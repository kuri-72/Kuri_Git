"""语音识别层"""

from .base import AsrProvider, AsrResult
from .faster_whisper_provider import FasterWhisperProvider, MockAsrProvider

_PROVIDERS = {
    "faster-whisper": FasterWhisperProvider,
    "mock": MockAsrProvider,
}


def create_provider(kind: str = "faster-whisper", **kwargs) -> AsrProvider:
    """工厂：按名字创建 ASR 后端。

    以后加 FunASR 只需在 _PROVIDERS 里注册一行。
    """
    cls = _PROVIDERS.get(kind)
    if cls is None:
        raise ValueError(f"未知的 ASR 后端 {kind!r}，可选：{list(_PROVIDERS)}")
    return cls(**kwargs)  # type: ignore[return-value]


__all__ = [
    "AsrProvider",
    "AsrResult",
    "FasterWhisperProvider",
    "MockAsrProvider",
    "create_provider",
]
