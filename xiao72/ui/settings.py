"""UI 设置：单独一份 settings.json，不进 git、不跨设备同步。

优先级：settings.json > .env > 代码默认。

v1 只存三项（语速 / 音色 / 音量），但文件结构留了扩展位。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULTS = {
    "tts_rate": "+50%",
    "tts_voice": "zh-CN-XiaoxiaoNeural",
    "tts_volume": "+0%",
}

# 常用中文音色（下拉用）
VOICES = [
    {"id": "zh-CN-XiaoxiaoNeural", "name": "晓晓 · 女声温柔"},
    {"id": "zh-CN-XiaoyiNeural", "name": "晓伊 · 女声活泼"},
    {"id": "zh-CN-YunxiNeural", "name": "云希 · 男声年轻"},
    {"id": "zh-CN-YunyangNeural", "name": "云扬 · 男声播音"},
    {"id": "zh-CN-YunjianNeural", "name": "云健 · 男声浑厚"},
]

RATE_MIN, RATE_MAX = -50, 100


def settings_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = Path(base) / "xiao72"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d / "settings.json"


def load() -> dict:
    """读 settings.json，缺失的键用默认值补。"""
    data = dict(DEFAULTS)
    p = settings_path()
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data.update({k: v for k, v in raw.items() if k in DEFAULTS})
        except Exception:
            pass
    return data


def save(patch: dict) -> dict:
    """合并写入，返回完整配置。值非法就忽略该键。"""
    data = load()
    if "tts_rate" in patch:
        try:
            n = int(str(patch["tts_rate"]).replace("%", "").replace("+", ""))
            n = max(RATE_MIN, min(RATE_MAX, n))
            data["tts_rate"] = ("+" if n >= 0 else "") + "%d%%" % n
        except Exception:
            pass
    if "tts_voice" in patch:
        v = str(patch["tts_voice"]).strip()
        if v:
            data["tts_voice"] = v
    if "tts_volume" in patch:
        try:
            n = int(str(patch["tts_volume"]).replace("%", "").replace("+", ""))
            n = max(-50, min(50, n))
            data["tts_volume"] = ("+" if n >= 0 else "") + "%d%%" % n
        except Exception:
            pass

    p = settings_path()
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def rate_to_percent(v: str) -> int:
    try:
        return int(str(v).replace("%", "").replace("+", ""))
    except Exception:
        return 50


def percent_to_rate(n: int) -> str:
    n = max(RATE_MIN, min(RATE_MAX, int(n)))
    return ("+" if n >= 0 else "") + "%d%%" % n
