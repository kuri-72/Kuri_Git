# K230 项目代码

> 阶段：P1 的**硬件无关部分**。所有代码都是纯 Python，可在 PC 上跑测试，不需要开发板。
>
> 可行性评估与总计划见 [`../docs/k230/00-feasibility-and-plan.md`](../docs/k230/00-feasibility-and-plan.md)。

## 目录

```text
k230/
├── lib/
│   ├── vision_math.py   相机内参、像素↔归一化、地面投影（相对/绝对坐标）、bbox 工具
│   ├── homography.py    平面单应：像素 ↔ 桌面绝对坐标，含最小二乘求解与误差评估
│   ├── tracker.py       多目标跟踪：IoU 匹配 + 匀速预测，稳定 ID、抗漏检
│   ├── registry.py      物品登记表：绝对坐标去重合并、查询、JSON 持久化
│   ├── pid.py           PID（死区、积分限幅、输出限幅、斜率限制）
│   ├── servo_bus.py     飞特 SCS/STS 兼容串口帧：组包、解析、同步写
│   └── gimbal.py        云台控制器：角误差 → 舵机位置（增量式）
└── tests/
    └── test_all.py      38 项离线测试（含无硬件闭环仿真）
```

## 跑测试

不需要开发板，用任意 Python 3：

```bash
python k230/tests/test_all.py
```

期望输出：

```text
38 passed, 0 failed, 38 total
```

## 各模块能解决什么问题

### `vision_math.py`

| 函数 / 类 | 用途 |
| --- | --- |
| `CameraModel.normalized(u, v)` | 像素 → 归一化坐标 |
| `CameraModel.yaw_pitch_error(u, v)` | 像素 → 云台需要的偏角（弧度），这是**相对坐标** |
| `GroundPlane.pixel_to_ground(u, v)` | 像素 → 地面/桌面平面坐标（米），这是**绝对坐标** |
| `GroundPlane.ground_to_pixel(X, Z)` | 反向映射，用于画框校验 |
| `bbox_iou` / `bbox_center` | 跟踪与去重用 |
| `distance_from_width` | 已知物体尺寸的单目粗测距 |

### `homography.py`

标定用：给定 ≥4 组「像素 ↔ 桌面坐标」，求单应矩阵。

```python
H = homography_from_points(pixels, plane_points)
X, Z = apply_homography(H, u, v)
err = reprojection_error(H, pixels, plane_points)   # 米，越小越好
```

### `pid.py` / `gimbal.py`

```python
pan_axis = PID(kp=0.8, ki=0.05, kd=0.02, out_min=-1, out_max=1,
               deadband=math.radians(1.0), max_rate=3.0)
tilt_axis = PID(...)
ctrl = PanTiltController(pan_axis, tilt_axis,
                         pan_center=2048, tilt_center=2048,
                         max_rate_ticks_per_s=1500)

yaw_err, pitch_err = cam.yaw_pitch_error(u, v)
pan, tilt = ctrl.update(yaw_err, pitch_err, dt)
bus.set_positions({1: pan, 2: tilt})
```

### `servo_bus.py`

飞特（Feetech）SCS/STS 帧格式。如果你的舵机是别的协议，只需要替换 `build_packet` 与寄存器地址，上层 `PanTiltController` 不用改。

### 一条完整的感知链路

```python
from tracker import IoUTracker
from registry import ObjectRegistry

tracker = IoUTracker(min_hits=3, max_age=15)
reg = ObjectRegistry(merge_distance_m=0.12)

# 每一帧：
dets = [...]                        # [(x, y, w, h), ...]，来自 YOLO / 人脸检测
tracks = tracker.update(dets, t)    # 返回本帧匹配上的轨迹，ID 稳定

for tr in tracks:
    u, v = tr.center()
    g = plane.pixel_to_ground(u, v)  # 绝对坐标（米）
    if g is not None:
        reg.observe(kind="cup", x=g[0], z=g[1], ts=t)
```

`tracker` 负责「同一个东西不要换 ID」，`registry` 负责「同一个东西不要记成两条」。

## 在 K230 上使用

1. 把 `lib/` 整个复制到开发板 `/sdcard/lib/`
2. 脚本里加：

```python
import sys
sys.path.append("/sdcard/lib")
import vision_math, homography, pid, servo_bus, gimbal
```

## 兼容性约定

- 只用标准库 `math`，不依赖 numpy / 第三方包
- 不用 f-string、不用 `dataclasses`、不用类型注解（兼容老版本 MicroPython）
- 浮点与整数分开使用，避免在 KPU 之外做重计算

## 待硬件确认后补充

- [ ] 相机内参标定结果（`cam.json`）
- [ ] 桌面平面单应（`ground_H.json`）
- [ ] 云台舵机 ID、限位、方向系数
- [ ] 串口波特率与协议实测
