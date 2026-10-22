"""k230/lib 的离线测试。用 CPython 跑，不需要开发板。

运行：
    python k230/tests/test_all.py
"""

import os
import sys
import math
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.abspath(os.path.join(HERE, os.pardir, "lib"))
sys.path.insert(0, LIB)

import vision_math
import homography
import pid
import servo_bus
import gimbal
import tracker
import registry


def approx(a, b, tol=1e-6, msg=""):
    if abs(a - b) > tol:
        raise AssertionError("%s expected %.10f, got %.10f (tol %g)" % (msg, b, a, tol))


def approx_pt(p, q, tol=1e-6, msg=""):
    if p is None:
        raise AssertionError("%s got None" % msg)
    approx(p[0], q[0], tol, msg + "[0]")
    approx(p[1], q[1], tol, msg + "[1]")


# ---------------------------------------------------------------- vision_math

def test_camera_roundtrip():
    cam = vision_math.CameraModel(500.0, 500.0, 320.0, 240.0, 640, 480)
    nx, ny = cam.normalized(400.0, 300.0)
    approx(nx, 0.16, 1e-12, "nx")
    approx(ny, 0.12, 1e-12, "ny")
    approx_pt(cam.project(nx, ny, 1.0), (400.0, 300.0), 1e-9, "project")


def test_ground_plane_level():
    cam = vision_math.CameraModel(500.0, 500.0, 320.0, 240.0)
    plane = vision_math.GroundPlane(cam, height_m=1.0, pitch_deg=0.0)
    X, Z = plane.pixel_to_ground(320.0, 490.0)   # 中心正下方 0.5 归一化
    approx(X, 0.0, 1e-9, "X")
    approx(Z, 2.0, 1e-9, "Z")


def test_ground_plane_pitched():
    cam = vision_math.CameraModel(500.0, 500.0, 320.0, 240.0)
    plane = vision_math.GroundPlane(cam, height_m=1.0, pitch_deg=30.0)
    X, Z = plane.pixel_to_ground(320.0, 240.0)   # 光轴正对处
    approx(X, 0.0, 1e-9, "X")
    approx(Z, 2.0 * math.cos(math.radians(30.0)), 1e-9, "Z")


def test_ground_plane_roundtrip():
    cam = vision_math.CameraModel(500.0, 500.0, 320.0, 240.0)
    plane = vision_math.GroundPlane(cam, height_m=1.2, pitch_deg=20.0)
    for uv in [(200.0, 300.0), (400.0, 300.0), (320.0, 400.0), (500.0, 350.0)]:
        g = plane.pixel_to_ground(uv[0], uv[1])
        if g is None:
            raise AssertionError("point should project to ground: %r" % (uv,))
        back = plane.ground_to_pixel(g[0], g[1])
        approx_pt(back, uv, 1e-6, "roundtrip %r" % (uv,))


def test_ground_plane_horizon():
    cam = vision_math.CameraModel(500.0, 500.0, 320.0, 240.0)
    plane = vision_math.GroundPlane(cam, height_m=1.0, pitch_deg=0.0)
    if plane.pixel_to_ground(320.0, 240.0) is not None:
        raise AssertionError("horizon pixel must return None")
    if plane.pixel_to_ground(320.0, 100.0) is not None:
        raise AssertionError("above horizon must return None")


def test_yaw_pitch_error():
    cam = vision_math.CameraModel(500.0, 500.0, 320.0, 240.0)
    yaw, pitch = cam.yaw_pitch_error(420.0, 340.0)
    approx(yaw, math.atan(0.2), 1e-9, "yaw")
    approx(pitch, math.atan(0.2), 1e-9, "pitch")


def test_bbox_helpers():
    a = (100.0, 100.0, 50.0, 50.0)
    b = (100.0, 100.0, 50.0, 50.0)
    approx(vision_math.bbox_iou(a, b), 1.0, 1e-12, "iou same")
    c = (200.0, 200.0, 50.0, 50.0)
    approx(vision_math.bbox_iou(a, c), 0.0, 1e-12, "iou disjoint")
    approx_pt(vision_math.bbox_center(a), (125.0, 125.0), 1e-12, "center")


