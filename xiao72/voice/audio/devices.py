"""
小72 · 音频设备管理
=====================
设计原则：
  1. **默认跟随系统**：不指定设备时，从 Windows 当前默认输入/输出出发，
     自动找到同一物理设备下"真正能收到声音"的接口组合。
  2. **可显式切换**：支持按索引、按名称片段指定。
  3. **必须做活体探测**：同一个麦克风在 Windows 里会以多个接口暴露
     （MME / DirectSound / WASAPI / WDM-KS），**其中一部分可能是死的**。

为什么要探测（实测证据）：
    设备 ROG DELTA II：
      MME        @44100/16000  →  -96.7 dBFS（纯零，等于没声音）
      DirectSound@44100        →  -75.3 dBFS（极弱）
      DirectSound@16000        →  -96.7 dBFS
      WASAPI     @16000        →  -141.5 dBFS（纯零）
      WDM-KS     @16000        →  -31.0 dBFS  peak=0.14  ← 真正可用
    如果按"系统默认设备"直接用 MME 那一路，会永远录到静音，
    而使用者会误以为是 ASR 坏了。

    另：Pico 头显麦克风能打开、能录，但永远 -96.7 dBFS，属于"虚拟死设备"。
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import sounddevice as sd

# 判定"该组合没有可用数据"的阈值（RMS，dBFS）。
#
# 实测教训（ROG DELTA II，同一个 MME 设备索引）：
#     @48000Hz → -44.3 dBFS  ✅ 有环境噪声，可用
#     @44100Hz → -96.7 dBFS  ❌ 只剩 1 位噪声，等于静音
#     @16000Hz → -96.7 dBFS  ❌ 同上
#   也就是说：**同一个设备的不同采样率，有的能用有的不能用**，
#   而且差别不是"增益小"，是"完全没数据"（1 LSB ≈ -96 dB）。
#
#   所以不能只信"原生采样率"，必须逐个试，选第一个真正有数据的。
#   -90 dBFS 能把"1 位噪声"和"真实环境噪声（通常 -60~-45）"分开。
DEAD_DEVICE_DBFS = -90.0

# 说话时"信号够用"的经验阈值（仅用于给出提示，不作为失败条件）
WEAK_SIGNAL_DBFS = -75.0

_PROBE_CACHE: dict[str, tuple[int, int]] = {}


@dataclass
class DeviceInfo:
    index: int
    name: str
    hostapi: str
    max_input_channels: int
    max_output_channels: int
    default_samplerate: float

    def __str__(self) -> str:
        kinds = []
        if self.max_input_channels > 0:
            kinds.append(f"IN×{self.max_input_channels}")
        if self.max_output_channels > 0:
            kinds.append(f"OUT×{self.max_output_channels}")
        return f"[{self.index:2d}] {self.name:<42} {','.join(kinds):<10} {self.hostapi}"


def _to_info(i: int, d: dict) -> DeviceInfo:
    api = sd.query_hostapis(d["hostapi"])
    return DeviceInfo(
        index=i,
        name=d["name"],
        hostapi=api["name"],
        max_input_channels=d["max_input_channels"],
        max_output_channels=d["max_output_channels"],
        default_samplerate=d["default_samplerate"],
    )


def list_inputs() -> list[DeviceInfo]:
    return [_to_info(i, d) for i, d in enumerate(sd.query_devices())
            if d["max_input_channels"] > 0]


def list_outputs() -> list[DeviceInfo]:
    return [_to_info(i, d) for i, d in enumerate(sd.query_devices())
            if d["max_output_channels"] > 0]


def system_default_input() -> int:
    return sd.default.device[0]


def system_default_output() -> int:
    return sd.default.device[1]


def describe(index: int) -> str:
    d = sd.query_devices(index)
    api = sd.query_hostapis(d["hostapi"])["name"]
    return f"[{index}] {d['name']} ({api})"


# ================================================================
#  活体探测
# ================================================================
def measure_rms(index: int, sr: int, duration: float = 0.7,
                trim_head: float = 0.25,
                retries: int = 2, gap: float = 0.12) -> tuple[bool, float]:
    """录一小段并返回 (能否打开, RMS dBFS)。

    **关键：必须掐掉录音开头。**

    实测：每次 sd.rec 开始后的前约 0.2~0.3 秒是空的（设备唤醒 / 流准备）。
    用 0.35 秒测量时几乎整段都是静音，结果恒为 -96.7 dBFS，
    会误判成"设备没数据"；用 0.5 秒以上才测到真实的 -53 dBFS。

    所以：录 duration 秒，丢弃前 trim_head 秒，只对剩余部分算 RMS。
    另外对"1 位噪声"结果做重试，因为偶尔会碰上整段静音。
    """
    last_db = -999.0
    opened = False
    keep_from = max(0, int(trim_head * sr))

    for attempt in range(retries + 1):
        try:
            d = sd.query_devices(index)
            ch = max(1, min(1, d["max_input_channels"]))
            a = sd.rec(int(duration * sr), samplerate=sr, channels=ch,
                       dtype="float32", device=index, blocking=True)
        except Exception:
            return opened, last_db if opened else -999.0

        opened = True
        x = a.flatten()
        if len(x) > keep_from + int(sr * 0.05):
            x = x[keep_from:]              # 掐掉开头的空白
        rms = float(np.sqrt(np.mean(x ** 2)))
        last_db = 20 * np.log10(rms + 1e-12)

        if last_db > DEAD_DEVICE_DBFS:
            return True, last_db          # 有数据，直接用

        if attempt < retries:
            time.sleep(gap)               # 等一下再试

    return opened, last_db


def is_dead_signal(x: np.ndarray) -> bool:
    """判断这段音频是不是"没数据"（设备在该采样率下静默失效）。

    不是"电平低"，而是"只剩 1 位噪声"。真实麦克风即使没人说话，
    也会收到环境噪声（通常 -60 ~ -45 dBFS）。
    """
    if x.size == 0:
        return True
    rms = float(np.sqrt(np.mean(x ** 2)))
    db = 20 * np.log10(rms + 1e-12)
    return db < DEAD_DEVICE_DBFS


def probe_candidates(name_hint: str | None = None,
                     duration: float = 0.6,
                     verbose: bool = False) -> list[dict]:
    """遍历同类设备的接口/采样率组合，返回**非数字静音**的那些（按电平降序）。

    ⚠ 注意：本函数在"没人说话"时测量的电平只能反映噪声底，
    不能代表麦克风好坏。要评估真实拾音效果，必须让人说话再测。
    它只用于筛掉"完全没数据"的接口。
    """
    if name_hint is None:
        try:
            name_hint = sd.query_devices(system_default_input())["name"]
        except Exception:
            name_hint = None

    hint = (name_hint or "").lower()
    cands = [d for d in list_inputs() if hint and hint in d.name.lower()]
    if not cands:
        cands = [d for d in list_inputs() if d.index == system_default_input()]

    results: list[dict] = []
    for d in cands:
        rates = {int(d.default_samplerate), 16000, 48000}
        for sr in sorted(rates):
            ok, db = measure_rms(d.index, sr, duration)
            if verbose:
                print(f"      探测 [{d.index:2d}] {d.hostapi:<16} @{sr:>5}Hz  "
                      f"{'RMS=' + format(db, '+6.1f') if ok else '打开失败'}")
            if ok and db > DEAD_DEVICE_DBFS:
                results.append({
                    "index": d.index, "name": d.name, "hostapi": d.hostapi,
                    "sr": sr, "db": db,
                })

    results.sort(key=lambda r: r["db"], reverse=True)
    return results


def pick_input(selector: int | str | None = None,
               verbose: bool = False) -> tuple[int, int]:
    """决定用哪个 (设备索引, 采样率)。

    **策略：尊重系统默认，不擅自换设备。**

    为什么不做"自动挑电平最高的"：
      实测 ROG 耳机麦克风在安静时 -96 dBFS、说话时 -75 dBFS，
      而内置 Realtek 阵列安静时就有 -53 dBFS（风扇噪声所以更高）。
      按"电平最高"自动挑，会把你特意选的耳机换成内置麦克风——
      噪音更大、也不是你要的设备。

    所以：
      1. selector 为空 → 用系统默认输入，原生采样率
      2. selector 指定 → 用它
      3. 只有真正录不到数据（数字零）时，才由 Recorder 触发回退
    """
    if selector is None or selector == "":
        idx = system_default_input()
    else:
        idx = resolve_input(selector)

    try:
        native = int(sd.query_devices(idx)["default_samplerate"])
    except Exception:
        native = 48000

    # ★ 逐个采样率验证：同一个设备的不同采样率可能"有的有数据、有的没数据"。
    # 顺序：48k → 44.1k → 16k → 原生（去重）。
    # 48k/44.1k 靠前是因为 Windows 共享模式混音器通常跑这两个率，
    # 非混音率（如 16k）容易静默失效。
    tried: list[int] = []
    for sr in (48000, 44100, 16000, native):
        if sr in tried:
            continue
        tried.append(sr)
        ok, db = measure_rms(idx, sr, 0.7)
        if ok and db > DEAD_DEVICE_DBFS:
            if verbose:
                print(f"  选定 {describe(idx)} @ {sr}Hz (RMS {db:+.1f} dBFS)")
            return idx, sr

    # 该设备所有采样率都无数据 → 回退到同名设备的其它接口
    if verbose:
        print(f"  {describe(idx)} 所有采样率均无数据，尝试回退…")
    try:
        name = sd.query_devices(idx)["name"]
    except Exception:
        name = ""
    for r in probe_candidates(name if name else None, duration=0.35):
        if verbose:
            print(f"  回退到 [{r['index']}] {r['hostapi']} @{r['sr']}Hz (RMS {r['db']:+.1f})")
        return r["index"], r["sr"]

    if verbose:
        print(f"  [!] 没有找到可用组合，暂用 {describe(idx)} @ {native}Hz")
    return idx, native


def find_alternatives(device_index: int, duration: float = 0.4) -> list[dict]:
    """列出与该设备同名的其它可用接口组合，供录音静音时回退。"""
    try:
        name = sd.query_devices(device_index)["name"]
    except Exception:
        return []
    return probe_candidates(name, duration=duration)


def stability_check(index: int, sr: int, duration: float = 3.0,
                    trim_head: float = 0.8,
                    window: float = 0.1) -> dict:
    """在**一条连续流**内评估信号质量。

    为什么改成连续流：
      早期版本是"反复打开/关闭设备各测 0.8 秒"，结果耳机被判为不稳定
      （-54.8 / -38.2 / -86.5）。但连续录 20 秒复测，掉音窗口仅 2.5%，
      且全部集中在开头 0.3 秒——那是流启动空白，不是设备缺陷。
      反复开关会放大这个空白，从而得出错误结论。

    所以：开一条流录 duration 秒，掐掉开头，按 window 切窗口，
    统计"无数据窗口"比例。
    """
    try:
        d = sd.query_devices(index)
        ch = max(1, min(1, d["max_input_channels"]))
        a = sd.rec(int(duration * sr), samplerate=sr, channels=ch,
                   dtype="float32", device=index, blocking=True)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "stable": False,
                "dead_ratio": 1.0, "median": -999.0, "peak": -999.0,
                "values": [], "windows": 0}

    x = a.flatten()
    keep = int(trim_head * sr)
    if len(x) > keep + int(sr * 0.2):
        x = x[keep:]

    n = max(1, int(window * sr))
    w = len(x) // n
    db = []
    for i in range(w):
        seg = x[i * n:(i + 1) * n]
        r = float(np.sqrt(np.mean(seg ** 2)))
        db.append(20 * np.log10(r + 1e-12))

    arr = np.array(db) if db else np.array([-999.0])
    dead_ratio = float(np.mean(arr < DEAD_DEVICE_DBFS))
    median = float(np.median(arr))
    peak = float(arr.max())

    # 判定：无数据窗口 < 10%，且中位数确实在持续出数据
    stable = dead_ratio < 0.10 and median > -85.0

    step = max(1, len(arr) // 20)
    return {
        "values": [round(float(v), 1) for v in arr[::step]],
        "dead_ratio": dead_ratio,
        "median": median,
        "peak": peak,
        "windows": w,
        "stable": stable,
    }


def resolve_input(selector: int | str | None) -> int:
    """把选择器解析成设备索引（不探测，仅解析）。

    None / "" → 系统默认输入
    int       → 直接索引
    "DELTA"   → 名称片段模糊匹配
    """
    if selector is None or selector == "":
        return system_default_input()

    if isinstance(selector, int):
        idx = selector
        if not (0 <= idx < len(sd.query_devices())):
            raise ValueError(f"设备索引 {idx} 超出范围")
        if sd.query_devices(idx)["max_input_channels"] <= 0:
            raise ValueError(f"设备 [{idx}] 没有输入通道")
        return idx

    key = str(selector).strip().lower()
    if key.isdigit():
        return resolve_input(int(key))

    matches = [d for d in list_inputs() if key in d.name.lower()]
    if not matches:
        raise ValueError(
            f"没有找到名称含 {selector!r} 的输入设备。\n可用设备：\n"
            + "\n".join(f"  {d}" for d in list_inputs())
        )
    for pref in ("WASAPI", "WDM-KS", "DirectSound", "MME"):
        for m in matches:
            if m.hostapi == pref:
                return m.index
    return matches[0].index


def resolve_output(selector: int | str | None) -> int:
    """解析输出设备（输出不需要探测，能打开即可）。"""
    if selector is None or selector == "":
        return system_default_output()

    if isinstance(selector, int):
        idx = selector
        if not (0 <= idx < len(sd.query_devices())):
            raise ValueError(f"设备索引 {idx} 超出范围")
        if sd.query_devices(idx)["max_output_channels"] <= 0:
            raise ValueError(f"设备 [{idx}] 没有输出通道")
        return idx

    key = str(selector).strip().lower()
    if key.isdigit():
        return resolve_output(int(key))

    matches = [d for d in list_outputs() if key in d.name.lower()]
    if not matches:
        raise ValueError(
            f"没有找到名称含 {selector!r} 的输出设备。\n可用设备：\n"
            + "\n".join(f"  {d}" for d in list_outputs())
        )
    for pref in ("WASAPI", "WDM-KS", "DirectSound", "MME"):
        for m in matches:
            if m.hostapi == pref:
                return m.index
    return matches[0].index


def check_input_alive(index: int, duration: float = 0.5,
                      sr: int = 16000) -> tuple[bool, float]:
    """录一小段判断设备是否有信号（不探测，直接测指定的那一个）。"""
    ok, db = measure_rms(index, sr, duration)
    if not ok:
        raise RuntimeError(f"设备 [{index}] 无法以 {sr}Hz 打开")
    return (db > DEAD_DEVICE_DBFS, db)
