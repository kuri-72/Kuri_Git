"""PID 控制器（带死区、积分限幅、输出限幅、斜率限制）。

为云台跟踪设计：输入是角度误差（弧度），输出是归一化控制量，
再由 gimbal.py 换算成舵机位置。纯 Python，兼容 MicroPython。
"""


class PID(object):
    def __init__(self, kp, ki=0.0, kd=0.0,
                 out_min=-1.0, out_max=1.0,
                 deadband=0.0, i_max=None, max_rate=None):
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)
        self.out_min = float(out_min)
        self.out_max = float(out_max)
        self.deadband = float(deadband)
        self.i_max = i_max
        self.max_rate = max_rate

        self.reset()

    def reset(self):
        self._integral = 0.0
        self._prev_error = None
        self._last_out = 0.0

    def _clamp(self, v, lo, hi):
        if v < lo:
            return lo
        if v > hi:
            return hi
        return v

    def update(self, error, dt):
        """error: 目标-当前；dt: 秒。返回控制量。"""
        if dt is None or dt <= 0.0:
            return self._last_out

        # 死区：小误差直接当 0，避免云台持续微抖
        if self.deadband > 0.0 and abs(error) < self.deadband:
            error = 0.0

        p_term = self.kp * error

        # 积分项（带限幅，防止积分饱和）
        self._integral += error * dt
        i_term = self.ki * self._integral
        if self.i_max is not None:
            if i_term > self.i_max:
                i_term = self.i_max
                if self.ki != 0.0:
                    self._integral = self.i_max / self.ki
            elif i_term < -self.i_max:
                i_term = -self.i_max
                if self.ki != 0.0:
                    self._integral = -self.i_max / self.ki

        if self._prev_error is None:
            d_term = 0.0
        else:
            d_term = self.kd * (error - self._prev_error) / dt
        self._prev_error = error

        out = p_term + i_term + d_term
        out = self._clamp(out, self.out_min, self.out_max)

        # 斜率限制：限制每个控制周期的变化量
        if self.max_rate is not None:
            step = self.max_rate * dt
            delta = out - self._last_out
            if delta > step:
                out = self._last_out + step
            elif delta < -step:
                out = self._last_out - step

        self._last_out = out
        return out

    def __repr__(self):
        return "PID(kp=%.3f, ki=%.3f, kd=%.3f)" % (self.kp, self.ki, self.kd)