def test_distance_from_width():
    d = vision_math.distance_from_width(pixel_width=150.0, real_width_m=0.15, fx=500.0)
    approx(d, 0.5, 1e-9, "distance")
    if vision_math.distance_from_width(0, 0.15, 500.0) is not None:
        raise AssertionError("zero pixel width must return None")


# ---------------------------------------------------------------- homography

def test_homography_recovers_affine():
    H_true = [0.01, 0.0, -3.2, 0.0, 0.01, -2.4, 0.0, 0.0, 1.0]
    src = [(0.0, 0.0), (640.0, 0.0), (0.0, 480.0), (640.0, 480.0)]
    dst = [homography.apply_homography(H_true, u, v) for u, v in src]
    H = homography.homography_from_points(src, dst)
    for i in range(9):
        approx(H[i], H_true[i], 1e-8, "H[%d]" % i)


def test_homography_recovers_projective():
    H_true = [0.01, 0.0002, -3.2, 0.0001, 0.01, -2.4, 1e-5, 2e-5, 1.0]
    src = [(100.0, 80.0), (540.0, 90.0), (120.0, 420.0), (560.0, 400.0),
           (320.0, 240.0), (200.0, 300.0), (450.0, 200.0), (300.0, 380.0)]
    dst = [homography.apply_homography(H_true, u, v) for u, v in src]
    H = homography.homography_from_points(src, dst)
    err = homography.reprojection_error(H, src, dst)
    if err is None or err > 1e-8:
        raise AssertionError("reprojection error too large: %r" % (err,))


def test_homography_inverse():
    H = [0.01, 0.0, -3.2, 0.0, 0.01, -2.4, 0.0, 0.0, 1.0]
    p = (320.0, 240.0)
    g = homography.apply_homography(H, p[0], p[1])
    approx_pt(g, (0.0, 0.0), 1e-9, "forward")
    approx_pt(homography.apply_homography_inv(H, g[0], g[1]), p, 1e-6, "inverse")


def test_homography_needs_four_points():
    try:
        homography.homography_from_points([(0, 0), (1, 0), (0, 1)], [(0, 0), (1, 0), (0, 1)])
    except ValueError:
        return
    raise AssertionError("expected ValueError for < 4 points")


# ---------------------------------------------------------------------- pid

def test_pid_proportional():
    p = pid.PID(kp=1.0, out_min=-10.0, out_max=10.0)
    approx(p.update(0.5, 0.1), 0.5, 1e-9, "P output")


def test_pid_output_clamp():
    p = pid.PID(kp=10.0, out_min=-1.0, out_max=1.0)
    approx(p.update(1.0, 0.1), 1.0, 1e-9, "clamped high")
    p2 = pid.PID(kp=10.0, out_min=-1.0, out_max=1.0)
    approx(p2.update(-1.0, 0.1), -1.0, 1e-9, "clamped low")


def test_pid_deadband():
    p = pid.PID(kp=1.0, deadband=0.1)
    approx(p.update(0.05, 0.1), 0.0, 1e-12, "inside deadband")
    approx(p.update(0.2, 0.1), 0.2, 1e-9, "outside deadband")


def test_pid_integral_limit():
    p = pid.PID(kp=0.0, ki=1.0, i_max=0.2, out_min=-10.0, out_max=10.0)
    for _ in range(20):
        out = p.update(1.0, 0.1)
    if out > 0.2 + 1e-9:
        raise AssertionError("integral windup: %r" % (out,))


def test_pid_slew_rate():
    p = pid.PID(kp=100.0, out_min=-10.0, out_max=10.0, max_rate=1.0)
    out = p.update(1.0, 0.1)          # 原始输出 10，斜率限制 1.0/s * 0.1s = 0.1
    approx(out, 0.1, 1e-9, "slew limited")
    out2 = p.update(1.0, 0.1)
    approx(out2, 0.2, 1e-9, "slew ramp")


def test_pid_invalid_dt():
    p = pid.PID(kp=1.0)
    p.update(1.0, 0.1)
    last = p.update(1.0, 0.1)
    if p.update(1.0, 0.0) != last:
        raise AssertionError("dt<=0 should return last output")


