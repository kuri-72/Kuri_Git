"""
check_env.py — 环境自检
=========================
用途：确认"你现在缺什么"，而不是让你猜。

跑法（在任意目录都行）：
    python xiao72/host/check_env.py

输出里：
    [OK]   正常
    [!!]   有问题，下面会告诉你怎么修
    [--]   可选，不影响当前阶段
"""
from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FIRMWARE = ROOT / "firmware"

ok_count = 0
warn_count = 0
fail_count = 0


def ok(msg: str) -> None:
    global ok_count
    ok_count += 1
    print(f"  [OK] {msg}")


def warn(msg: str, fix: str = "") -> None:
    global warn_count
    warn_count += 1
    print(f"  [--] {msg}")
    if fix:
        print(f"       修复：{fix}")


def fail(msg: str, fix: str = "") -> None:
    global fail_count
    fail_count += 1
    print(f"  [!!] {msg}")
    if fix:
        print(f"       修复：{fix}")


def section(title: str) -> None:
    print(f"\n{title}")
    print("-" * 58)


def main() -> int:
    print("=" * 58)
    print("  小72 · 环境自检")
    print("=" * 58)

    # ---------------------------------------------------------- Python
    section("1. Python")
    v = sys.version_info
    if v >= (3, 9):
        ok(f"Python {v.major}.{v.minor}.{v.micro}（需要 >= 3.9）")
    elif v >= (3, 7):
        warn(f"Python {v.major}.{v.minor}.{v.micro} 能用，但建议升到 3.9+")
    else:
        fail(f"Python {v.major}.{v.minor} 太旧", "去 python.org 装 3.9+")
    ok(f"运行位置：{sys.executable}")

    # ---------------------------------------------------------- 依赖
    section("2. Python 依赖")
    for mod, pkg, required in (
        ("openai", "openai", True),          # 阶段 4 才需要，但装了更好
        ("serial", "pyserial", False),       # 阶段 3 才需要
    ):
        spec = importlib.util.find_spec(mod)
        if spec is not None:
            ok(f"{pkg} 已安装")
        elif required:
            warn(f"{pkg} 未安装（接真 AI 时需要）", f"pip install {pkg}")
        else:
            warn(f"{pkg} 未安装（周六接串口时才需要）", f"pip install {pkg}")

    # ---------------------------------------------------------- 项目文件
    section("3. 项目文件完整性")
    need = [
        (ROOT / "docs" / "intent_prompt.md", "意图识别 Prompt"),
        (HERE / "state.py", "状态合并/协议编码"),
        (HERE / "intent.py", "意图识别层"),
        (HERE / "main.py", "CLI 入口"),
        (FIRMWARE / "x72_proto.c", "单片机解析器"),
        (FIRMWARE / "x72_proto.h", "单片机接口"),
        (FIRMWARE / "template" / "x72_port_stm32.c", "平台适配层"),
    ]
    for path, desc in need:
        if path.exists():
            ok(f"{desc}：{path.name}")
        else:
            fail(f"缺少{desc}：{path}", "项目文件不完整，请重新索取")

    # ---------------------------------------------------------- 模拟器
    section("4. C 模拟器（阶段 1 验证用）")
    sim = FIRMWARE / "sim.exe"
    if sim.exists():
        ok(f"sim.exe 已存在（{sim.stat().st_size // 1024} KB）")
        try:
            r = subprocess.run([str(sim), "--selftest"],
                               capture_output=True, text=True, timeout=15)
            tail = [ln for ln in r.stdout.splitlines() if "selftest" in ln]
            if r.returncode == 0 and tail:
                ok(f"C 解析器自检：{tail[-1].strip()}")
            else:
                fail("sim.exe 能跑但自检失败", "重新编译：cl /DX72_NO_PORT ...")
        except Exception as e:
            fail(f"sim.exe 运行异常：{e}")
    else:
        warn("sim.exe 不存在（不影响 Python 端测试）",
             "用 VS 的 x64 Native Tools 命令行在 firmware 目录编译")

    # ---------------------------------------------------------- 编译器
    section("5. C 编译器（只有要重新编译模拟器时才需要）")
    found = []
    for name in ("cl", "gcc", "clang"):
        p = shutil.which(name)
        if p:
            found.append(f"{name} → {p}")
    if found:
        ok("已找到：" + "；".join(found))
    else:
        warn("当前终端里找不到 cl/gcc",
             "用「x64 Native Tools Command Prompt for VS 2022」打开再试")

    # ---------------------------------------------------------- 串口
    section("6. 串口（阶段 3 才需要）")
    try:
        from serial.tools import list_ports  # type: ignore
        ports = list(list_ports.comports())
        if ports:
            for p in ports:
                ok(f"{p.device}  {p.description}")
        else:
            warn("没检测到串口设备（周六插上 USB-TTL 后再看这里）")
    except ImportError:
        warn("pyserial 没装，暂时跳过（阶段 3 再装）")

    # ---------------------------------------------------------- 环境
    section("7. 系统信息")
    ok(f"系统：{platform.system()} {platform.release()}")
    ok(f"工作目录：{os.getcwd()}")

    # ---------------------------------------------------------- 总结
    print("\n" + "=" * 58)
    print(f"  结果：{ok_count} 项正常 / {warn_count} 项提醒 / {fail_count} 项失败")
    print("=" * 58)

    if fail_count == 0 and warn_count <= 2:
        print("\n  可以开始了。下一步：")
        print("    cd host")
        print("    python main.py --mock --dry-run --demo")
    elif fail_count == 0:
        print("\n  基本可用。提醒项不影响当前阶段。")
    else:
        print("\n  先解决 [!!] 项，再往下走。")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
