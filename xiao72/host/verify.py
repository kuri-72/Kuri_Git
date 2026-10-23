"""
verify.py — 两端一致性验证（在 PC 上跑，不需要单片机）
=========================================================
这是整套架构最重要的一个测试：

    Python 编码出的报文  →  喂给 C 解析器  →  解析出的状态
    必须 === Python 侧的状态

同时覆盖两种格式（紧凑帧 / JSON）。任何一端改了协议而另一端没改，这里立刻红。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from state import FORMAT_FRAME, FORMAT_JSON, LedState, decode

HERE = Path(__file__).resolve().parent
FIRMWARE = HERE.parent / "firmware"
SIM = FIRMWARE / "sim.exe"

CASES: list[tuple[int, int]] = [
    (0, 0), (10, 0), (50, 2000), (100, 0), (100, 999),
    (1, 50), (30, 500), (72, 1230), (99, 100), (5, 9990),
]


def run_c(lines: list[str]) -> list[tuple[int, int]]:
    """把报文喂给 C 模拟器，按顺序返回它解析出的 (brightness, period_ms)。"""
    if not SIM.exists():
        raise FileNotFoundError(
            f"没找到 {SIM}\n"
            "先在 firmware 目录编译模拟器：\n"
            "  cl /nologo /wd4819 /DX72_NO_PORT /Fe:sim.exe sim_main.c x72_proto.c\n"
            "  gcc -DX72_NO_PORT -I. sim_main.c x72_proto.c -o sim.exe"
        )
    inp = "\n".join(lines) + "\n"
    out = subprocess.run([str(SIM)], input=inp, capture_output=True,
                         text=True, encoding="utf-8", errors="replace",
                         timeout=20).stdout

    result: list[tuple[int, int]] = []
    for line in out.splitlines():
        if not line.startswith("FRAME"):
            continue
        try:
            head, tail = line.split("|", 1)
            st = int(head.split()[1])
            parts = tail.split()
            b = int(parts[1].split("=")[1])
            period = int(parts[2].split("=")[1])
        except (IndexError, ValueError):
            continue
        # C 端 sim_main 打印时已经做过 /10，这里直接用
        result.append((b, period) if st == 0 else (-1, -1))
    return result


def check_format(fmt: str) -> int:
    failures = 0
    msgs: list[str] = []
    expects: list[tuple[int, int]] = []

    for b, p in CASES:
        s = LedState(brightness=b, period_ms=p)
        msg = s.encode(fmt)
        r = decode(msg)
        if not r.ok:
            print(f"  [FAIL] Python 解不了自己产的报文: {msg}  ({r.error})")
            failures += 1
            continue
        msgs.append(msg)
        expects.append((r.state["brightness"], r.state["period_ms"]))

    got = run_c(msgs)
    if len(got) != len(msgs):
        print(f"  [FAIL] C 输出条数不符: {len(got)} / {len(msgs)}")
        return failures + 1

    for msg, exp, g in zip(msgs, expects, got):
        ok = g == exp
        print(f"  [{'PASS' if ok else 'FAIL'}] {msg:<34} python={exp}  c={g}")
        if not ok:
            failures += 1
    return failures


def check_reject() -> int:
    """两端都必须拒收的脏输入。"""
    bad = [
        "[L-1x2000|A---|]",
        "[L0300500]",              # 段数不足
        "[La50000|A---|]",         # 非数字
        "no frame here",
        "[L0300500|B---|]",        # 第二段首字母错
        '{"foo":1}',               # 无已知字段
        '{"led":}',                # 值缺失
        "{bad json}",
    ]
    failures = 0
    for f in bad:
        r = decode(f)
        ok = not r.ok
        print(f"  [{'PASS' if ok else 'FAIL'}] python 拒收 {f!r}")
        if not ok:
            failures += 1

    # C 端也必须全部拒收
    got = run_c(bad)
    if len(got) == len(bad):
        for f, g in zip(bad, got):
            ok = g == (-1, -1)
            print(f"  [{'PASS' if ok else 'FAIL'}] c 端拒收   {f!r}  -> {g}")
            if not ok:
                failures += 1
    else:
        print(f"  [FAIL] C 端拒收测试输出条数不符: {len(got)} / {len(bad)}")
        failures += 1
    return failures


def main() -> int:
    print("=" * 64)
    print("  两端一致性验证：Python 编码 ↔ C 解析")
    print("=" * 64)

    print("\n[1] 紧凑帧格式")
    f1 = check_format(FORMAT_FRAME)

    print("\n[2] JSON 格式")
    f2 = check_format(FORMAT_JSON)

    print("\n[3] 脏输入必须两端都拒收")
    f3 = check_reject()

    total = f1 + f2 + f3
    print(f"\n{'=' * 64}")
    print(f"结果：{'全部通过' if total == 0 else str(total) + ' 项失败'}")
    print("=" * 64)
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
