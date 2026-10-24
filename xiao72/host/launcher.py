"""
launcher.py — 一键启动器（桌面快捷方式实际调用的就是这个）
=============================================================
做的事：
  1. 自动找 Python（DSH 内置的，不依赖 PATH）
  2. 自动找串口（优先 .env 里配的，其次第一个 CH340）
  3. 检查 openai 库和 API key，缺了直接给中文提示
  4. 起 main.py 的交互模式

用法：
    python launcher.py            自动选串口
    python launcher.py COM8       指定串口
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
ENV_FILE = PROJECT / ".env"


def read_env(key: str):
    """从 .env 读一个键（只读，不污染 os.environ）。"""
    if not ENV_FILE.exists():
        return None
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip() or None
    return None


def find_python() -> str:
    """解释器优先级：.env 的 X72_PYTHON → 用户级 venv → 仓库内 .venv → 当前解释器。

    不写死任何绝对路径：换机器时只要 .env 里换一行。
    """
    candidates = [
        read_env("X72_PYTHON"),
        str(Path.home() / "xiao72-venv" / "Scripts" / "python.exe"),
        str(PROJECT / ".venv" / "Scripts" / "python.exe"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return sys.executable


def pause(msg: str = "\n按任意键关闭窗口…") -> None:
    try:
        input(msg)
    except (EOFError, KeyboardInterrupt):
        pass


def detect_port(hint: str | None) -> str | None:
    try:
        from serial.tools import list_ports
    except ImportError:
        return hint

    ports = list(list_ports.comports())
    if hint:
        for p in ports:
            if p.device.upper() == hint.upper():
                return hint
        # .env 里配了但没插上，继续往下找

    # 优先 CH340
    for p in ports:
        if "CH340" in (p.description or "").upper():
            return p.device
    # 其次任何 USB 串口
    for p in ports:
        if "USB" in (p.description or "").upper():
            return p.device
    return None


def main() -> int:
    print("=" * 58)
    print("  小72 · 灯控助手")
    print("=" * 58)

    args = sys.argv[1:]
    port_arg = next((a for a in args if a.upper().startswith("COM")), None)

    port = port_arg or detect_port(read_env("X72_PORT"))
    if port is None:
        print("\n[!] 没检测到串口设备。")
        print("    1. 确认 USB 转串口已插好")
        print("    2. 确认驱动装了（设备管理器里能看到 CH340）")
        print("    3. 或者手动指定：python launcher.py COM8")
        pause()
        return 1

    print(f"  串口：{port}")

    # 预检依赖与 key
    try:
        import openai  # noqa: F401
    except ImportError:
        print("\n[!] 缺 openai 库，正在安装…")
        subprocess.run([find_python(), "-m", "pip", "install", "openai",
                        "-i", "https://pypi.tuna.tsinghua.edu.cn/simple",
                        "--quiet", "--disable-pip-version-check"], check=False)

    sys.path.insert(0, str(HERE))
    from config import Config
    cfg = Config.from_env()
    if not cfg.ready:
        print("\n[!] 还没填 API key。")
        print(f"    打开这个文件填 X72_API_KEY：\n    {ENV_FILE}")
        pause()
        return 1

    print(f"  模型：{cfg.provider} / {cfg.model}")
    print("=" * 58)
    print("  直接输入中文说话；:state 看状态  :raw 看原始输出  :quit 退出")
    print("=" * 58 + "\n")

    # 起 main.py，把串口参数传过去
    cmd = [find_python(), str(HERE / "main.py"), "--port", port]
    try:
        return subprocess.call(cmd, cwd=str(HERE))
    except KeyboardInterrupt:
        return 0
    finally:
        print("\n小72 已退出。")


if __name__ == "__main__":
    try:
        code = main()
    except Exception as e:
        print(f"\n[启动失败] {type(e).__name__}: {e}")
        pause()
        code = 1
    pause()
    sys.exit(code)
