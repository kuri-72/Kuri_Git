# -*- coding: utf-8 -*-
"""
小72 · 注视数据采集（标定版）
================================
目标：只输出原始 pitch/yaw，不做任何判定。用真实数据定阈值。

硬件：立创·庐山派 K230-CanMV（1G）
  RGB 灯（低电平点亮）: R=GPIO62  G=GPIO20  B=GPIO63
  用户按键: GPIO53

用法：
  1. 把本文件保存到 /sdcard/gaze_stream.py
  2. 在 CanMV IDE 里运行（分辨率 640x360，约 4 fps）
  3. 【每做一个动作前，按一下板上的用户按键 GPIO53】，
     日志里会写一行 #MARK n，用于精确切分动作段
  4. 动作顺序（每个 5 秒）：
         看镜头 → 看屏幕正中 → 看左 → 看右 → 低头看键盘
  5. 结束后数据写到 /sdcard/gaze_log.csv

输出（串口 + 文件）：
  G,<pitch>,<yaw>,<face>,<ts_ms>
      face=1 表示检测到人脸（此时 pitch/yaw 有效）
      face=0 时 pitch/yaw 填 0

注意：
  · display_mode 用 virt，不占 HDMI
  · 每帧都打串口会拖慢帧率，所以文件里记全部、串口只记每 5 帧
"""

import os
import sys
import time
import math
import gc

from media.media import *
import nncase_runtime as nn
import ulab.numpy as np
import image
import aidemo

from libs.PipeLine import PipeLine
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *

from machine import Pin, FPIOA


# ============================================================ 指示灯
class Led:
    """板载 RGB 灯，低电平点亮。"""

    R, G, B = 62, 20, 63

    def __init__(self):
        self.r = Pin(self.R, Pin.OUT, pull=Pin.PULL_NONE, drive=7)
        self.g = Pin(self.G, Pin.OUT, pull=Pin.PULL_NONE, drive=7)
        self.b = Pin(self.B, Pin.OUT, pull=Pin.PULL_NONE, drive=7)
        self.off()

    def _one(self, pin, on):
        pin.value(0 if on else 1)      # 低电平点亮

    def off(self):
        self._one(self.r, False)
        self._one(self.g, False)
        self._one(self.b, False)

    def green(self):
        self._one(self.r, False)
        self._one(self.g, True)
        self._one(self.b, False)

    def blue(self):
        self._one(self.r, False)
        self._one(self.g, False)
        self._one(self.b, True)

    def red(self):
        self._one(self.r, True)
        self._one(self.g, False)
        self._one(self.b, False)


# ============================================================ 人脸检测
class FaceDetApp(AIBase):
    def __init__(self, kmodel_path, model_input_size, anchors,
                 confidence_threshold=0.25, nms_threshold=0.3,
                 rgb888p_size=[800, 480], display_size=[800, 480], debug_mode=0):
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
                 rgb888p_size=[800, 480], display_size=[800, 480], debug_mode=0):
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
                 nms_threshold=0.3, rgb888p_size=[800, 480], debug_mode=0):
        self.face_det = FaceDetApp(face_det_kmodel, det_input_size, anchors,
                                   confidence_threshold, nms_threshold,
                                   rgb888p_size, rgb888p_size, debug_mode)
        self.eye_gaze = EyeGazeApp(eye_gaze_kmodel, eye_gaze_input_size,
                                   rgb888p_size, rgb888p_size, debug_mode)
        self.face_det.config_preprocess()

    def run(self, img):
        dets = self.face_det.run(img)
        # 只取最大的一张脸，多张脸时不判断注视（避免误触发）
        if len(dets) == 0:
            return 0, 0.0, 0.0, 0
        if len(dets) > 1:
            return len(dets), 0.0, 0.0, 0
        self.eye_gaze.config_preprocess(dets[0])
        pitch, yaw = self.eye_gaze.run(img)
        return 1, float(pitch), float(yaw), 1


# ============================================================ 主程序
def main():
    led = Led()
    led.green()                      # 待机：绿灯常亮

    # 用户按键 GPIO53：下拉输入，按下为高电平。每按一次在日志里打一个标记
    btn = Pin(53, Pin.IN, pull=Pin.PULL_DOWN)
    btn_last = 0
    btn_ts = 0
    mark = 0

    face_det_kmodel_path = "/sdcard/examples/kmodel/face_detection_320.kmodel"
    eye_gaze_kmodel_path = "/sdcard/examples/kmodel/eye_gaze.kmodel"
    anchors_path = "/sdcard/examples/utils/prior_data_320.bin"
    log_path = "/sdcard/gaze_log.csv"

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

    print("# 每做一个动作【前】按一下板上的用户按键，日志会打 #MARK")
    print("# 顺序：看镜头 / 看屏幕正中 / 看左 / 看右 / 低头看键盘，每个 5 秒")
    print("# 格式: G,pitch,yaw,face,ts_ms")

    f = open(log_path, "w")
    f.write("pitch,yaw,face,ts_ms\n")

    frame = 0
    buf = []
    t0 = time.ticks_ms()
    fps_t0 = t0
    fps_n = 0

    try:
        while True:
            img = pl.get_frame()
            nface, pitch, yaw, valid = eg.run(img)
            ts = time.ticks_ms() - t0

            # ---- 按键打点（300ms 防抖）----
            v = btn.value()
            if v and not btn_last and (ts - btn_ts) > 300:
                mark += 1
                btn_ts = ts
                f.write("#MARK %d,%d\n" % (mark, ts))
                f.flush()
                print("#MARK %d @%d" % (mark, ts))
            btn_last = v

            line = "G,%.4f,%.4f,%d,%d" % (pitch, yaw, valid, ts)
            if frame % 5 == 0:
                print(line)

            buf.append("%.4f,%.4f,%d,%d\n" % (pitch, yaw, valid, ts))
            if len(buf) >= 25:
                f.write("".join(buf))
                buf = []

            frame += 1
            fps_n += 1
            if fps_n >= 50:
                dt = time.ticks_ms() - fps_t0
                if dt > 0:
                    print("# fps %.1f" % (fps_n * 1000.0 / dt))
                fps_t0 = time.ticks_ms()
                fps_n = 0

            if frame % 25 == 0:
                gc.collect()

    except KeyboardInterrupt:
        print("# 停止")
    finally:
        try:
            if buf:
                f.write("".join(buf))
            f.close()
        except Exception:
            pass
        eg.face_det.deinit()
        eg.eye_gaze.deinit()
        pl.destroy()
        led.off()
        print("# 数据已写入 %s" % log_path)


main()
