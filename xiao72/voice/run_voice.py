"""
run_voice.py — 语音闭环入口（P3）
====================================
跑法（必须用虚拟环境的 python）：

    run_voice.bat                      # 听麦克风，说完就控制灯
    run_voice.bat --text               # 打字测试，不碰麦克风
    run_voice.bat --dry-run            # 只打印帧，不发送
    run_voice.bat --port COM8          # 指定串口
    run_voice.bat --model medium       # 换更大的模型
    run_voice.bat --silence-end 800    # 更快判定说完
    run_voice.bat --input Realtek      # 换麦克风

环境变量（模型下载 / 缓存）由 run_voice.bat 统一设置。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

MODEL_DIR = os.environ.get("X72_MODEL_DIR", r"D:\AI_Cache\models")
DEFAULT_PORT = os.environ.get("X72_PORT", "COM8")


def main() -> int:
    ap = argparse.ArgumentParser(description="小72 语音闭环")
    ap.add_argument("--text", action="store_true", help="文字模式：打字代替说话")
    ap.add_argument("--dry-run", action="store_true", help="只打印帧，不发送串口")
    ap.add_argument("--port", default=DEFAULT_PORT, help=f"串口（默认 {DEFAULT_PORT}）")
    ap.add_argument("--input", default=None, help="麦克风：索引或名称片段")
    ap.add_argument("--model", default="small", help="ASR 模型：tiny/base/small/medium/large-v3")
    ap.add_argument("--device", default="cpu", help="ASR 设备：cpu / cuda")
    ap.add_argument("--compute", default=None, help="int8 / float16")
    ap.add_argument("--language", default="zh", help="语言，auto 自动检测")
    ap.add_argument("--silence-end", type=int, default=1200,
                    help="静音多少毫秒算说完（默认 1200）")
    ap.add_argument("--timeout", type=float, default=30.0, help="单轮最长等待秒数")
    ap.add_argument("--no-llm", action="store_true", help="强制只用规则版（离线）")
    ap.add_argument("--verbose", action="store_true", help="打印 LLM 失败详情")
    args = ap.parse_args()

    compute = args.compute or ("float16" if args.device == "cuda" else "int8")

    from voice.pipeline import VoiceAssistant

    a = VoiceAssistant(
        model=args.model,
        asr_device=args.device,
        compute_type=compute,
        model_dir=MODEL_DIR,
        audio_device=args.input,
        port=None if args.dry_run else args.port,
        dry_run=args.dry_run,
        language=None if args.language == "auto" else args.language,
        silence_end_ms=args.silence_end,
        timeout=args.timeout,
        use_llm=not args.no_llm,
        verbose=args.verbose,
    )

    try:
        a.setup()
    except Exception as e:
        print(f"\n[启动失败] {type(e).__name__}: {e}")
        return 1

    if args.text:
        a.run_text_mode()
    else:
        a.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