# --------------------------------------------------------------- servo_bus

def test_packet_structure():
    pkt = servo_bus.build_packet(1, servo_bus.INST_WRITE, [0x2A, 0x00, 0x08])
    if len(pkt) != 9:
        raise AssertionError("packet length %d" % len(pkt))
    if pkt[0] != 0xFF or pkt[1] != 0xFF:
        raise AssertionError("bad header")
    if pkt[2] != 1 or pkt[3] != 5 or pkt[4] != servo_bus.INST_WRITE:
        raise AssertionError("bad header fields")
    body = [pkt[2], pkt[3], pkt[4], pkt[5], pkt[6], pkt[7]]
    if servo_bus.checksum(body) != pkt[8]:
        raise AssertionError("checksum mismatch")


def test_parse_roundtrip():
    pkt = servo_bus.build_packet(7, servo_bus.INST_WRITE, [0x2A, 0x10, 0x27])
    got = servo_bus.parse_packet(pkt)
    if got is None:
        raise AssertionError("parse returned None")
    sid, inst, params, nxt = got
    if sid != 7 or inst != servo_bus.INST_WRITE or params != [0x2A, 0x10, 0x27] or nxt != len(pkt):
        raise AssertionError("parsed wrong: %r" % (got,))


def test_parse_rejects_bad_checksum():
    pkt = bytearray(servo_bus.build_packet(7, servo_bus.INST_WRITE, [0x2A, 0x10]))
    pkt[-1] = (pkt[-1] ^ 0xFF) & 0xFF
    if servo_bus.parse_packet(bytes(pkt)) is not None:
        raise AssertionError("corrupted packet must be rejected")


def test_sync_write():
    entries = [(1, [0x00, 0x08]), (2, [0xFF, 0x0F])]
    pkt = servo_bus.build_sync_write(entries, servo_bus.ADDR_GOAL_POSITION)
    got = servo_bus.parse_packet(pkt)
    if got is None:
        raise AssertionError("sync packet unparsable")
    sid, inst, params, _ = got
    if inst != servo_bus.INST_SYNC_WRITE:
        raise AssertionError("wrong instruction")
    if params != [servo_bus.ADDR_GOAL_POSITION, 2, 1, 0x00, 0x08, 2, 0xFF, 0x0F]:
        raise AssertionError("wrong params: %r" % (params,))


def test_feetech_bus_clamps():
    sent = []
    bus = servo_bus.FeetechBus(lambda data: sent.append(data))
    bus.set_position(1, 9999)
    got = servo_bus.parse_packet(sent[-1])
    pos = got[2][1] | (got[2][2] << 8)
    if pos != 4095:
        raise AssertionError("position not clamped: %d" % pos)


# -------------------------------------------------------------------- gimbal

def test_gimbal_moves_toward_target():
    pan_axis = pid.PID(kp=1.0, out_min=-1.0, out_max=1.0)
    tilt_axis = pid.PID(kp=1.0, out_min=-1.0, out_max=1.0)
    ctrl = gimbal.PanTiltController(pan_axis, tilt_axis,
                                    pan_center=2048, tilt_center=2048,
                                    max_rate_ticks_per_s=1000.0)
    pan, tilt = ctrl.update(0.5, 0.0, 0.1)
    if pan != 2098:
        raise AssertionError("pan moved to %d, expected 2098" % pan)
    if tilt != 2048:
        raise AssertionError("tilt should stay, got %d" % tilt)


def test_gimbal_clamps_at_limit():
    pan_axis = pid.PID(kp=1.0, out_min=-1.0, out_max=1.0)
    tilt_axis = pid.PID(kp=1.0, out_min=-1.0, out_max=1.0)
    ctrl = gimbal.PanTiltController(pan_axis, tilt_axis,
                                    pan_center=2048, tilt_center=2048,
                                    pan_range=(2040, 2060),
                                    max_rate_ticks_per_s=1000.0)
    for _ in range(10):
        pan, _tilt = ctrl.update(1.0, 0.0, 0.1)
    if pan != 2060:
        raise AssertionError("pan should clamp at 2060, got %d" % pan)
    if not ctrl.at_limit()["pan"]:
        raise AssertionError("at_limit must report pan limit")


