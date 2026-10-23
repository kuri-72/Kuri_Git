"""
小72 · 主程序（文本输入 → 意图 → 帧 → 输出/串口）
====================================================
用法：
    python main.py                        # 真 AI（需要 .env 里的 key）
    python main.py --mock                 # 离线规则版，不需要 key/网络
    python main.py --mock --dry-run       # 只打印帧，不碰串口（现在用这个）
    python main.py --dry-run              # 真 AI + 只打印帧
    python main.py --port COM3 --ack      # 真发串口，等 OK 应答
    python main.py --demo                 # 跑一遍内置测试句，然后退出

设计要点：
    - 意图层可替换（IntentParser / MockParser），其余层完全不感知
    - 没有串口也完全可用（--dry-run），这是周六之前的主要工作方式
"""
from __future__ import annotations

import argparse
import sys

from config import Config
from intent import Intent, IntentError, IntentParser, MockParser
from state import LedState


def print_banner(cfg: Config | None, use_mock: bool, dry_run: bool, port: str | None):
    line = "=" * 62
    print(line)
    print("  小72 · 灯控链路 v0.1")
    if use_mock:
        print("  意图层：MockParser（离线规则版，不需要 key）")
    elif cfg is not None:
        print(f"  意图层：LLM  {cfg.provider} / {cfg.model}")
        print(f"  key：{cfg.masked_key()}   base_url：{cfg.base_url}")
    print(f"  输出：{'DRY-RUN（只打印帧）' if dry_run else f'串口 {port}'}")
    print(line)
    print("  输入中文指令；:quit 退出  :state 看当前状态  :raw 看模型原始输出")
    print(line)


def process_text(text: str, parser, state: LedState, link,
                 dry_run: bool, verbose_raw: bool) -> None:
    try:
        intent: Intent = parser.parse(text)
    except IntentError as e:
        print(f"  [意图层失败] {e}")
        print("  （状态未改变，这是设计如此：理解失败不应该改变硬件状态）")
        return

    changed = state.apply(intent.cmd, intent.brightness, intent.period_ms)
    frame = state.encode()

    print(f"  小72：{intent.say}")
    print(f"  意图：{intent.as_dict()}")
    if intent.repaired:
        print(f"  修复：{'；'.join(intent.repaired)}")
    if verbose_raw and intent.raw:
        print(f"  原始：{intent.raw[:200]}")
    print(f"  变化：{changed if changed else '无（状态未变，仍发全量帧）'}")
    print(f"  帧  ：{frame}   ({len(frame)} 字节)")

    if dry_run or link is None:
        return
    try:
        ack = link.send(frame)
        if ack:
            print(f"  应答：{ack}")
    except Exception as e:
        print(f"  [串口失败] {type(e).__name__}: {e}")


DEMO_TEXTS = [
    "灯好亮啊",
    "调暗一点，然后慢慢呼吸",
    "调到 40%",
    "全亮",
    "你叫什么名字",
    "把机械臂转到 90 度",
    "关灯",
    "灯太暗了，看不清",
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="小72 灯控链路")
    ap.add_argument("--mock", action="store_true", help="用离线规则版意图解析")
    ap.add_argument("--dry-run", action="store_true", help="只打印帧，不发串口")
    ap.add_argument("--port", default=None, help="串口号，如 COM3")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--ack", action="store_true", help="等待单片机回 OK")
    ap.add_argument("--demo", action="store_true", help="跑内置测试句后退出")
    ap.add_argument("--raw", action="store_true", help="打印模型原始输出")
    args = ap.parse_args(argv)

    cfg = None
    if args.mock:
        parser = MockParser()
    else:
        cfg = Config.from_env()
        parser = IntentParser(cfg)

    link = None
    if not args.dry_run and args.port:
        from serial_link import SerialLink
        link = SerialLink(args.port, args.baud, ack=args.ack).open()

    state = LedState(brightness=0, period_ms=0)
    print_banner(cfg, args.mock, args.dry_run or link is None, args.port)

    if args.demo:
        for t in DEMO_TEXTS:
            print(f"\n> {t}")
            process_text(t, parser, state, link, args.dry_run or link is None, args.raw)
        print(f"\n最终状态：{state.to_dict()}")
        return 0

    try:
        while True:
            try:
                text = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not text:
                continue
            if text in (":quit", ":q", "exit", "quit"):
                break
            if text == ":state":
                print(f"  当前状态：{state.to_dict()}")
                print(f"  当前帧  ：{state.encode()}")
                continue
            process_text(text, parser, state, link,
                         args.dry_run or link is None, args.raw or text == ":raw")
    finally:
        if link is not None:
            link.close()
    print(f"\n最终状态：{state.to_dict()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
