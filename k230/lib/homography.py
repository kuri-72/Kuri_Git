"""平面单应矩阵（Homography）：像素坐标 <-> 桌面/地面绝对坐标。

纯 Python 实现，兼容 MicroPython。求解用 8x8 正规方程 + 高斯消元，
适合 4~20 组标定点，足够桌面标定使用。

用法
----
# 至少 4 组对应点：像素 (u, v) -> 平面坐标 (X, Z)，单位米
H = homography_from_points(pixels, plane_points)
X, Z = apply_homography(H, u, v)
err = reprojection_error(H, pixels, plane_points)   # 平均像素误差
"""

import math


def _solve_linear(mat, rhs):
    """高斯消元（部分主元）。mat: n x n，rhs: n。返回解向量，奇异时返回 None。"""
    n = len(rhs)
    a = [list(mat[i]) + [rhs[i]] for i in range(n)]
    for col in range(n):
        pivot = col
        best = abs(a[col][col])
        for r in range(col + 1, n):
            v = abs(a[r][col])
            if v > best:
                best = v
                pivot = r
        if best < 1e-12:
            return None
        if pivot != col:
            a[col], a[pivot] = a[pivot], a[col]
        pv = a[col][col]
        for r in range(col + 1, n):
            factor = a[r][col] / pv
            if factor == 0.0:
                continue
            for c in range(col, n + 1):
                a[r][c] -= factor * a[col][c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        s = a[r][n]
        for c in range(r + 1, n):
            s -= a[r][c] * x[c]
        x[r] = s / a[r][r]
    return x


def homography_from_points(src_points, dst_points):
    """由对应点求 3x3 单应矩阵（返回长度 9 的列表，行优先，h8 固定为 1）。

    src_points: [(u, v), ...] 图像坐标
    dst_points: [(X, Z), ...] 平面坐标（米）
    至少 4 组；多于 4 组时用最小二乘。
    """
    n = len(src_points)
    if n < 4 or len(dst_points) != n:
        raise ValueError("need at least 4 corresponding points")

    ata = [[0.0] * 8 for _ in range(8)]
    atb = [0.0] * 8

    for i in range(n):
        u, v = float(src_points[i][0]), float(src_points[i][1])
        x, y = float(dst_points[i][0]), float(dst_points[i][1])

        row1 = [u, v, 1.0, 0.0, 0.0, 0.0, -u * x, -v * x]
        row2 = [0.0, 0.0, 0.0, u, v, 1.0, -u * y, -v * y]

        for a_row, b_val in ((row1, x), (row2, y)):
            for r in range(8):
                if a_row[r] == 0.0:
                    continue
                ar = a_row[r]
                atb[r] += ar * b_val
                row = ata[r]
                for c in range(8):
                    if a_row[c] != 0.0:
                        row[c] += ar * a_row[c]

    h = _solve_linear(ata, atb)
    if h is None:
        raise ValueError("singular system, check point layout")

    return [h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7], 1.0]


def apply_homography(H, u, v):
    """把图像点映射到平面坐标。"""
    w = H[6] * u + H[7] * v + H[8]
    if abs(w) < 1e-12:
        return None
    x = (H[0] * u + H[1] * v + H[2]) / w
    y = (H[3] * u + H[4] * v + H[5]) / w
    return (x, y)


def apply_homography_inv(H, x, y):
    """把平面坐标反映射回图像点。"""
    inv = invert3x3(H)
    if inv is None:
        return None
    return apply_homography(inv, x, y)


def invert3x3(H):
    a, b, c = H[0], H[1], H[2]
    d, e, f = H[3], H[4], H[5]
    g, h, i = H[6], H[7], H[8]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-15:
        return None
    inv_det = 1.0 / det
    return [
        (e * i - f * h) * inv_det, (c * h - b * i) * inv_det, (b * f - c * e) * inv_det,
        (f * g - d * i) * inv_det, (a * i - c * g) * inv_det, (c * d - a * f) * inv_det,
        (d * h - e * g) * inv_det, (b * g - a * h) * inv_det, (a * e - b * d) * inv_det,
    ]


def reprojection_error(H, src_points, dst_points):
    """平均误差（与平面坐标同单位，米）。"""
    total = 0.0
    n = len(src_points)
    for i in range(n):
        p = apply_homography(H, src_points[i][0], src_points[i][1])
        if p is None:
            return None
        dx = p[0] - dst_points[i][0]
        dy = p[1] - dst_points[i][1]
        total += math.sqrt(dx * dx + dy * dy)
    return total / n
