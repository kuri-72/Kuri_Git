"""
check_asr.py — 语音识别自检（P1 验收脚本）
=============================================
跑法（必须用虚拟环境里的 python）：

    E:\\xiao72-venv\\Scripts\\python.exe voice\\check_asr.py --file voice\\p0_capture.wav
    E:\\xiao72-venv\\Scripts\\python.exe voice\\check_asr.py --record 5      # 现录现识别
    E:\\xiao72-venv\\Scripts\\python.exe voice\\check_asr.py --record 5 --input Realtek
    E:\\xiao72-venv\\Scripts\\python.exe voice\\check_asr.py --model medium   # 换模型
    E:\\xiao72-venv\\Scripts\\python.exe voice\\check_asr.py --device cuda --model large-v3

或者用包装脚本：
    run_asr.bat --record 5

环境变量（模型下载用）：
    HF_ENDPOINT=https://huggingface.co
    HTTPS_PROXY=http://127.0.0.1:7897
    HF_HUB_DISABLE_XET=1
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 默认模型下载目录，跟 .env / 系统环境变量保持一致
import os
try:
    from host.config import load_dotenv
    load_dotenv()
except Exception:
    pass

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def _default_model_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "xiao72", "models")


MODEL_DIR = os.environ.get("X72_MODEL_DIR") or _default_model_dir()


def main() -> int:
    ap = argparse.ArgumentParser(description="小72 语音识别自检")
    ap.add_argument("--file", default=None, help="要识别的 wav 文件")
    ap.add_argument("--record", type=float, default=None, help="先录这么多秒再识别")
    ap.add_argument("--record-auto", action="store_true",
                    help="VAD 自动切句：一直听，说完就识别（P2）")
    ap.add_argument("--silence-end", type=int, default=1200,
                    help="说完判定：静音多少毫秒算结束（默认 1200）")
    ap.add_argument("--timeout", type=float, default=30.0,
                    help="自动模式最长等待秒数（默认 30）")
    ap.add_argument("--input", default=None, help="录音设备（索引或名称片段）")
    ap.add_argument("--model", default="small", help="模型：tiny/base/small/medium/large-v3")
    ap.add_argument("--device", default="cpu", help="cpu 或 cuda")
    ap.add_argument("--compute", default=None, help="int8 / float16 / int8_float16")
    ap.add_argument("--language", default="zh", help="语言，auto 表示自动检测")
    ap.add_argument("--model-dir", default=MODEL_DIR, help="模型缓存目录")
    ap.add_argument("--save", default=None, help="录音保存路径")
    args = ap.parse_args()

    if not args.file and args.record is None and not args.record_auto:
        print("请指定 --file <wav> / --record <秒数> / --record-auto（VAD 自动切句）")
        return 2

    compute = args.compute or ("float16" if args.device == "cuda" else "int8")
    lang = None if args.language == "auto" else args.language

    print("=" * 70)
    print("  小72 · 语音识别自检")
    print("=" * 70)
    print(f"  模型      : {args.model}")
    print(f"  设备      : {args.device} ({compute})")
    print(f"  模型目录  : {args.model_dir}")
    print(f"  语言      : {args.language}")
    if args.record_auto:
        print(f"  切句模式  : VAD 自动（静音 {args.silence_end} ms 判定结束）")
    print()

    # ---------- 准备音频 ----------
    audio_path = args.file
    if args.record_auto:
        import numpy as np

        from voice.audio import Recorder
        from voice.audio.vad import VadSegmenter

        print("[1] VAD 自动切句：请说话，说完会自动结束")
        rec = Recorder(device=args.input)
        print(f"    设备：{rec.info()}")

        seg = VadSegmenter(end_silence_ms=args.silence_end)
        print(f"    阈值={seg.threshold}  静音判定={seg.end_silence_ms}ms  "
              f"最短语音={seg.min_speech_ms}ms")
        print("    正在听……（最多等 %.0f 秒）" % args.timeout)

        t0 = time.time()
        utt = rec.record_utterance(segmenter=seg, timeout=args.timeout,
                                   silence_end_ms=args.silence_end)
        elapsed = time.time() - t0

        if utt.size == 0:
            print(f"    [FAIL] {elapsed:.1f} 秒内没有检测到有效语音")
            print("           可能原因：麦克风电平太低 / 阈值太高 / 说话太短")
            return 1

        dur = utt.size / 16000
        rms = float(np.sqrt(np.mean(utt ** 2)))
        print(f"    检测到一句：{dur:.2f} 秒（等待 {elapsed - dur:.1f}s + 语音 {dur:.1f}s）")
        print(f"    电平 {20 * np.log10(rms + 1e-12):+.1f} dBFS")

        audio_path = args.save or str(Path(__file__).resolve().parent / "asr_input.wav")
        Recorder.save_wav(audio_path, utt)
        print(f"    已保存：{audio_path}")

    elif args.record is not None:
        import numpy as np

        from voice.audio import Recorder
        from voice.audio.recorder import normalize_gain

        print(f"[1] 录音 {args.record} 秒（现在可以说话）")
        rec = Recorder(device=args.input)
        print(f"    设备：{rec.info()}")
        raw = rec.record_raw(args.record)
        norm, gain_db = normalize_gain(raw)
        rms = float(np.sqrt(np.mean(raw ** 2)))
        print(f"    原始电平 {20 * np.log10(rms + 1e-12):+.1f} dBFS"
              f"  →  增益 {gain_db:+.1f} dB")

        audio_path = args.save or str(Path(__file__).resolve().parent / "asr_input.wav")
        Recorder.save_wav(audio_path, norm)
        print(f"    已保存：{audio_path}")
    else:
        print(f"[1] 使用文件：{audio_path}")

    if not audio_path or not Path(audio_path).exists():
        print(f"[FAIL] 找不到音频文件：{audio_path}")
        return 1

    # ---------- 加载模型 ----------
    from voice.asr import create_provider

    print(f"\n[2] 加载模型（首次会下载到 {args.model_dir}）")
    t0 = time.time()
    try:
        provider = create_provider(
            "faster-whisper",
            model_size=args.model,
            device=args.device,
            compute_type=compute,
            model_dir=args.model_dir,
        )
        # 触发一次空转，把模型真正加载进来
        provider._ensure_model()  # noqa: SLF001
    except Exception as e:
        print(f"    [FAIL] {type(e).__name__}: {e}")
        print("    常见原因：")
        print("      · 模型下载失败 → 设置 HF_ENDPOINT / HTTPS_PROXY / HF_HUB_DISABLE_XET=1")
        print("      · CUDA 不可用 → 去掉 --device cuda，先用 CPU")
        return 1
    print(f"    加载耗时 {time.time() - t0:.1f} 秒")

    # ---------- 识别 ----------
    print("\n[3] 识别")
    try:
        r = provider.transcribe(audio_path, language=lang)
    except Exception as e:
        print(f"    [FAIL] {type(e).__name__}: {e}")
        return 1

    print(f"    语言：{r.language} (置信 {r.language_probability:.2f})")
    print(f"    音频 {r.duration:.2f}s / 耗时 {r.elapsed:.2f}s / 实时率 {r.realtime_factor:.1f}x")
    print()
    print("=" * 70)
    print(f"  识别结果：{r.text if r.text else '(空)'}")
    print("=" * 70)

    if r.segments:
        print("\n分段：")
        for s in r.segments:
            print(f"  [{s['start']:6.2f} → {s['end']:6.2f}] {s['text']}")

    provider.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
