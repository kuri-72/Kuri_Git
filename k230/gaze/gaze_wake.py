# -*- coding: utf-8 -*-
"""
小72 · 注视唤醒（正式版）
================================
板子：立创·庐山派 K230-CanMV（1G）
灯  ：RGB 三路独立 GPIO，低电平点亮   R=62  G=20  B=63
按键：GPIO53（下拉，按下为高）

行为
----
1. 待机：绿灯常亮。持续跑人脸检测 + 注视估计。
2. 判定：连续 2 帧落在阈值内 → 认为是"看向我"。
        阈值来自实测（看镜头 vs 看屏幕 vs 看左右），见 TH_PITCH / TH_YAW。
3. 唤醒：串口打印一行 `W`，绿灯改成呼吸。
        **笔记本收到 W 之后才开始它的流程**：
          · 麦克风本来就一直在录，写进 1.5 秒环形缓冲
          · 收到 W 只是"准备"，不录音
          · 真正录不录，取决于之后 1 秒内有没有人声
          · 有人声 → 快照缓冲 + 继续录；没人声 → 忽略这次唤醒
        这样即使把路人照进来误触发，也只是灯亮一下，不会真的开始录。
4. 超时：唤醒后 10 秒没人说话 → 闪两下 → 回待机。

串口输出
--------
    W                 唤醒（只发一次）
    G,pitch,yaw,face,ts   每 5 帧一行的调试数据（可关）
    TIMEOUT           10 秒超时（便于笔记本对齐）

注意
----
· 没有硬件 PWM 落在 GPIO20 上，呼吸用软件 PWM（独立线程）。
· 线程失败会自动降级成常亮，不影响唤醒本身。
"""

import os
import sys
import time
import math
import gc
import _thread

from media.media import *
import nncase_runtime as nn
import ulab.numpy as np
import image
import aidemo

from libs.PipeLine import PipeLine
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *

from machine import Pin


# ============================================================ 参数
# 阈值：实测"看镜头"时 pitch≈-0.03、yaw≈-0.13
TH_PITCH_LO, TH_PITCH_HI = -0.25, 0.20
TH_YAW_LO, TH_YAW_HI = -0.30, 0.00

CONFIRM_FRAMES = 2          # 连续多少帧满足才唤醒（3.9fps 下约 0.5s）
AWAKE_TIMEOUT_MS = 10000    # 唤醒后多久没人说话就退回
DEBUG_G = True              # 是否打印 G 调试行


# ============================================================ 指示灯
class Led:
    """板载 RGB，低电平点亮；绿灯支持软件 PWM 呼吸。"""

    R, G, B = 62, 20, 63

    def __init__(self):
        self.r = Pin(self.R, Pin.OUT, pull=Pin.PULL_NONE, drive=7)
        self.g = Pin(self.G, Pin.OUT, pull=Pin.PULL_NONE, drive=7)
        self.b = Pin(self.B, Pin.OUT, pull=Pin.PULL_NONE, drive=7)
        self.duty = 100          # 0..100
        self._run = True
        self._thread_ok = False
        self.off()

    def _one(self, pin, on):
        pin.value(0 if on else 1)

    def off(self):
        self._one(self.r, False)
        self._one(self.g, False)
        self._one(self.b, False)

    def green(self):
        self._one(self.r, False)
        self._one(self.g, True)
        self._one(self.b, False)

    def _pwm(self):
        """软件 PWM：10ms 周期，1ms 粒度。失败不影响主流程。"""
        try:
            while self._run:
                d = self.duty
                if d <= 0:
                    self._one(self.g, False)
                    time.sleep_ms(8)
                    continue
                if d >= 100:
                    self._one(self.g, True)
                    time.sleep_ms(8)
                    continue
                on_ms = d // 10
                off_ms = 10 - on_ms
                if on_ms > 0:
                    self._one(self.g, True)
                    time.sleep_ms(on_ms)
                if off_ms > 0:
                    self._one(self.g, False)
                    time.sleep_ms(off_ms)
        except Exception:
            self._thread_ok = False

    def start(self):
        try:
            _thread.start_new_thread(self._pwm, ())
            self._thread_ok = True
        except Exception:
            self._thread_ok = False
            self.green()

    def set_duty(self, d):
        self.duty = max(0, min(100, int(d)))
        if not self._thread_ok:
            if self.duty > 30:
                self._one(self.g, True)
            else:
                self._one(self.g, False)


