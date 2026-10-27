"""算力分时状态机。

K230 的 KPU 是独占资源：人脸、YOLO、关键词唤醒不能同时满帧跑。
用状态机明确「当前该跑哪个模型、多少帧」，而不是靠零散的 if 判断。

模式与模型的对应关系（对应可行性文档 2.3 节）：

    idle       不占 KPU，只跑固件里的 KWS（open_kws）与低帧率人脸检测
    tracking   跑人脸检测/识别，高帧率，喂云台
    scanning   跑 YOLOv8，低帧率，做物品登记
    monitoring 只编码推流，不跑模型

纯 Python，兼容 MicroPython。
"""


class Mode(object):
    def __init__(self, name, model=None, fps=0, desc=""):
        self.name = name
        self.model = model
        self.fps = fps
        self.desc = desc

    def __repr__(self):
        return "Mode(%s, model=%r, fps=%r)" % (self.name, self.model, self.fps)


class ModeMachine(object):
    def __init__(self, modes, transitions, initial,
                 timeouts=None, fallback="idle"):
        """modes: [Mode]；transitions: {state: {event: next_state}}。"""
        self.modes = {}
        for m in modes:
            self.modes[m.name] = m
        if initial not in self.modes:
            raise ValueError("unknown initial mode: %s" % initial)
        self.transitions = transitions
        self.current = initial
        self.timeouts = timeouts or {}
        self.fallback = fallback
        self.entered_at = 0.0
        self.last_ts = 0.0

    def mode(self):
        return self.modes[self.current]

    def active_model(self):
        return self.modes[self.current].model

    def trigger(self, event, ts=None):
        """尝试一次状态转移。成功返回 (old, new)，否则返回 None。"""
        targets = self.transitions.get(self.current, {})
        nxt = targets.get(event)
        if nxt is None or nxt not in self.modes:
            return None
        old = self.current
        self.current = nxt
        if ts is not None:
            self.entered_at = ts
        return (old, nxt)

    def tick(self, ts):
        """推进时间；超时则回落到 fallback。返回 (old, new) 或 None。"""
        self.last_ts = ts
        limit = self.timeouts.get(self.current)
        if limit is None:
            return None
        if ts - self.entered_at < limit:
            return None
        old = self.current
        self.current = self.fallback
        self.entered_at = ts
        return (old, self.fallback)

    def dwell(self, ts):
        return ts - self.entered_at

    def snapshot(self):
        m = self.mode()
        return {
            "mode": m.name,
            "model": m.model,
            "fps": m.fps,
            "dwell_s": round(self.last_ts - self.entered_at, 3),
        }


MODE_IDLE = "idle"
MODE_TRACKING = "tracking"
MODE_SCANNING = "scanning"
MODE_MONITORING = "monitoring"


def default_machine():
    """本项目默认的分时策略。"""
    modes = [
        Mode(MODE_IDLE, model=None, fps=5, desc="待机：KWS + 低频人脸探测"),
        Mode(MODE_TRACKING, model="face_detect", fps=25, desc="人脸跟踪，喂云台"),
        Mode(MODE_SCANNING, model="yolov8", fps=10, desc="物品扫描与登记"),
        Mode(MODE_MONITORING, model=None, fps=25, desc="只推流监控"),
    ]
    transitions = {
        MODE_IDLE: {
            "wake": MODE_TRACKING,
            "scan": MODE_SCANNING,
            "monitor": MODE_MONITORING,
        },
        MODE_TRACKING: {
            "face_lost": MODE_IDLE,
            "scan": MODE_SCANNING,
            "monitor": MODE_MONITORING,
        },
        MODE_SCANNING: {
            "done": MODE_IDLE,
            "wake": MODE_TRACKING,
            "monitor": MODE_MONITORING,
        },
        MODE_MONITORING: {
            "wake": MODE_TRACKING,
            "scan": MODE_SCANNING,
        },
    }
    timeouts = {
        MODE_TRACKING: 8.0,    # 8 秒没确认目标就回待机
        MODE_SCANNING: 30.0,   # 单次扫描最多 30 秒
    }
    return ModeMachine(modes, transitions, MODE_IDLE, timeouts, MODE_IDLE)
