"""设备身份握手（host 侧）。

协议（文本行，`\n` 结尾，与现有帧格式同族）
------------------------------------------------
  PC  → 设备：`[I?]`
  设备 → PC ：`[I <id>|<model>|<version>|<cap1,cap2,...>]`

例：`[I kuri72-desk|X72-LED|1.0|led,brightness,period]`

为什么用握手而不是 COM 口号 / 序列号
------------------------------------
CH340 这类芯片多数**没有 USB 序列号**，同一型号两颗完全无法区分；
COM 口号又会随插拔顺序变化。让设备自己报名是唯一不依赖硬件型号的办法。

兼容性
------
老固件不认识 `[I?]`，会当作非法帧丢弃且不回复。
本模块对此的处理是**超时返回 None**，不抛异常，不影响后续正常发帧。

用法
----
    from device_id import identify_port, scan_ports

    dev = identify_port("COM13")          # -> dict 或 None
    found = scan_ports()                   # -> [{"port": "COM13", ...}, ...]
"""
from __future__ import annotations

import time

QUERY = "[I?]"
DEFAULT_TIMEOUT = 0.6
DEFAULT_BAUD = 115200

# 已知的 USB 转串口 VID（用于跳过蓝牙虚拟串口）
USB_SERIAL_VIDS = {
    0x1A86,  # CH340 / CH341
    0x10C4,  # CP210x
    0x0403,  # FTDI
    0x067B,  # PL2303
}


def parse_reply(line: str):
    """解析 `[I ...]` 应答，失败返回 None。"""
    s = (line or "").strip()
    if not s.startswith("[I") or not s.endswith("]"):
        return None
    body = s[2:-1].strip()
    if not body:
        return None
    parts = [p.strip() for p in body.split("|")]
    if len(parts) < 4:
        return None
    caps = [c.strip() for c in parts[3].split(",") if c.strip()]
    return {
        "id": parts[0],
        "model": parts[1],
        "firmware": parts[2],
        "capabilities": caps,
        "raw": s,
    }


def identify(ser, timeout: float = DEFAULT_TIMEOUT):
    """在一个已打开的 serial 对象上做握手。失败返回 None。"""
    try:
        ser.reset_input_buffer()
    except Exception:
        pass
    ser.write((QUERY + "\n").encode("ascii"))
    try:
        ser.flush()
    except Exception:
        pass

    deadline = time.time() + timeout
    buf = bytearray()
    while time.time() < deadline:
        chunk = ser.read(1)
        if not chunk:
            continue
        buf.extend(chunk)
        if b"]" in buf:
            break

    if not buf:
        return None
    text = bytes(buf).decode("ascii", errors="replace")
    # 可能收到多行，取第一条像应答的
    for line in text.replace("\r", "\n").split("\n"):
        got = parse_reply(line)
        if got:
            return got
    return None


def identify_port(port: str, baud: int = DEFAULT_BAUD,
                  timeout: float = DEFAULT_TIMEOUT):
    """打开端口 → 握手 → 关闭。失败返回 None（不抛异常）。"""
    try:
        import serial  # type: ignore
    except ImportError:
        return None
    try:
        ser = serial.Serial(port, baud, timeout=0.1)
    except Exception:
        return None
    try:
        time.sleep(0.15)          # 等 CH340 的 DTR 稳定
        return identify(ser, timeout)
    finally:
        try:
            ser.close()
        except Exception:
            pass


def _candidate_ports(include_bluetooth: bool = False):
    """列出候选端口，默认跳过蓝牙虚拟串口。"""
    try:
        from serial.tools import list_ports  # type: ignore
    except ImportError:
        return []
    out = []
    for p in list_ports.comports():
        desc = (p.description or "").upper()
        if not include_bluetooth and ("BTHENUM" in (p.hwid or "").upper()
                                      or "BLUETOOTH" in desc):
            continue
        out.append(p)
    # 带已知 USB VID 的排前面
    def rank(p):
        return 0 if (p.vid in USB_SERIAL_VIDS) else 1
    out.sort(key=rank)
    return out


def scan_ports(timeout: float = 0.4, include_bluetooth: bool = False):
    """逐个端口握手，返回所有认出身份的端口。"""
    found = []
    for p in _candidate_ports(include_bluetooth):
        dev = identify_port(p.device, timeout=timeout)
        if dev:
            dev["port"] = p.device
            dev["description"] = p.description
            found.append(dev)
    return found


if __name__ == "__main__":
    hits = scan_ports()
    if not hits:
        print("没有设备响应握手。可能原因：")
        print("  1) 固件还没有实现 [I?] 应答（需要升级固件）")
        print("  2) 板子没上电 / 串口被别的程序占用")
    else:
        for d in hits:
            print("%-6s %-24s %-10s caps=%s" % (
                d["port"], d["model"], d["firmware"], ",".join(d["capabilities"])))
