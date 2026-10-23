"""
小72 · 语音闭环流水线
=======================
把已经做好的四块串起来：

    麦克风 → VAD 切句 → ASR 转文字 → 意图识别 → 协议帧 → 串口 → 单片机 → 灯

设计原则：
  1. **复用，不重写**
     intent / state / serial 都是灯控阶段已经验证过的模块，这里只 import。
  2. **意图层可降级**
     LLM 调用失败（断网/限流/超时）自动退回离线规则版，
     保证"至少能认调亮/调暗/关灯/呼吸"。
  3. **unknown 不改变硬件**
     听不懂就什么都不发，灯保持原样。这是安全底线。
  4. **每轮打印耗时拆解**
     方便判断延迟瓶颈在 VAD、ASR 还是 LLM。
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# host/ 里的模块用的是扁平 import（from config import ...），需要把目录加进 sys.path
HOST_DIR = Path(__file__).resolve().parent.parent / "host"
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

import numpy as np  # noqa: E402

from state import LedState  # noqa: E402
from serial_link import SerialLink  # noqa: E402

try:
    from intent import Intent, IntentError, IntentParser, MockParser  # noqa: E402
except Exception:  # pragma: no cover
    Intent = object  # type: ignore
    IntentError = Exception  # type: ignore
    IntentParser = None  # type: ignore
    MockParser = None  # type: ignore


@dataclass
class TurnResult:
    """一轮交互的完整记录。"""
    text: str = ""
    say: str = ""
    cmd: str = ""
    frame: str = ""
    changed: list[str] = field(default_factory=list)
    degraded: bool = False          # 是否用了规则版兜底
    error: str = ""
    t_vad: float = 0.0              # 从开始等到切出一句（含用户说话时间）
    t_asr: float = 0.0
    t_intent: float = 0.0
    t_act: float = 0.0              # 生成帧 + 串口下发
    t_total: float = 0.0            # ASR + 意图 + 下发（不含等待用户说话）

    def summary(self) -> str:
        parts = [
            f"你说：{self.text or '(空)'}",
            f"小72：{self.say or '(沉默)'}",
            f"帧  ：{self.frame or '(未发送)'}",
        ]
        if self.changed:
            parts.append(f"变化：{','.join(self.changed)}")
        if self.degraded:
            parts.append("注：LLM 不可用，用的规则版")
        if self.error:
            parts.append(f"错误：{self.error}")
        parts.append(
            f"耗时：ASR {self.t_asr:.2f}s + 意图 {self.t_intent:.2f}s "
            f"+ 下发 {self.t_act:.2f}s = {self.t_total:.2f}s"
        )
        return "\n".join(parts)


class VoiceAssistant:
    """语音闭环。

    用法：
        a = VoiceAssistant(port="COM8")
        a.run()                 # 一直听
    """

    def __init__(self,
                 model: str = "small",
                 asr_device: str = "cpu",
                 compute_type: str = "int8",
                 model_dir: str | None = None,
                 audio_device: str | int | None = None,
                 port: str | None = "COM8",
                 dry_run: bool = False,
                 language: str = "zh",
                 silence_end_ms: int = 1200,
                 timeout: float = 30.0,
                 use_llm: bool = True,
                 verbose: bool = False):
        self.model_name = model
        self.asr_device = asr_device
        self.compute_type = compute_type
        self.model_dir = model_dir
        self.audio_device = audio_device
        self.port = port
        self.dry_run = dry_run
        self.language = language
        self.silence_end_ms = silence_end_ms
        self.timeout = timeout
        self.use_llm = use_llm
        self.verbose = verbose

        self.recorder = None
        self.asr = None
        self.llm = None
        self.rule = None
        self.state = LedState(0, 0)
        self.link = None

        self.turns = 0
        self.ok = 0
        self.unknown = 0
        self.errors = 0
        self.degraded_count = 0

    # ================================================================
    #  初始化
    # ================================================================
    def setup(self) -> None:
        from voice.asr import create_provider
        from voice.audio import Recorder

        print("=" * 72)
        print("  小72 · 语音闭环")
        print("=" * 72)

        # --- 麦克风 ---
        print("\n[1/4] 麦克风")
        self.recorder = Recorder(device=self.audio_device)
        print(f"      {self.recorder.info()}")

        # --- ASR ---
        print(f"\n[2/4] 语音识别（{self.model_name} / {self.asr_device} / {self.compute_type}）")
        print("      正在加载模型，首次约 20 秒（读 464MB 模型文件），请稍候…")
        t0 = time.time()
        self.asr = create_provider(
            "faster-whisper",
            model_size=self.model_name,
            device=self.asr_device,
            compute_type=self.compute_type,
            model_dir=self.model_dir,
        )
        try:
            self.asr._ensure_model()  # noqa: SLF001
        except Exception as e:
            print(f"      [FAIL] 模型加载失败：{type(e).__name__}: {e}")
            raise
        print(f"      加载耗时 {time.time() - t0:.1f} 秒")

        # --- 意图层 ---
        print("\n[3/4] 意图识别")
        self.rule = MockParser() if MockParser else None
        if self.use_llm and IntentParser is not None:
            try:
                from config import Config

                cfg = Config.from_env()
                if cfg.ready:
                    self.llm = IntentParser(cfg)
                    print(f"      LLM：{cfg.provider} / {cfg.model}")
                else:
                    print("      LLM：未配置 API key → 只用规则版")
            except Exception as e:
                print(f"      LLM 初始化失败（{type(e).__name__}）→ 只用规则版")
        else:
            print("      只用规则版（离线）")

        # --- 串口 ---
        print("\n[4/4] 串口")
        if self.dry_run:
            print("      DRY-RUN：只打印帧，不发送")
        elif self.port:
            try:
                self.link = SerialLink(self.port, 115200, timeout=0.5).open()
                print(f"      {self.port} 已连接")
            except Exception as e:
                print(f"      [WARN] 打开 {self.port} 失败：{e}")
                print("             常见原因：串口助手占用 / 板子没插")
                print("             将进入 DRY-RUN 模式（只打印帧）")
                self.dry_run = True
        else:
            self.dry_run = True
            print("      未指定端口 → DRY-RUN")

        print("\n" + "-" * 72)
        print("  准备好了。说完话停顿约 %.1f 秒自动识别。" % (self.silence_end_ms / 1000))
        print("  Ctrl+C 退出")
        print("-" * 72)

    # ================================================================
    #  单轮
    # ================================================================
    def listen(self) -> np.ndarray:
        """等一句话，返回音频（16k float32）。超时返回空数组。"""
        return self.recorder.record_utterance(
            timeout=self.timeout, silence_end_ms=self.silence_end_ms
        )

    def understand(self, text: str) -> tuple[object, bool]:
        """文字 → 意图。返回 (Intent, 是否降级)。

        先试 LLM；失败自动退回规则版。
        """
        if self.llm is not None:
            try:
                return self.llm.parse(text), False
            except IntentError as e:
                if self.verbose:
                    print(f"      [LLM 失败] {str(e)[:80]}")
            except Exception as e:
                if self.verbose:
                    print(f"      [LLM 异常] {type(e).__name__}")

        if self.rule is not None:
            return self.rule.parse(text), True

        raise RuntimeError("没有可用的意图识别后端")

    def act(self, intent) -> tuple[str, list[str]]:
        """意图 → 帧 → 下发。返回 (帧, 变化字段)。"""
        cmd = getattr(intent, "cmd", "unknown")
        changed = self.state.apply(
            cmd, getattr(intent, "brightness", None), getattr(intent, "period_ms", None)
        )
        frame = self.state.encode()

        # unknown 不动硬件：不发送，保持原状态
        if cmd == "unknown":
            return "", changed

        if self.dry_run or self.link is None:
            return frame, changed

        try:
            self.link.send(frame)
        except Exception as e:
            # 发送失败：尝试重连一次
            try:
                self.link.close()
                self.link = SerialLink(self.port, 115200).open()
                self.link.send(frame)
            except Exception as e2:
                raise RuntimeError(f"串口发送失败：{e} / 重连后仍失败：{e2}") from e2
        return frame, changed

    def handle_text(self, text: str) -> TurnResult:
        """处理一句已知文字（麦克风路径和 --text 模式共用）。"""
        r = TurnResult(text=text)

        t0 = time.time()
        try:
            intent, degraded = self.understand(text)
        except Exception as e:
            r.error = f"意图识别失败：{e}"
            self.errors += 1
            return r
        r.t_intent = time.time() - t0
        r.degraded = degraded
        if degraded:
            self.degraded_count += 1

        r.cmd = getattr(intent, "cmd", "unknown")
        r.say = getattr(intent, "say", "") or ""

        t1 = time.time()
        try:
            frame, changed = self.act(intent)
        except Exception as e:
            r.error = str(e)
            self.errors += 1
            return r
        r.frame = frame
        r.changed = changed
        r.t_act = time.time() - t1
        r.t_total = r.t_intent + r.t_act

        if r.cmd == "unknown":
            self.unknown += 1
        else:
            self.ok += 1
        return r

    def handle_once(self) -> TurnResult | None:
        """听一句 → 处理。没听到语音返回 None。"""
        t0 = time.time()
        audio = self.listen()
        t_vad = time.time() - t0

        if audio.size == 0:
            return None

        t1 = time.time()
        try:
            asr_res = self.asr.transcribe(audio, language=self.language)
        except Exception as e:
            self.errors += 1
            return TurnResult(error=f"ASR 失败：{e}")
        t_asr = time.time() - t1

        text = (asr_res.text or "").strip()
        if not text:
            self.errors += 1
            return TurnResult(error="ASR 返回空文本")

        r = self.handle_text(text)
        r.t_vad = t_vad
        r.t_asr = t_asr
        r.t_total += t_asr
        return r

    # ================================================================
    #  主循环
    # ================================================================
    def run(self) -> None:
        if self.recorder is None:
            self.setup()

        try:
            while True:
                print("\n" + "=" * 72)
                print("  正在听……（最多等 %.0f 秒）" % self.timeout)
                r = self.handle_once()

                if r is None:
                    print("  没听到语音，继续听")
                    continue

                self.turns += 1
                print(r.summary())
        except KeyboardInterrupt:
            print("\n\n收到 Ctrl+C，退出。")
        finally:
            self.print_stats()
            self.close()

    def run_text_mode(self) -> None:
        """不打麦克风，直接打字测试（调试意图层用）。"""
        if self.recorder is None:
            self.setup()

        print("\n文字模式：输入一句话测试，:quit 退出\n")
        try:
            while True:
                try:
                    text = input("> ").strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if not text:
                    continue
                if text in (":quit", ":q", "exit"):
                    break
                self.turns += 1
                print(self.handle_text(text).summary())
        finally:
            self.print_stats()
            self.close()

    def print_stats(self) -> None:
        print("\n" + "-" * 72)
        print(f"  本轮会话：{self.turns} 轮 / 执行 {self.ok} / 未听懂 {self.unknown} "
              f"/ 错误 {self.errors} / 降级 {self.degraded_count}")
        print(f"  当前灯状态：亮度 {self.state.brightness}%，周期 {self.state.period_ms}ms")
        print("-" * 72)

    def close(self) -> None:
        if self.link is not None:
            try:
                self.link.close()
            except Exception:
                pass
            self.link = None
        if self.asr is not None:
            try:
                self.asr.close()
            except Exception:
                pass
            self.asr = None