def test_gimbal_reset():
    pan_axis = pid.PID(kp=1.0, out_min=-1.0, out_max=1.0)
    tilt_axis = pid.PID(kp=1.0, out_min=-1.0, out_max=1.0)
    ctrl = gimbal.PanTiltController(pan_axis, tilt_axis, pan_center=2048, tilt_center=2048)
    ctrl.update(1.0, 1.0, 0.1)
    pan, tilt = ctrl.reset()
    if pan != 2048 or tilt != 2048:
        raise AssertionError("reset should return center")


# ------------------------------------------------------------------- tracker

def test_tracker_keeps_id():
    tr = tracker.IoUTracker(iou_threshold=0.3, max_age=10, min_hits=1)
    tr.update([(100.0, 100.0, 60.0, 60.0)], 0.0)
    ids = set()
    for i in range(1, 6):
        b = (100.0 + i * 2.0, 100.0, 60.0, 60.0)
        matched = tr.update([b], i * 0.033)
        for t in matched:
            ids.add(t.id)
    if len(ids) != 1:
        raise AssertionError("id should stay stable, got %r" % (ids,))


def test_tracker_survives_occlusion():
    tr = tracker.IoUTracker(max_age=10, min_hits=2)
    box = (100.0, 100.0, 60.0, 60.0)
    tr.update([box], 0.0)
    tr.update([box], 0.033)
    tid = tr.tracks[0].id

    for i in range(3):
        tr.update([], 0.033 * (i + 2))

    if len(tr.tracks) != 1:
        raise AssertionError("track dropped too early: %d alive" % len(tr.tracks))

    back = tr.update([box], 0.033 * 5)
    if not back or back[0].id != tid:
        raise AssertionError("should re-acquire same id after occlusion")


def test_tracker_expires():
    tr = tracker.IoUTracker(max_age=2, min_hits=1)
    tr.update([(10.0, 10.0, 20.0, 20.0)], 0.0)
    for i in range(5):
        tr.update([], 0.033 * (i + 1))
    if tr.tracks:
        raise AssertionError("track should expire, %d left" % len(tr.tracks))


def test_tracker_confirmation():
    tr = tracker.IoUTracker(min_hits=3)
    box = (50.0, 50.0, 40.0, 40.0)
    tr.update([box], 0.0)
    if tr.confirmed_tracks():
        raise AssertionError("new track must not be confirmed")
    tr.update([box], 0.033)
    if tr.confirmed_tracks():
        raise AssertionError("2 hits must not be confirmed")
    tr.update([box], 0.066)
    if len(tr.confirmed_tracks()) != 1:
        raise AssertionError("3 hits should confirm")


def test_tracker_two_objects():
    tr = tracker.IoUTracker(min_hits=1)
    a = (10.0, 10.0, 40.0, 40.0)
    b = (300.0, 10.0, 40.0, 40.0)
    tr.update([a, b], 0.0)
    matched = tr.update([a, b], 0.033)
    ids = sorted(t.id for t in matched)
    if len(ids) != 2 or ids[0] == ids[1]:
        raise AssertionError("two objects need two ids, got %r" % (ids,))


# ------------------------------------------------------------------ registry

def test_registry_merges_same_object():
    reg = registry.ObjectRegistry(merge_distance_m=0.2)
    a = reg.observe("cup", 1.0, 2.0, ts=0.0)
    b = reg.observe("cup", 1.05, 2.02, ts=1.0)
    if a["id"] != b["id"]:
        raise AssertionError("should merge into one item")
    if b["hits"] != 2:
        raise AssertionError("hits should be 2, got %d" % b["hits"])
    if len(reg) != 1:
        raise AssertionError("registry should hold 1 item")
    approx(b["x"], 1.025, 1e-9, "averaged x")


def test_registry_separates_far():
    reg = registry.ObjectRegistry(merge_distance_m=0.2)
    a = reg.observe("cup", 1.0, 2.0)
    b = reg.observe("cup", 1.5, 2.0)
    if a["id"] == b["id"]:
        raise AssertionError("far objects must not merge")
    if len(reg) != 2:
        raise AssertionError("registry should hold 2 items")


