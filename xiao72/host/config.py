"""
小72 · 配置
=============
密钥绝不要写进代码、也不要贴进聊天。
放在环境变量里，或者项目根目录的 xiao72/.env 文件里（.env 已在 .gitignore 中）。

支持的 provider（都是 OpenAI 兼容接口，改 base_url + model 即可）：
    - deepseek   https://api.deepseek.com          model: deepseek-chat
    - qwen       https://dashscope.aliyuncs.com/compatible-mode/v1   model: qwen-plus
    - moonshot   https://api.moonshot.cn/v1        model: moonshot-v1-8k
    - openai     https://api.openai.com/v1         model: gpt-4o-mini
    - 本地       http://127.0.0.1:11434/v1         model: qwen2.5:7b （Ollama）
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
ENV_FILE = PROJECT_ROOT / ".env"
PROMPT_FILE = PROJECT_ROOT / "docs" / "intent_prompt.md"

PRESETS: dict[str, tuple[str, str]] = {
    "deepseek": ("https://api.deepseek.com", "deepseek-chat"),
    "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    "moonshot": ("https://api.moonshot.cn/v1", "moonshot-v1-8k"),
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "ollama": ("http://127.0.0.1:11434/v1", "qwen2.5:7b"),
}


def load_dotenv(path: Path = ENV_FILE) -> None:
    """极简 .env 读取，不依赖第三方库。已存在的环境变量优先，不覆盖。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


@dataclass
class Config:
    provider: str
    base_url: str
    model: str
    api_key: str
    timeout: float
    temperature: float

    @property
    def ready(self) -> bool:
        return bool(self.api_key)

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        provider = os.environ.get("X72_PROVIDER", "deepseek").strip().lower()
        default_base, default_model = PRESETS.get(provider, PRESETS["deepseek"])
        return cls(
            provider=provider,
            base_url=os.environ.get("X72_BASE_URL", default_base).strip(),
            model=os.environ.get("X72_MODEL", default_model).strip(),
            api_key=os.environ.get("X72_API_KEY", "").strip(),
            timeout=float(os.environ.get("X72_TIMEOUT", "20")),
            # 意图识别要稳定，温度调低；0 也不错，但部分厂商不推荐，用 0.1
            temperature=float(os.environ.get("X72_TEMPERATURE", "0.1")),
        )

    def masked_key(self) -> str:
        if not self.api_key:
            return "(未设置)"
        if len(self.api_key) <= 8:
            return "****"
        return f"{self.api_key[:4]}...{self.api_key[-4:]}"


def load_system_prompt(path: Path = PROMPT_FILE) -> str:
    """读取意图识别 prompt。文件不存在时抛清晰错误，而不是静默用错 prompt。"""
    if not path.exists():
        raise FileNotFoundError(
            f"找不到 prompt 文件：{path}\n"
            f"请确认 docs/intent_prompt.md 存在（这是意图识别层的核心资产）。"
        )
    return path.read_text(encoding="utf-8")
