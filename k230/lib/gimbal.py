"""云台（pan / tilt）跟踪控制器。

把「目标相对画面中心的角误差」变成舵机位置指令：

    yaw_err, pitch_err  --PID-->  归一化角速度  --积分-->  舵机位置

采用增量式（速度型）控制，而不是直接给绝对位置：
这样做对视觉延迟、舵机型号差异更宽容，也避免了位置环与视觉环互相打架。

纯 Python，兼容 MicroPython。
"""


class PanTiltController(object):
    def __init__(self, pan_pid, tilt_pid,
                 pan_center=2048, tilt_center=2048,
                 pan_range=(0, 4095), tilt_range=(0, 4095),
                 pan_dir=1, tilt_dir=1,
                 max_rate_ticks_per_s=1500.0):
        self.pan_pid = pan_pid
        self.tilt_pid = tilt_pid
        self.pan_center = pan_center
        self.tilt_center = tilt_center
        self.pan_range = pan_range
        self.tilt_range = tilt_range
        self.pan_dir = 1 if pan_dir >= 0 else -1
        self.tilt_dir = 1 if tilt_dir >= 0 else -1
        self.max_rate = float(max_rate_ticks_per_s)

        self.pan = pan_center
        self.tilt = tilt_center

    def _clamp_axis(self, value, rng):
        if value < rng[0]:
            return rng[0]
        if value > rng[1]:
            return rng[1]
        return value

    def update(self, yaw_error, pitch_error, dt):
        """输入角误差（弧度，右/下为正），返回 (pan, tilt) 目标位置。"""
        u = self.pan_pid.update(yaw_error, dt) * self.pan_dir
        v = self.tilt_pid.update(pitch_error, dt) * self.tilt_dir

        self.pan += u * self.max_rate * dt
        self.tilt += v * self.max_rate * dt

        self.pan = self._clamp_axis(self.pan, self.pan_range)
        self.tilt = self._clamp_axis(self.tilt, self.tilt_range)
        return (int(self.pan), int(self.tilt))

    def reset(self, pan=None, tilt=None):
        self.pan = self.pan_center if pan is None else pan
        self.tilt = self.tilt_center if tilt is None else tilt
        self.pan_pid.reset()
        self.tilt_pid.reset()
        return (int(self.pan), int(self.tilt))

    def at_limit(self):
        """是否顶到机械限位（可用于提示或降速）。"""
        return {
            "pan": self.pan <= self.pan_range[0] or self.pan >= self.pan_range[1],
            "tilt": self.tilt <= self.tilt_range[0] or self.tilt >= self.tilt_range[1],
        }
