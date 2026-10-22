"""多目标跟踪：IoU 匹配 + 匀速预测，解决人脸/物体 ID 跳变。

K230 上人脸检测每帧可能漏检、box 会抖，直接拿检测结果当目标会导致
云台「追着一个一帧就消失的 ID」乱转。这里用最轻量的办法解决：

  - 匀速模型预测下一帧位置（漏检时也能维持）
  - IoU 贪心匹配（不用匈牙利算法，MicroPython 也能跑）
  - 连续命中若干帧才确认（抑制误检）
  - 超过 max_age 帧未更新才删除

纯 Python，兼容 MicroPython。
"""

import vision_math


class Track(object):
    def __init__(self, tid, box, ts, hits=1, min_hits=1):
        self.id = tid
        self.box = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
        self.vx = 0.0
        self.vy = 0.0
        self.hits = hits
        self.min_hits = min_hits
        self.age = 1
        self.time_since_update = 0
        self.last_ts = ts

    @property
    def confirmed(self):
        return self.hits >= self.min_hits

    def center(self):
        return vision_math.bbox_center(self.box)

    def predict(self, dt):
        if dt > 0.0:
            cx, cy = vision_math.bbox_center(self.box)
            cx += self.vx * dt
            cy += self.vy * dt
            w = self.box[2]
            h = self.box[3]
            self.box = (cx - w * 0.5, cy - h * 0.5, w, h)
        self.age += 1
        self.time_since_update += 1

    def update(self, box, ts):
        dt = ts - self.last_ts
        ocx, ocy = vision_math.bbox_center(self.box)
        ncx, ncy = vision_math.bbox_center(box)
        if dt > 1e-6:
            nvx = (ncx - ocx) / dt
            nvy = (ncy - ocy) / dt
            # 一阶平滑，避免单帧抖动把速度带飞
            alpha = 0.5
            self.vx = alpha * nvx + (1.0 - alpha) * self.vx
            self.vy = alpha * nvy + (1.0 - alpha) * self.vy
        self.box = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
        self.last_ts = ts
        self.hits += 1
        self.time_since_update = 0


class IoUTracker(object):
    def __init__(self, iou_threshold=0.3, max_age=15, min_hits=3):
        self.iou_threshold = float(iou_threshold)
        self.max_age = int(max_age)
        self.min_hits = int(min_hits)
        self.tracks = []
        self._next_id = 1
        self._last_ts = None

    def _new_track(self, box, ts):
        t = Track(self._next_id, box, ts, min_hits=self.min_hits)
        self._next_id += 1
        return t

    def update(self, detections, ts):
        """detections: [(x, y, w, h), ...]；ts: 秒。

        返回本帧匹配上的 Track 列表（已按确认状态标注）。
        """
        dt = 0.0
        if self._last_ts is not None:
            dt = ts - self._last_ts
            if dt < 0.0:
                dt = 0.0
        self._last_ts = ts

        for t in self.tracks:
            t.predict(dt)

        # 贪心匹配：所有 (IoU, track_idx, det_idx) 排序后依次认领
        pairs = []
        for ti in range(len(self.tracks)):
            for di in range(len(detections)):
                iou = vision_math.bbox_iou(self.tracks[ti].box, detections[di])
                if iou >= self.iou_threshold:
                    pairs.append((iou, ti, di))
        pairs.sort(reverse=True)

        used_t = set()
        used_d = set()
        matched = []
        for _iou, ti, di in pairs:
            if ti in used_t or di in used_d:
                continue
            used_t.add(ti)
            used_d.add(di)
            self.tracks[ti].update(detections[di], ts)
            matched.append(self.tracks[ti])

        for di in range(len(detections)):
            if di in used_d:
                continue
            self.tracks.append(self._new_track(detections[di], ts))

        # 清理太久没更新的
        alive = []
        for t in self.tracks:
            if t.time_since_update <= self.max_age:
                alive.append(t)
        self.tracks = alive

        return matched

    def confirmed_tracks(self):
        return [t for t in self.tracks if t.hits >= self.min_hits]

    def reset(self):
        self.tracks = []
        self._next_id = 1
        self._last_ts = None
