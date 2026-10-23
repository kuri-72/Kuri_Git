"""
小72 · 状态合并 + 协议编解码（PC 侧）
========================================
这一层是整套东西的"确定性核心"：
    意图（可能错） + 当前状态 → 完整状态帧（每次都一样）

支持两种输出格式（与 firmware/x72_proto.c 一一对应）：
    format="frame"  →  [L00502000|A---|]        （PC 自动发送用，紧凑）
    format="json"   →  {"led":50,"period":2000} （手敲调试用，好读）

三条必须守住的行为：
  1. unknown 不改变任何状态（"没听懂"绝不能把灯关掉）
  2. 每次发**全量状态**，不是增量命令（幂等，丢帧不会累积错误）
  3. 数值一律限幅，永远不产生非法帧
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

HEADER = "["
TAIL = "]"
SEP = "|"
ARM_PLACEHOLDER = "A---"          # 本版不实现机械臂，固定占位

BRIGHT_MIN, BRIGHT_MAX = 0, 100
PERIOD_MIN_MS, PERIOD_MAX_MS = 0, 9999   # 4 位，单位 ms

FORMAT_FRAME = "frame"
FORMAT_JSON = "json"


def _as_int(v, default: int) -> int:
    """严格整数解析：接受 int/float/数字字符串，其他一律回退默认值。

    不用 int() 直转，是因为 int("abc") 抛异常、int(None) 也抛异常，
    而 float("nan") 转 int 会给出未定义值。宁可显式回退。
    """
    try:
        if isinstance(v, bool):
            return default
        n = float(v)
        if n != n or n in (float("inf"), float("-inf")):   # NaN / Inf
            return default
        return int(round(n))
    except (TypeError, ValueError):
        return default


def clamp(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else hi if v > hi else v


@dataclass
class LedState:
    """LED 的完整状态。单片机侧对应同一组变量。"""
    brightness: int = 0      # 0–100
    period_ms: int = 0       # 0 = 常亮；>0 = 呼吸周期
    extra: str = ""          # 保留段，留给未来的设备

    # ------------------------------------------------------------ 合并
    def apply(self, cmd: str, brightness: int | None, period_ms: int | None) -> list[str]:
        """把意图合并进状态，返回"真正变化的字段名"。"""
        changed: list[str] = []
        if cmd == "unknown":
            return changed                       # ★ 不改变任何东西

        if cmd == "off":
            if self.brightness != 0:
                self.brightness = 0
                changed.append("brightness")
            if self.period_ms != 0:
                self.period_ms = 0
                changed.append("period_ms")
            return changed

        if cmd in ("set_led", "breath"):
            new_b = clamp(_as_int(brightness, self.brightness), BRIGHT_MIN, BRIGHT_MAX)
            if new_b != self.brightness:
                self.brightness = new_b
                changed.append("brightness")

            new_p = 0 if cmd == "set_led" else clamp(
                _as_int(period_ms, self.period_ms),
                PERIOD_MIN_MS, PERIOD_MAX_MS)
            if new_p != self.period_ms:
                self.period_ms = new_p
                changed.append("period_ms")
        return changed

    # ------------------------------------------------------------ 编码
    def encode(self, fmt: str = FORMAT_FRAME) -> str:
        """全量状态 → 一行文本（格式由 fmt 决定）。"""
        b = clamp(self.brightness, BRIGHT_MIN, BRIGHT_MAX)
        p = clamp(int(self.period_ms), PERIOD_MIN_MS, PERIOD_MAX_MS)

        if fmt == FORMAT_JSON:
            # 字段顺序固定，方便人读；C 端其实支持任意顺序
            return json.dumps({"led": b, "period": p}, separators=(",", ":"))

        extra = "".join(ch for ch in self.extra if ch not in "[]\r\n|")
        return f"{HEADER}L{b:04d}{p:04d}{SEP}{ARM_PLACEHOLDER}{SEP}{extra}{TAIL}"

    def to_dict(self) -> dict:
        return {"brightness": self.brightness, "period_ms": self.period_ms,
                "extra": self.extra}


# ---------------------------------------------------------------- 解码（与 C 同规则）

@dataclass
class ParseResult:
    ok: bool
    state: dict | None = None
    error: str = ""
    notes: list[str] = field(default_factory=list)


def decode_frame(s: str) -> ParseResult:
    """解析紧凑帧，行为必须与 firmware/x72_proto.c 的 parse_frame 一致。"""
    notes: list[str] = []

    i, j = s.find(HEADER), s.rfind(TAIL)
    if i < 0:
        return ParseResult(False, error="FRAME: 缺少帧头 '['")
    body = s[i + 1:j] if j > i else s[i + 1:]

    parts = body.split(SEP)
    if len(parts) < 2:
        return ParseResult(False, error="FRAME: 段数不足（至少要 灯段+臂段）")

    led = parts[0]
    if len(led) != 9 or led[0] != "L":
        return ParseResult(False, error="FRAME: 灯段必须是 L + 8 位数字")
    b_raw, p_raw = led[1:5], led[5:9]
    if not (b_raw.isdigit() and p_raw.isdigit()):
        return ParseResult(False, error="FRAME: 亮度/周期必须是数字")

    brightness = int(b_raw)
    period_ms = int(p_raw)
    if brightness > BRIGHT_MAX:
        notes.append(f"CLAMPED: brightness {brightness} → {BRIGHT_MAX}")
        brightness = BRIGHT_MAX
    if period_ms > PERIOD_MAX_MS:
        notes.append(f"CLAMPED: period_ms {period_ms} → {PERIOD_MAX_MS}")
        period_ms = PERIOD_MAX_MS

    arm = parts[1]
    if arm and arm[0] != "A":
        return ParseResult(False, error="FRAME: 臂段格式错误，应为 A---")

    extra = SEP.join(parts[2:]) if len(parts) > 2 else ""
    return ParseResult(True, state={
        "brightness": brightness,
        "period_ms": period_ms,
        "extra": extra,
    }, notes=notes)


def decode_json(s: str) -> ParseResult:
    """解析 JSON，行为与 firmware/x72_proto.c 的 parse_json 一致。

    缺字段 = 保持不变。这里为了"能返回完整状态"，缺字段填 -1 表示"未指定"。
    """
    notes: list[str] = []
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return ParseResult(False, error="JSON: 缺少 { 或 }")
    try:
        obj = json.loads(s[i:j + 1])
    except json.JSONDecodeError as e:
        return ParseResult(False, error=f"JSON: {e}")
    if not isinstance(obj, dict):
        return ParseResult(False, error="JSON: 顶层必须是对象")

    have_led = "led" in obj
    have_period = "period" in obj
    if not have_led and not have_period:
        return ParseResult(False, error="JSON: 没有已知字段（led / period）")

    brightness = -1
    period_ms = -1
    if have_led:
        brightness = clamp(_as_int(obj["led"], 0), BRIGHT_MIN, BRIGHT_MAX)
        if brightness != _as_int(obj["led"], 0):
            notes.append(f"CLAMPED: led → {brightness}")
    if have_period:
        period_ms = clamp(_as_int(obj["period"], 0), PERIOD_MIN_MS, PERIOD_MAX_MS)

    return ParseResult(True, state={
        "brightness": brightness,
        "period_ms": period_ms,
        "extra": "",
    }, notes=notes)


def decode(text: str) -> ParseResult:
    """自动判断格式。行为与 C 的 dispatch_line 一致：先找 '[' 再找 '{'。"""
    i_bracket = text.find("[")
    i_brace = text.find("{")
    if i_bracket >= 0 and (i_brace < 0 or i_bracket < i_brace):
        return decode_frame(text)
    if i_brace >= 0:
        return decode_json(text)
    return ParseResult(False, error="格式不对：既不是紧凑帧也不是 JSON")
