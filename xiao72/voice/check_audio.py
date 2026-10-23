"""
check_audio.py — 音频层自检（P0 验收脚本）
=============================================
跑法：
    python xiao72/voice/check_audio.py                 # 跟随系统默认
    python xiao72/voice/check_audio.py --list          # 只列设备
    python xiao72/voice/check_audio.py --stability     # 只做稳定性检测
    python xiao72/voice/check_audio.py --input Realtek # 指定麦克风
    python xiao72/voice/check_audio.py --input 2 --sr 44100
    python xiao72/voice/check_audio.py --record 5 --play

检查顺序：
    1. 系统默认设备是谁
    2. 该设备在哪个采样率下真正有数据（逐个试）
    3. 重复测 3 次，判断是否稳定（识别"间歇性失声"的设备）
    4. 录一段、归一化、存 wav、校验格式
"""
from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from voice.audio import Recorder, devices  # noqa: E402
from voice.audio.recorder import normalize_gain  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="小72 音频层自检")
    ap.add_argument("--input", default=None, help="麦克风：索引或名称片段，留空=系统默认")
    ap.add_argument("--output", default=None, help="扬声器：索引或名称片段，留空=系统默认")
    ap.add_argument("--sr", type=int, default=None, help="强制采样率")
    ap.add_argument("--list", action="store_true", help="只列出设备")
    ap.add_argument("--stability", action="store_true", help="只做稳定性检测")
    ap.add_argument("--record", type=float, default=3.0, help="录音秒数")
    ap.add_argument("--play", action="store_true", help="录完回放")
    ap.add_argument("--out", default=None, help="wav 保存路径")
    args = ap.parse_args()

    print("=" * 72)
    print("  小72 · 音频层自检")
    print("=" * 72)

    print(f"\n系统默认输入：{devices.describe(devices.system_default_input())}")
    print(f"系统默认输出：{devices.describe(devices.system_default_output())}")

    if args.list:
        print("\n【输入设备】")
        for d in devices.list_inputs():
            print("  " + str(d))
        print("\n【输出设备】")
        for d in devices.list_outputs():
            print("  " + str(d))
        return 0

    # ---------- 选设备 ----------
    print("\n[1] 选择录音设备")
    try:
        rec = Recorder(device=args.input, sr=args.sr, verbose=True)
    except Exception as e:
        print(f"    [FAIL] {e}")
        return 1
    print(f"    → {rec.info()}")

    # ---------- 信号质量 ----------
    print("\n[2] 信号质量检测（一条连续流录 3 秒，掐掉开头 0.8 秒）")
    st = devices.stability_check(rec.device_index, rec.sr, duration=3.0)

    if "error" in st:
        print(f"    [FAIL] {st['error']}")
        return 1

    print(f"    窗口数：{st['windows']}（每 100ms 一格）")
    print(f"    无数据窗口：{st['dead_ratio'] * 100:.1f}%")
    print(f"    中位数：{st['median']:+.1f} dBFS    峰值：{st['peak']:+.1f} dBFS")

    if st["stable"]:
        print("    判定：[OK] 信号连续可用")
    else:
        print("    判定：[WARN] 信号断续")
        print("           可能原因：")
        print("             · 麦克风物理静音 / 无线休眠")
        print("             · 驱动或降噪软件压制")
        print("           可换设备对比：--input <名称片段>")

    if args.stability:
        return 0 if st["stable"] else 1

    # ---------- 录音 ----------
    print(f"\n[3] 录音 {args.record} 秒（现在可以说话）")
    raw = rec.record_raw(args.record)
    rms = float(np.sqrt(np.mean(raw ** 2)))
    db = 20 * np.log10(rms + 1e-12)
    print(f"    原始电平 = {db:+.1f} dBFS")
    print(f"    时长 = {len(raw) / 16000:.2f} 秒  ({len(raw)} 样本 @16k)")

    if devices.is_dead_signal(raw):
        print("    [!] 这段录音没有有效数据（低于 -90 dBFS）")

    norm, gain_db = normalize_gain(raw)
    rms2 = float(np.sqrt(np.mean(norm ** 2)))
    print(f"    自动增益 = {gain_db:+.1f} dB  →  {20 * np.log10(rms2 + 1e-12):+.1f} dBFS")

    # ---------- 保存 ----------
    out_path = args.out or str(Path(__file__).resolve().parent / "p0_capture.wav")
    saved = Recorder.save_wav(out_path, norm)
    print(f"\n[4] 已保存：{saved}")
    with wave.open(str(saved), "rb") as w:
        print(f"    通道={w.getnchannels()}  位深={w.getsampwidth()*8}bit  "
              f"采样率={w.getframerate()}Hz  帧数={w.getnframes()}")
        ok = (w.getnchannels() == 1 and w.getframerate() == 16000
              and w.getsampwidth() == 2)
        print(f"    格式校验：{'通过' if ok else '不符合 ASR 要求'}")

    # ---------- 回放 ----------
    if args.play:
        print("\n[5] 回放")
        try:
            out_idx = devices.resolve_output(args.output)
            Recorder.play(norm, device=out_idx)
            print("    播放完成")
        except Exception as e:
            print(f"    播放失败：{e}")

    print("\n" + "=" * 72)
    print("  结论：音频层可用" if st["stable"] else "  结论：链路可用，但麦克风不稳定")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
