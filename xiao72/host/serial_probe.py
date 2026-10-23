"""
serial_probe.py — 串口连通性诊断（只看，不改硬件状态）
========================================================
不发送任何控制命令，只做三件事：
  1. 打开端口，确认驱动/波特率可用
  2. 静默监听 1 秒，看板子有没有主动输出（新 main.c 不会输出，所以安静属正常）
  3. 发送一个换行，观察是否有任何回显

判断依据：
  - 打开成功但完全没数据 → 板子可能在跑旧固件（还没加 USART1 初始化）
  - 有乱码 → 波特率不对
  - 有 "[...]" 之类回显 → 可能在跑回环或旧固件
"""
from __future__ import annotations

import sys
import time

import serial
from serial.tools import list_ports

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM8"
BAUD = 115200


def main() -> int:
    print("=" * 56)
    print(f"  串口诊断  {PORT} @ {BAUD}")
    print("=" * 56)

    print("\n[1] 可用端口")
    ports = list(list_ports.comports())
    if not ports:
        print("  没有检测到任何串口")
    for p in ports:
        mark = " ←目标" if p.device.upper() == PORT.upper() else ""
        print(f"  {p.device:8s} {p.description}{mark}")

    print(f"\n[2] 打开 {PORT}")
    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.2)
    except Exception as e:
        print(f"  [FAIL] 打开失败: {type(e).__name__}: {e}")
        print("  常见原因：端口被串口助手占用 / 端口号不对 / 驱动未装")
        return 1
    print(f"  [OK] 已打开（DTR={ser.dtr}, RTS={ser.rts}）")

    # 清掉上电残留
    time.sleep(0.2)
    ser.reset_input_buffer()

    print("\n[3] 静默监听 1 秒（观察板子是否主动输出）")
    deadline = time.time() + 1.0
    got = bytearray()
    while time.time() < deadline:
        n = ser.in_waiting
        if n:
            got.extend(ser.read(n))
        else:
            time.sleep(0.02)
    if got:
        print(f"  收到 {len(got)} 字节: {got[:80]!r}")
        try:
            print(f"  按 UTF-8 解码: {got.decode('utf-8', errors='replace')[:200]!r}")
        except Exception:
            pass
    else:
        print("  无数据（预期：新固件不主动输出；若板子还在跑旧固件也正常）")

    print("\n[4] 发送一个换行 + 一个合法帧，观察回显")
    for label, payload in [
        ("空行", b"\n"),
        ("JSON 帧", b'{"led":50,"period":2000}\n'),
        ("紧凑帧", b"[L00502000|A---|]\n"),
    ]:
        ser.write(payload)
        ser.flush()
        time.sleep(0.3)
        resp = ser.read(ser.in_waiting or 1)
        # read() 在无数据时会等 timeout，这里用 in_waiting 预判
        resp = ser.read(ser.in_waiting) if ser.in_waiting else b""
        print(f"  发送 {label:10s} {payload!r:40s} → 回显 {resp!r}")

    ser.close()
    print(f"\n[5] 已关闭 {PORT}")

    print("\n" + "=" * 56)
    print("  判读")
    print("=" * 56)
    if not got:
        print("  端口能开、无主动输出 → 硬件链路正常。")
        print("  下一步：确认板子里烧的是新固件（含 USART1_Init），")
        print("  然后用 main.py --port COM8 发命令，看 OLED 的 RX/F 计数是否跳动。")
    else:
        print("  有主动输出，需要看内容判断固件类型。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
