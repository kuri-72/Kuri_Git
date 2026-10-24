"""
小72 · 意图识别层
===================
职责：自然语言 → 结构化意图（dict）。**不生成协议文本。**

为什么这里要做这么重的校验？
因为 LLM 是概率模型。你让它"只输出 JSON"，它 95% 的时候听话，
5% 的时候会给你包一层 ```json、加句"好的"、或者自己发明字段。
这些垃圾如果流到串口，单片机会解析出错误参数。

所以本模块的返回值永远是"已校验的干净 dict"，不是模型原文。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from config import Config, load_system_prompt

VALID_CMDS = {"set_led", "breath", "off", "unknown", "chat"}


@dataclass
class Intent:
    cmd: str
    brightness: int | None = None
    period_ms: int | None = None
    say: str = ""
    raw: str = ""                      # 模型原始输出，仅供调试
    repaired: list[str] = field(default_factory=list)  # 做过哪些修复

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"cmd": self.cmd, "say": self.say}
        if self.brightness is not None:
            d["brightness"] = self.brightness
        if self.period_ms is not None:
            d["period_ms"] = self.period_ms
        return d


class IntentError(RuntimeError):
    """API 调用失败或模型输出无法修复时抛出。"""


# ---------------------------------------------------------------- 修复工具

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
_OBJECT_RE = re.compile(r"\{.*\}", re.S)


def extract_json(text: str) -> dict[str, Any] | None:
    """从任意脏输出里掏出第一个 JSON 对象。掏不出返回 None。"""
    if not text:
        return None
    # 1) 优先取 ``` 代码块里的内容
    m = _FENCE_RE.search(text)
    candidates = [m.group(1)] if m else []
    # 2) 再尝试从全文里截取最外层 {...}
    m2 = _OBJECT_RE.search(text)
    if m2:
        candidates.append(m2.group(0))
    candidates.append(text)

    for cand in candidates:
        cand = cand.strip()
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            # 常见脏点：单引号、尾逗号、中文引号
            fixed = (
                cand.replace("'", '"')
                .replace("，", ",")
                .replace("：", ":")
                .replace("\u201c", '"')
                .replace("\u201d", '"')
            )
            fixed = re.sub(r",\s*([}\]])", r"\1", fixed)  # 去掉尾逗号
            try:
                obj = json.loads(fixed)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    return None


def _clamp(v: Any, lo: int, hi: int, default: int) -> tuple[int, bool]:
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        return default, True
    if n < lo:
        return lo, True
    if n > hi:
        return hi, True
    return n, False


def normalize(obj: dict[str, Any]) -> Intent:
    """把模型的 JSON 规整成可信的 Intent。这是"闸门"的核心。"""
    repaired: list[str] = []

    cmd = str(obj.get("cmd", "")).strip().lower()
    if cmd not in VALID_CMDS:
        # 模型有时会自己发明 cmd（比如 "set_brightness"、"dim"）
        alias = {
            "set_brightness": "set_led", "dim": "set_led", "brighten": "set_led",
            "set": "set_led", "led": "set_led", "turn_off": "off", "close": "off",
            "breathing": "breath", "breathe": "breath",
        }
        cmd = alias.get(cmd, "unknown")
        repaired.append(f"cmd 归一化 → {cmd}")

    say = str(obj.get("say", "")).strip().replace("\n", " ")[:120]

    brightness = None
    period_ms = None

    if cmd in ("set_led", "breath"):
        b, fixed_b = _clamp(obj.get("brightness", 50), 0, 100, 50)
        brightness = b
        if fixed_b:
            repaired.append(f"brightness 限幅 → {b}")
        if cmd == "breath":
            p, fixed_p = _clamp(obj.get("period_ms", 2000), 0, 9999, 2000)
            # 协议只支持 3 位，映射到 50–9990ms 后取整到 10ms
            p = max(50, min(9990, p))
            p = int(round(p / 10.0) * 10)
            period_ms = p
            if fixed_p:
                repaired.append(f"period_ms 限幅 → {p}")
        else:
            period_ms = 0
    elif cmd == "off":
        brightness = 0
        period_ms = 0

    if not say:
        say = {
            "set_led": f"亮度 {brightness}%",
            "breath": f"呼吸模式 {period_ms}ms",
            "off": "已关灯",
            "unknown": "没听懂，试试：调亮/调暗/关灯/呼吸",
            "chat": "嗯，我在听",
        }[cmd]
        repaired.append("say 为空，已补默认话术")

    return Intent(cmd=cmd, brightness=brightness, period_ms=period_ms,
                  say=say, raw="", repaired=repaired)


# ---------------------------------------------------------------- LLM 客户端

class IntentParser:
    """意图识别器。一次构造，多次复用（保持对话上下文可选）。"""

    def __init__(self, cfg: Config | None = None, *, keep_history: bool = False):
        self.cfg = cfg or Config.from_env()
        self.system_prompt = load_system_prompt()
        self.keep_history = keep_history
        self._history: list[dict[str, str]] = []
        self._client = None

    # -- 惰性导入 openai，没装也能用 mock 模式 --
    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not self.cfg.ready:
            raise IntentError(
                "未设置 API key。\n"
                "  方式一（推荐）：在项目根目录建 .env，写一行\n"
                "      X72_API_KEY=sk-你的key\n"
                "      X72_PROVIDER=deepseek\n"
                "  方式二：设置环境变量 X72_API_KEY\n"
                "注意：key 不要贴到任何聊天窗口里。"
            )
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as e:
            raise IntentError(
                "缺少 openai 库。执行：pip install openai"
            ) from e
        self._client = OpenAI(
            api_key=self.cfg.api_key,
            base_url=self.cfg.base_url,
            timeout=self.cfg.timeout,
        )
        return self._client

    def parse(self, user_text: str, context: str | None = None) -> Intent:
        user_text = (user_text or "").strip()
        if not user_text:
            return Intent(cmd="unknown", brightness=None, period_ms=None,
                          say="你还没说话")

        client = self._ensure_client()
        messages: list[dict[str, str]] = [{"role": "system", "content": self.system_prompt}]
        if context:
            messages.append({"role": "system", "content": f"当前设备状态：{context}"})
        if self.keep_history:
            messages.extend(self._history[-6:])
        messages.append({"role": "user", "content": user_text})

        try:
            resp = client.chat.completions.create(
                model=self.cfg.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=self.cfg.temperature,
                max_tokens=200,
            )
        except Exception as e:  # 网络/鉴权/限流，统一包一层
            raise IntentError(f"调用模型失败：{type(e).__name__}: {e}") from e

        content = (resp.choices[0].message.content or "").strip()
        obj = extract_json(content)
        if obj is None:
            raise IntentError(
                "模型输出里找不到 JSON，原文如下（可把这段发我，我改 prompt）：\n"
                f"{content[:500]}"
            )

        intent = normalize(obj)
        intent.raw = content
        if self.keep_history:
            self._history.append({"role": "user", "content": user_text})
            self._history.append({"role": "assistant", "content": json.dumps(intent.as_dict(), ensure_ascii=False)})
        return intent


class MockParser:
    """离线演示/单元测试用。不需要网络和 key。

    注意：这是**规则版**，故意做得很土。它的价值是让整条链路
    在不接 AI 的情况下也能跑通、可回归测试。
    """

    def parse(self, user_text: str, context: str | None = None) -> Intent:
        t = user_text.strip()
        low = t.lower()

        def has(*words: str) -> bool:
            return any(w in t for w in words)

        if not t:
            return Intent(cmd="unknown", say="你还没说话")

        if has("关灯", "关掉", "别亮", "睡觉", "熄灭"):
            return Intent(cmd="off", brightness=0, period_ms=0, say="已关灯")

        if has("机械臂", "摄像头", "舵机"):
            return Intent(cmd="unknown", say="机械臂还没接入，目前只有灯")

        if has("呼吸", "一闪一闪"):
            period = 2000
            if has("快"):
                period = 800
            elif has("慢"):
                period = 4000
            b = 80
            m = re.search(r"(\d{1,3})\s*%?", t)
            if m:
                b = max(0, min(100, int(m.group(1))))
            return Intent(cmd="breath", brightness=b, period_ms=period,
                          say=f"呼吸模式，{period}ms")

        if has("全亮", "最亮"):
            return Intent(cmd="set_led", brightness=100, period_ms=0, say="已调到最亮")

        m = re.search(r"(\d{1,3})\s*%?", t)
        if m and has("调到", "调到百分之", "%", "亮度"):
            b = max(0, min(100, int(m.group(1))))
            return Intent(cmd="set_led", brightness=b, period_ms=0, say=f"亮度 {b}%")

        if has("亮", "刺眼"):
            if has("太亮", "好亮", "刺眼", "暗一点", "暗点"):
                return Intent(cmd="set_led", brightness=40, period_ms=0, say="已调暗")
            return Intent(cmd="set_led", brightness=90, period_ms=0, say="已调亮")

        if has("暗", "看不清"):
            return Intent(cmd="set_led", brightness=80, period_ms=0, say="已调亮")

        return Intent(cmd="unknown", say="没听懂，试试：调亮/调暗/关灯/呼吸")
