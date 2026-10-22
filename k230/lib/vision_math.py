"""相机几何与坐标变换（纯 Python，兼容 MicroPython，无第三方依赖）。

坐标系约定
----------
图像坐标 (u, v)：u 向右，v 向下，原点在左上角。
相机坐标 (x, y, z)：x 向右，y 向下，z 向前（光轴方向）。
世界坐标 (X, Y, Z)：X 向右，Y 向上，Z 水平向前。
相机安装在世界坐标 (0, h, 0)，光轴水平下俯 pitch 角度。

单位：外部长度统一用米（m），角度用度（deg）。

典型用法
--------
cam = CameraModel(fx=500.0, fy=500.0, cx=320.0, cy=240.0)
plane = GroundPlane(cam, height_m=1.0, pitch_deg=20.0)
X, Z = plane.pixel_to_ground(400, 300)      # 绝对坐标（米）
yaw, pitch = cam.yaw_pitch_error(400, 300)  # 相对坐标（弧度，供云台 PID）
"""

import math


class CameraModel(object):
    """针孔相机模型。"""

    def __init__(self, fx, fy, cx, cy, width=None, height=None):
        self.fx = float(fx)
        self.fy = float(fy)
        self.cx = float(cx)
        self.cy = float(cy)
        self.width = width
        self.height = height

    def normalized(self, u, v):
        """像素坐标 -> 归一化相机坐标 (x/z, y/z)。"""
        return ((u - self.cx) / self.fx, (v - self.cy) / self.fy)

    def project(self, x, y, z):
        """相机坐标 -> 像素坐标。"""
        if z <= 0:
            return None
        return (self.fx * x / z + self.cx, self.fy * y / z + self.cy)

    def yaw_pitch_error(self, u, v):
        """像素相对光心的偏角（弧度），直接喂给云台 PID。

        返回 (yaw, pitch)：yaw 向右为正，pitch 向下为正。
        """
        nx, ny = self.normalized(u, v)
        return (math.atan(nx), math.atan(ny))

    def fov_deg(self):
        """水平 / 垂直视场角（需要提供 width / height）。"""
        if not self.width or not self.height:
            return None
        return (
            2.0 * math.degrees(math.atan(self.width / (2.0 * self.fx))),
            2.0 * math.degrees(math.atan(self.height / (2.0 * self.fy))),
        )

    def __repr__(self):
        return "CameraModel(fx=%.2f, fy=%.2f, cx=%.2f, cy=%.2f)" % (
            self.fx, self.fy, self.cx, self.cy)


class GroundPlane(object):
    """地面/桌面平面投影：像素 -> 平面绝对坐标（单目，假设目标落在平面上）。"""

    def __init__(self, camera, height_m, pitch_deg=0.0):
        self.camera = camera
        self.height = float(height_m)
        self.pitch = math.radians(float(pitch_deg))

    def pixel_to_ground(self, u, v):
        nx, ny = self.camera.normalized(u, v)
        return self.normalized_to_ground(nx, ny)

    def normalized_to_ground(self, nx, ny):
        """归一化坐标 -> (X, Z)，单位米；指向地平线及以上时返回 None。"""
        cp = math.cos(self.pitch)
        sp = math.sin(self.pitch)
        denom = ny * cp + sp
        if denom <= 1e-9:
            return None
        t = self.height / denom
        return (t * nx, t * (cp - ny * sp))

    def ground_to_pixel(self, X, Z):
        """平面绝对坐标 -> 像素，用于校验与画框。"""
        cp = math.cos(self.pitch)
        sp = math.sin(self.pitch)
        y_c = self.height * cp - sp * Z
        z_c = self.height * sp + cp * Z
        if z_c <= 1e-9:
            return None
        return self.camera.project(X, y_c, z_c)

    def __repr__(self):
        return "GroundPlane(h=%.3f m, pitch=%.2f deg)" % (
            self.height, math.degrees(self.pitch))


def bbox_center(box):
    """box = (x, y, w, h) -> 中心点 (u, v)。"""
    return (box[0] + box[2] * 0.5, box[1] + box[3] * 0.5)


def bbox_area(box):
    return float(box[2]) * float(box[3])


def bbox_iou(a, b):
    """两个 (x, y, w, h) 框的交并比。"""
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = ix2 - ix1
    ih = iy2 - iy1
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = float(iw) * float(ih)
    union = bbox_area(a) + bbox_area(b) - inter
    if union <= 0:
        return 0.0
    return inter / union


def distance_from_width(pixel_width, real_width_m, fx):
    """已知物体真实宽度估距（米）。像素宽度越小 -> 越远。"""
    if pixel_width <= 0:
        return None
    return fx * float(real_width_m) / float(pixel_width)


def distance_from_face(box, fx, real_face_width_m=0.15):
    """按人脸宽度（默认 15 cm）估距，仅作粗测。"""
    return distance_from_width(box[2], real_face_width_m, fx)
