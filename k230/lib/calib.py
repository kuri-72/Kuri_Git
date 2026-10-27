"""标定配置：相机内参与桌面单应的读写、生成、校验。

把「标定」这件事从临时脚本变成可复现的配置文件：
  cam.json      相机内参
  ground_H.json 桌面平面单应

纯 Python，兼容 MicroPython（读写 JSON 用 json / ujson）。
"""

try:
    import json
except ImportError:  # MicroPython
    import ujson as json

import math
import homography
import vision_math


CONFIG_VERSION = 1


# ---------------------------------------------------------------- 内参

def intrinsics_from_focal(width, height, fx, fy=None):
    """已知焦距（像素）时构造内参。"""
    if fy is None:
        fy = fx
    return {
        "version": CONFIG_VERSION,
        "width": int(width),
        "height": int(height),
        "fx": float(fx),
        "fy": float(fy),
        "cx": float(width) / 2.0,
        "cy": float(height) / 2.0,
    }


def intrinsics_from_fov(width, height, hfov_deg):
    """由水平视场角估算内参。

    注意：厂商标的 FOV 常是对角线，这里是水平 FOV，用之前先确认。
    """
    hfov = math.radians(float(hfov_deg))
    fx = (float(width) / 2.0) / math.tan(hfov / 2.0)
    return intrinsics_from_focal(width, height, fx)


def camera_from_config(cfg):
    return vision_math.CameraModel(
        cfg["fx"], cfg["fy"], cfg["cx"], cfg["cy"],
        cfg.get("width"), cfg.get("height"))


def validate_intrinsics(cfg):
    """返回问题列表，空列表表示通过。"""
    problems = []
    for key in ("fx", "fy", "cx", "cy"):
        if key not in cfg:
            problems.append("missing %s" % key)
            continue
        v = cfg[key]
        if not isinstance(v, (int, float)) or v != v:  # NaN 检查
            problems.append("%s is not a number" % key)
        elif v <= 0 and key in ("fx", "fy"):
            problems.append("%s must be positive" % key)
    if "width" in cfg and "cx" in cfg:
        if abs(cfg["cx"] - cfg["width"] / 2.0) > cfg["width"] * 0.2:
            problems.append("cx far from image center")
    if "height" in cfg and "cy" in cfg:
        if abs(cfg["cy"] - cfg["height"] / 2.0) > cfg["height"] * 0.2:
            problems.append("cy far from image center")
    return problems


# ---------------------------------------------------------------- 单应

def calibrate_ground(pixels, plane_points):
    """由对应点求桌面单应，返回 (H, 平均重投影误差)。"""
    H = homography.homography_from_points(pixels, plane_points)
    err = homography.reprojection_error(H, pixels, plane_points)
    return (H, err)


def ground_config(H, error_m=None, height_m=None, pitch_deg=None):
    return {
        "version": CONFIG_VERSION,
        "homography": [float(v) for v in H],
        "reprojection_error_m": None if error_m is None else float(error_m),
        "height_m": None if height_m is None else float(height_m),
        "pitch_deg": None if pitch_deg is None else float(pitch_deg),
    }


def validate_ground(cfg, max_error_m=0.03):
    problems = []
    H = cfg.get("homography")
    if not H or len(H) != 9:
        problems.append("homography must have 9 values")
        return problems
    if homography.invert3x3(H) is None:
        problems.append("homography is singular")
    err = cfg.get("reprojection_error_m")
    if err is not None and err > max_error_m:
        problems.append("reprojection error %.4f m > %.4f m" % (err, max_error_m))
    return problems


# ---------------------------------------------------------------- 点文件

def parse_points_csv(text):
    """解析标定点。

    格式：每行 `u,v,X,Z`，允许 # 注释与空行，第一行可以是表头。
    返回 (pixels, plane_points)。
    """
    pixels = []
    plane = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.replace(";", ",").split(",")]
        if len(parts) != 4:
            raise ValueError("bad line: %r" % raw)
        try:
            u, v, x, z = [float(p) for p in parts]
        except ValueError:
            # 表头行
            continue
        pixels.append((u, v))
        plane.append((x, z))
    return (pixels, plane)


def load_points_csv(path):
    with open(path, "r") as f:
        return parse_points_csv(f.read())


# ---------------------------------------------------------------- 读写

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_json(path):
    with open(path, "r") as f:
        return json.load(f)
