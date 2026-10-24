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

# 统一从项目根 .env 读本机配置；.env 里没有才用下面的默认值
try:
    from host.config import load_dotenv
    load_dotenv()
except Exception:
    pass

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def _default_model_dir() -> str:
    """模型缓存目录：优先 LOCALAPPDATA，不写死盘符。"""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "xiao72", "models")


def _detect_port() -> str:
    """没配 X72_PORT 时按描述找 CH340 / USB 串口。"""
    try:
        from serial.tools import list_ports  # type: ignore
    except ImportError:
        return "COM1"
    ports = list(list_ports.comports())
    for p in ports:
        if "CH340" in (p.description or "").upper():
            return p.device
    for p in ports:
        if "USB" in (p.description or "").upper():
            return p.device
    return "COM1"


def _resolve_port() -> str:
    """端口优先级：X72_PORT（且当前真实存在）> auto（靠握手发现）。

    配了 X72_PORT 但设备没插上、或插拔后口号变了，就回退到 auto，
    避免把 COM13 写死在 .env 里之后，换一次接口就打不开。
    """
    want = os.environ.get("X72_PORT")
    if not want:
        return "auto"
    try:
        from serial.tools import list_ports  # type: ignore
        ports = list(list_ports.comports())
    except ImportError:
        return want
    for p in ports:
        if p.device.upper() == want.upper():
            return want
    return "auto"


MODEL_DIR = os.environ.get("X72_MODEL_DIR") or _default_model_dir()
DEFAULT_PORT = _resolve_port()


def main() -> int:
    ap = argparse.ArgumentParser(description="小72 语音闭环")
    ap.add_argument("--text", action="store_true", help="文字模式：打字代替说话")
    ap.add_argument("--dry-run", action="store_true", help="只打印帧，不发送串口")
    ap.add_argument("--port", default=DEFAULT_PORT,
                    help="auto（默认）靠握手发现设备；也可指定 COMx")
    ap.add_argument("--target", default=None,
                    help="期望的设备身份（id 或 model 片段），多设备时必填")
    ap.add_argument("--input", default=None, help="麦克风：索引或名称片段")
    ap.add_argument("--model", default="small", help="ASR 模型：tiny/base/small/medium/large-v3")
    ap.add_argument("--device", default="cpu", help="ASR 设备：cpu / cuda")
    ap.add_argument("--compute", default=None, help="int8 / float16")
    ap.add_argument("--language", default="zh", help="语言，auto 自动检测")
    ap.add_argument("--silence-end", type=int, default=1200,
                    help="静音多少毫秒算说完（默认 1200）")
    ap.add_argument("--max-utterance", type=int, default=10000,
                    help="单句最长录音毫秒数（默认 10000）。VAD 没判出句尾时强制收尾，"
                         "避免长音频拖慢 ASR")
    ap.add_argument("--trigger", default="space", choices=["space", "auto"],
                    help="录音触发方式：space=按空格开始（默认）；auto=一直听（旧行为）")
    ap.add_argument("--mute", action="store_true",
                    help="关闭语音播报（TTS）；等价于 X72_TTS_MUTE=1")
    ap.add_argument("--timeout", type=float, default=30.0, help="单轮最长等待秒数")
    ap.add_argument("--no-llm", action="store_true", help="强制只用规则版（离线）")
    ap.add_argument("--verbose", action="store_true", help="打印 LLM 失败详情")
    args = ap.parse_args()

    if args.mute:
        os.environ["X72_TTS_MUTE"] = "1"

    compute = args.compute or ("float16" if args.device == "cuda" else "int8")

    from voice.pipeline import VoiceAssistant
    from voice.trigger import make_trigger

    a = VoiceAssistant(
        model=args.model,
        asr_device=args.device,
        compute_type=compute,
        model_dir=MODEL_DIR,
        audio_device=args.input,
        port=None if args.dry_run else args.port,
        device=args.target,
        dry_run=args.dry_run,
        language=None if args.language == "auto" else args.language,
        silence_end_ms=args.silence_end,
        timeout=args.timeout,
        use_llm=not args.no_llm,
        verbose=args.verbose,
        max_utterance_ms=args.max_utterance,
        trigger=make_trigger(args.trigger),
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