# ============================================================ 人脸检测
class FaceDetApp(AIBase):
    def __init__(self, kmodel_path, model_input_size, anchors,
                 confidence_threshold=0.25, nms_threshold=0.3,
                 rgb888p_size=[640, 360], display_size=[640, 360], debug_mode=0):
        super().__init__(kmodel_path, model_input_size, rgb888p_size, debug_mode)
        self.kmodel_path = kmodel_path
        self.model_input_size = model_input_size
        self.confidence_threshold = confidence_threshold
        self.nms_threshold = nms_threshold
        self.anchors = anchors
        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0], 16), rgb888p_size[1]]
        self.display_size = [ALIGN_UP(display_size[0], 16), display_size[1]]
        self.debug_mode = debug_mode
        self.ai2d = Ai2d(debug_mode)
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT,
                                 np.uint8, np.uint8)

    def config_preprocess(self, input_image_size=None):
        with ScopedTiming("set preprocess config", self.debug_mode > 0):
            ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size
            top, bottom, left, right, _ = letterbox_pad_param(self.rgb888p_size,
                                                              self.model_input_size)
            self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [114, 114, 114])
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            self.ai2d.build([1, 3, ai2d_input_size[1], ai2d_input_size[0]],
                            [1, 3, self.model_input_size[1], self.model_input_size[0]])

    def postprocess(self, results):
        with ScopedTiming("postprocess", self.debug_mode > 0):
            res = aidemo.face_det_post_process(self.confidence_threshold, self.nms_threshold,
                                               self.model_input_size[0], self.anchors,
                                               self.rgb888p_size, results)
            if len(res) == 0:
                return res
            return res[0]


# ============================================================ 注视估计
class EyeGazeApp(AIBase):
    def __init__(self, kmodel_path, model_input_size,
                 rgb888p_size=[640, 360], display_size=[640, 360], debug_mode=0):
        super().__init__(kmodel_path, model_input_size, rgb888p_size, debug_mode)
        self.kmodel_path = kmodel_path
        self.model_input_size = model_input_size
        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0], 16), rgb888p_size[1]]
        self.display_size = [ALIGN_UP(display_size[0], 16), display_size[1]]
        self.debug_mode = debug_mode
        self.ai2d = Ai2d(debug_mode)
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT,
                                 np.uint8, np.uint8)

    def config_preprocess(self, det, input_image_size=None):
        with ScopedTiming("set preprocess config", self.debug_mode > 0):
            ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size
            x, y, w, h = map(lambda v: int(round(v, 0)), det[:4])
            self.ai2d.crop(x, y, w, h)
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            self.ai2d.build([1, 3, ai2d_input_size[1], ai2d_input_size[0]],
                            [1, 3, self.model_input_size[1], self.model_input_size[0]])

    def postprocess(self, results):
        with ScopedTiming("postprocess", self.debug_mode > 0):
            post_ret = aidemo.eye_gaze_post_process(results)
            return post_ret[0], post_ret[1]