def test_registry_kind_isolation():
    reg = registry.ObjectRegistry(merge_distance_m=1.0)
    a = reg.observe("cup", 0.0, 0.0)
    b = reg.observe("bottle", 0.0, 0.0)
    if a["id"] == b["id"]:
        raise AssertionError("different kinds must stay separate")


def test_registry_nearest():
    reg = registry.ObjectRegistry(merge_distance_m=0.05)
    reg.observe("cup", 0.0, 0.0)
    reg.observe("cup", 2.0, 0.0)
    it = reg.nearest(1.9, 0.0, kind="cup")
    if it is None or abs(it["x"] - 2.0) > 1e-9:
        raise AssertionError("nearest returned %r" % (it,))


def test_registry_save_load():
    import tempfile
    reg = registry.ObjectRegistry()
    reg.observe("cup", 0.1, 0.2, ts=1.0)
    reg.observe("bottle", 0.5, 0.6, ts=2.0)

    path = os.path.join(tempfile.gettempdir(), "kuri_registry_test.json")
    reg.save(path)
    reg2 = registry.ObjectRegistry.load(path)
    try:
        os.remove(path)
    except OSError:
        pass

    if len(reg2) != 2:
        raise AssertionError("loaded %d items" % len(reg2))
    if reg2.items[0]["kind"] != "cup":
        raise AssertionError("kind lost on load")


def test_registry_max_items():
    reg = registry.ObjectRegistry(merge_distance_m=0.01, max_items=3)
    for i in range(5):
        reg.observe("cup", float(i), 0.0, ts=float(i))
    if len(reg) != 3:
        raise AssertionError("max_items not enforced: %d" % len(reg))
    xs = sorted(it["x"] for it in reg.items)
    if xs[0] < 1.9:
        raise AssertionError("oldest should be evicted, got %r" % (xs,))


# --------------------------------------------------------------- 闭环仿真

def test_closed_loop_tracking_converges():
    """无硬件的端到端验证：像素 -> 角误差 -> PID -> 舵机 -> 目标回中。"""
    cam = vision_math.CameraModel(500.0, 500.0, 320.0, 240.0)
    pan_axis = pid.PID(kp=1.5, out_min=-1.0, out_max=1.0)
    tilt_axis = pid.PID(kp=1.5, out_min=-1.0, out_max=1.0)
    ctrl = gimbal.PanTiltController(pan_axis, tilt_axis,
                                    pan_center=2048, tilt_center=2048,
                                    max_rate_ticks_per_s=1500.0)

    target_bearing = 0.20      # 目标在世界中的方位角（弧度）
    ticks_per_rad = 1000.0
    dt = 0.033

    for _ in range(80):
        cam_bearing = (ctrl.pan - 2048) / ticks_per_rad
        err = target_bearing - cam_bearing
        u = 320.0 + cam.fx * math.tan(err)
        yaw_err, pitch_err = cam.yaw_pitch_error(u, 240.0)
        ctrl.update(yaw_err, pitch_err, dt)

    final_err = abs((ctrl.pan - 2048) / ticks_per_rad - target_bearing)
    if final_err > 0.01:
        raise AssertionError("did not converge: %.4f rad" % final_err)

    # 收敛后目标应接近画面中心
    cam_bearing = (ctrl.pan - 2048) / ticks_per_rad
    px = 320.0 + cam.fx * math.tan(target_bearing - cam_bearing)
    if abs(px - 320.0) > 5.0:
        raise AssertionError("target not centered: u=%.1f" % px)


# ---------------------------------------------------------------------- main

def main():
    tests = []
    for name in sorted(globals()):
        if name.startswith("test_") and callable(globals()[name]):
            tests.append((name, globals()[name]))

    failed = []
    for name, fn in tests:
        try:
            fn()
            print("PASS  %s" % name)
        except Exception:
            failed.append(name)
            print("FAIL  %s" % name)
            traceback.print_exc()

    print("")
    print("%d passed, %d failed, %d total" % (len(tests) - len(failed), len(failed), len(tests)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
