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

# voice/ 里同样用扁平 import（from trigger import ...）
VOICE_DIR = Path(__file__).resolve().parent
if str(VOICE_DIR) not in sys.path:
    sys.path.insert(0, str(VOICE_DIR))

import numpy as np  # noqa: E402

from trigger import AutoTrigger, Trigger  # noqa: E402
from tts import TtsService  # noqa: E402
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
    audio_s: float = 0.0            # 这一轮实际送进 ASR 的音频长度（秒）
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
        audio_note = f"（音频 {self.audio_s:.1f}s）" if self.audio_s else ""
        parts.append(
            f"耗时：ASR {self.t_asr:.2f}s + 意图 {self.t_intent:.2f}s "
            f"+ 下发 {self.t_act:.2f}s = {self.t_total:.2f}s{audio_note}"
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
                 verbose: bool = False,
                 device: str | None = None,
                 max_utterance_ms: int = 20000,
                 trigger: Trigger | None = None):
        self.model_name = model
        self.asr_device = asr_device
        self.compute_type = compute_type
        self.model_dir = model_dir
        self.audio_device = audio_device
        self.port = port
        self.device = device          # 期望的设备身份（id 或 model 片段）
        self.device_info = None       # 握手拿到的身份信息
        self.dry_run = dry_run
        self.language = language
        self.silence_end_ms = silence_end_ms
        self.timeout = timeout
        self.max_utterance_ms = max_utterance_ms
        self.trigger: Trigger = trigger or AutoTrigger()
        # 触发后等待语音的时长：由触发器决定（空格=8s，自动=timeout）
        self.listen_timeout = float(self.trigger.timeout_hint)
        self.use_llm = use_llm
        self.verbose = verbose

        self.recorder = None
        self.asr = None
        self.llm = None
        self.rule = None
        self.state = LedState(0, 0)
        self.link = None
        self.tts = None
        self.runtime = None          # UI 版会注入；无 UI 时保持 None

        self.turns = 0
        self.ok = 0
        self.unknown = 0
        self.errors = 0
        self.degraded_count = 0

    # ================================================================
    #  串口发现（靠握手，不靠 COM 号）
    # ================================================================
    def _discover_port(self) -> str | None:
        """遍历串口逐个发 `[I?]`，按设备自报的身份找到它。

        为什么不能写死 COM 号：
            CH340 这类芯片没有 USB 序列号，COM 号随插拔顺序变化
            （本机实测从 COM8 变成过 COM11）。
            设备自己报名是唯一稳定的办法。

        选择规则：
            · 指定了 self.device → 按 id / model 片段匹配（大小写不敏感）
            · 未指定 → 只有**恰好一个**设备应答时才采用；
              多个应答则列出并拒绝猜，避免控制到错误的板子。
        """
        print("      按设备身份发现（遍历串口发 [I?]，不依赖 COM 号）…")
        try:
            from device_id import scan_ports
        except Exception as e:
            print(f"      [WARN] 无法导入 device_id：{e}")
            return None

        try:
            hits = scan_ports()
        except Exception as e:
            print(f"      [WARN] 扫描串口失败：{e}")
            return None

        if not hits:
            print("      没有任何设备回应握手。可能原因：")
            print("        · 板子没上电 / 串口被占用")
            print("        · 固件较老，没有 [I?] 应答（需 `[I?]` 版本固件）")
            print("      可用 --port COMx 手动指定端口")
            return None

        def desc(d):
            return (f"{d['port']}  {d.get('model','?')}  "
                    f"id={d.get('id','?')}  fw={d.get('firmware','?')}")

        # 指定身份 → 过滤
        if self.device:
            key = self.device.lower()
            matched = [d for d in hits
                       if key in str(d.get("id", "")).lower()
                       or key in str(d.get("model", "")).lower()]
            if not matched:
                print(f"      未找到身份匹配 {self.device!r} 的设备。当前在线的有：")
                for d in hits:
                    print(f"        {desc(d)}")
                return None
            hits = matched

        if len(hits) > 1:
            print(f"      发现 {len(hits)} 个设备，为避免控制错板子，请用 --device 指定：")
            for d in hits:
                print(f"        {desc(d)}")
            return None

        self.device_info = hits[0]
        d = hits[0]
        print(f"      发现设备：{d['port']}  {d.get('model','?')}  "
              f"id={d.get('id','?')}  fw={d.get('firmware','?')}")
        print(f"      能力：{','.join(d.get('capabilities') or [])}")
        return d["port"]

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
        else:
            # port 为 None 或 "auto" 时：靠握手认设备，不认 COM 号
            if self.port is None or str(self.port).lower() == "auto":
                self.port = self._discover_port()

            if self.port:
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
                print("      未找到设备 → DRY-RUN（只打印帧）")

        # --- 语音播报 ---
        try:
            self.tts = TtsService()
            print("\n[TTS] %s" % self.tts.cfg.describe())
        except Exception as e:
            self.tts = None
            print("\n[TTS] 初始化失败（%s），将不播报" % type(e).__name__)

        print("\n" + "-" * 72)
        print("  准备好了。说完话停顿约 %.1f 秒自动识别。" % (self.silence_end_ms / 1000))
        print("  Ctrl+C 退出")
        print("-" * 72)

    # ================================================================
    #  单轮
    # ================================================================
    def _state(self, v: str) -> None:
        """给 UI 报状态；没有 UI 时什么都不做。"""
        rt = getattr(self, "runtime", None)
        if rt is not None:
            try:
                rt.set_state(v)
            except Exception:
                pass

    def _emit(self, event: dict) -> None:
        rt = getattr(self, "runtime", None)
        if rt is not None:
            try:
                rt.emit(event)
            except Exception:
                pass

    def _on_level(self, rms: float) -> None:
        rt = getattr(self, "runtime", None)
        if rt is not None:
            try:
                rt.emit({"t": "level", "v": round(min(1.0, rms * 6.0), 3)})
            except Exception:
                pass

    def _cancelled(self) -> bool:
        rt = getattr(self, "runtime", None)
        return bool(rt is not None and rt.cancel_flag.is_set())

    def listen(self) -> np.ndarray:
        """等一句话，返回音频（16k float32）。超时返回空数组。"""
        held = getattr(self.trigger, "held", None)
        return self.recorder.record_utterance(
            timeout=self.listen_timeout,
            silence_end_ms=self.silence_end_ms,
            max_utterance_ms=self.max_utterance_ms,
            stop_when=held,
            tail_ms=250,
            no_speech_ms=5000,
            on_level=self._on_level,
        )

    def _context(self) -> str:
        """把当前灯状态作为上下文喂给模型，闲聊时也能回答「现在多亮」。"""
        st = self.state
        return "亮度 %d%%，周期 %dms" % (st.brightness, st.period_ms)

    def route_text(self, text: str):
        """文字 → (intent | None, 聊天文本, 是否降级)。

        LLM 走 tool calling：调工具就是命令，直接回话就是聊天。
        LLM 失败时退回规则版（只能识别命令，聊天退化成"没听懂"）。
        """
        if self.llm is not None:
            try:
                rep = self.llm.route(text, context=self._context())
                if rep.intent is not None:
                    return rep.intent, "", False
                return None, rep.text, False
            except IntentError as e:
                if self.verbose:
                    print(f"      [LLM 失败] {str(e)[:80]}")
            except Exception as e:
                if self.verbose:
                    print(f"      [LLM 异常] {type(e).__name__}")

        if self.rule is not None:
            it = self.rule.parse(text)
            if getattr(it, "cmd", "unknown") == "unknown":
                return None, (getattr(it, "say", "") or "没听懂"), True
            return it, "", True

        raise RuntimeError("没有可用的意图识别后端")

    def understand(self, text: str) -> tuple[object, bool]:
        """兼容旧接口：返回 (Intent, 是否降级)，聊天包装成 cmd=chat。"""
        intent, chat_text, degraded = self.route_text(text)
        if intent is not None:
            return intent, degraded
        return Intent(cmd="chat", say=chat_text), degraded

    def act(self, intent) -> tuple[str, list[str]]:
        """意图 → 帧 → 下发。返回 (帧, 变化字段)。"""
        cmd = getattr(intent, "cmd", "unknown")
        changed = self.state.apply(
            cmd, getattr(intent, "brightness", None), getattr(intent, "period_ms", None)
        )
        frame = self.state.encode()

        # unknown / chat 不动硬件：不发送，保持原状态
        if cmd in ("unknown", "chat"):
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
            intent, chat_text, degraded = self.route_text(text)
        except Exception as e:
            r.error = f"意图识别失败：{e}"
            self.errors += 1
            return r
        r.t_intent = time.time() - t0
        r.degraded = degraded
        if degraded:
            self.degraded_count += 1

        # ---- 纯粹聊天：不碰硬件，只说一句话 ----
        if intent is None:
            r.cmd = "chat"
            r.say = chat_text
            r.t_total = r.t_intent
            self.ok += 1
            return self._finish(r)

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
        return self._finish(r)

    def _finish(self, r: TurnResult) -> TurnResult:
        """播报 + 上报 UI。

        **文字在播报之前就发出去**：这样用户打断播报时，全文已经在屏幕上，
        不需要等声音放完才知道说了什么。
        """
        # 先让 TTS 在后台逐句合成，文字再发出去 —— 打字和合成并行
        items = []
        if self.tts is not None and r.say:
            try:
                items = self.tts.prepare_chunks(r.say)
            except Exception:
                items = []

        t_emit = time.time()
        self._emit({"t": "reply", "text": r.say, "cmd": r.cmd})
        self._emit({"t": "metrics",
                    "asr": round(r.t_asr, 2), "intent": round(r.t_intent, 2),
                    "act": round(r.t_act, 2), "total": round(r.t_total, 2),
                    "audio_s": round(r.audio_s, 1)})

        if items:
            rt = getattr(self, "runtime", None)
            stop_ev = rt.interrupt_flag if rt is not None else None
            self._state("speaking")

            first_ms = -1
            played = 0
            for i, (_, job) in enumerate(items):
                try:
                    job.result(timeout=30)          # 等这一句合成好
                except Exception:
                    break
                if first_ms < 0:
                    first_ms = int((time.time() - t_emit) * 1000)
                if stop_ev is not None and stop_ev.is_set():
                    break
                if not self.tts.play(job, stop_ev):
                    break
                played += 1

            self._emit({"t": "tts", "first_ms": first_ms,
                        "chunks": len(items), "played": played})
            r.t_total += time.time() - t_emit

        self._state("idle")
        self._emit({"t": "stats", "turns": self.turns, "ok": self.ok,
                    "unknown": self.unknown, "errors": self.errors,
                    "degraded": self.degraded_count})
        return r

    def handle_once(self) -> TurnResult | None:
        """听一句 → 处理。没听到语音返回 None。"""
        self._state("recording")
        t0 = time.time()
        audio = self.listen()
        t_vad = time.time() - t0

        if self._cancelled():
            self._state("idle")
            return None

        if audio.size == 0:
            self._state("idle")
            return None

        audio_s = audio.size / 16000.0
        self._state("thinking")

        t1 = time.time()
        try:
            asr_res = self.asr.transcribe(audio, language=self.language)
        except Exception as e:
            self.errors += 1
            self._state("idle")
            return TurnResult(error=f"ASR 失败：{e}", audio_s=audio_s)
        t_asr = time.time() - t1

        text = (asr_res.text or "").strip()
        self._emit({"t": "asr", "text": text, "secs": round(t_asr, 2),
                    "audio_s": round(audio_s, 2)})

        # ASR 期间按了 Esc：不发 API，直接丢弃
        if self._cancelled():
            self._state("cancelled")
            return TurnResult(text=text, error="已取消", audio_s=audio_s)

        if not text:
            self.errors += 1
            self._state("idle")
            return TurnResult(error="ASR 返回空文本", audio_s=audio_s)

        r = self.handle_text(text)
        r.t_vad = t_vad
        r.t_asr = t_asr
        r.audio_s = audio_s
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
                hint = self.trigger.describe()
                if hint:
                    print(hint)

                if not self.trigger.wait():
                    print("\n收到退出指令，结束。")
                    break

                if self.trigger.name != "auto":
                    print("  正在听……（%.0f 秒内没听到就取消）" % self.listen_timeout)

                r = self.handle_once()

                if r is None:
                    print("  没听到语音，回到等待")
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
        if self.tts is not None:
            try:
                self.tts.close()
            except Exception:
                pass
            self.tts = None