# ============================================================ 组合
class EyeGaze:
    def __init__(self, face_det_kmodel, eye_gaze_kmodel, det_input_size,
                 eye_gaze_input_size, anchors, confidence_threshold=0.25,
                 nms_threshold=0.3, rgb888p_size=[640, 360], debug_mode=0):
        self.face_det = FaceDetApp(face_det_kmodel, det_input_size, anchors,
                                   confidence_threshold, nms_threshold,
                                   rgb888p_size, rgb888p_size, debug_mode)
        self.eye_gaze = EyeGazeApp(eye_gaze_kmodel, eye_gaze_input_size,
                                   rgb888p_size, rgb888p_size, debug_mode)
        self.face_det.config_preprocess()

    def run(self, img):
        dets = self.face_det.run(img)
        if len(dets) != 1:          # 没人脸 / 多张脸都不判断，避免误唤醒
            return 0, 0.0, 0.0, 0
        self.eye_gaze.config_preprocess(dets[0])
        pitch, yaw = self.eye_gaze.run(img)
        return 1, float(pitch), float(yaw), 1


# ============================================================ 主程序
def main():
    led = Led()
    led.start()
    led.set_duty(100)            # 待机：常亮

    face_det_kmodel_path = "/sdcard/examples/kmodel/face_detection_320.kmodel"
    eye_gaze_kmodel_path = "/sdcard/examples/kmodel/eye_gaze.kmodel"
    anchors_path = "/sdcard/examples/utils/prior_data_320.bin"

    rgb888p_size = [640, 360]
    face_det_input_size = [320, 320]
    eye_gaze_input_size = [448, 448]
    confidence_threshold = 0.5
    nms_threshold = 0.2
    anchor_len = 4200
    det_dim = 4

    anchors = np.fromfile(anchors_path, dtype=np.float)
    anchors = anchors.reshape((anchor_len, det_dim))

    pl = PipeLine(rgb888p_size=rgb888p_size, display_mode="virt",
                  display_size=rgb888p_size)
    pl.create()

    eg = EyeGaze(face_det_kmodel_path, eye_gaze_kmodel_path,
                 det_input_size=face_det_input_size,
                 eye_gaze_input_size=eye_gaze_input_size,
                 anchors=anchors,
                 confidence_threshold=confidence_threshold,
                 nms_threshold=nms_threshold,
                 rgb888p_size=rgb888p_size)

    print("# gaze_wake 启动：待机中（绿灯常亮）")

    STANDBY, AWAKE = 0, 1
    state = STANDBY
    hit = 0
    awake_at = 0
    frame = 0
    t0 = time.ticks_ms()

    try:
        while True:
            img = pl.get_frame()
            _n, pitch, yaw, valid = eg.run(img)
            ts = time.ticks_ms() - t0

            in_box = (valid and
                      TH_PITCH_LO <= pitch <= TH_PITCH_HI and
                      TH_YAW_LO <= yaw <= TH_YAW_HI)

            if state == STANDBY:
                hit = hit + 1 if in_box else 0

                if hit >= CONFIRM_FRAMES:
                    state = AWAKE
                    awake_at = ts
                    hit = 0
                    led.set_duty(45)          # 呼吸（由线程按正弦调）
                    print("W")                # ← 唤醒信号
                    if DEBUG_G:
                        print("# awake pitch=%.3f yaw=%.3f" % (pitch, yaw))

            else:  # AWAKE
                # 呼吸：用主循环的帧率推正弦，线程只负责执行占空比
                phase = (ts - awake_at) / 1000.0
                led.set_duty(45 + 45 * math.sin(phase * 3.0))

                if ts - awake_at > AWAKE_TIMEOUT_MS:
                    print("TIMEOUT")
                    led.set_duty(0)
                    time.sleep_ms(120)
                    led.set_duty(100)
                    time.sleep_ms(120)
                    led.set_duty(0)
                    time.sleep_ms(120)
                    led.set_duty(100)
                    state = STANDBY
                    hit = 0

            if DEBUG_G and frame % 5 == 0:
                print("G,%.4f,%.4f,%d,%d" % (pitch, yaw, valid, ts))

            frame += 1
            if frame % 25 == 0:
                gc.collect()

    except KeyboardInterrupt:
        print("# stop")
    finally:
        led.set_duty(0)
        led.off()
        eg.face_det.deinit()
        eg.eye_gaze.deinit()
        pl.destroy()
        print("# bye")


main()
