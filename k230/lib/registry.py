"""物品登记表：把检测结果和绝对坐标存下来，支持按距离合并与查询。

对应目标里的「感知多种物品并登记绝对坐标位置」。
坐标来自 vision_math.GroundPlane / homography，单位米。

设计要点
--------
- 同一个物品在连续帧被检测到，不该产生一堆重复条目：
  同类别、距离小于 merge_distance 就合并，位置做加权平均。
- 每条记录带 hits（被看到几次）与 last_seen，可用于淘汰过期物品。
- 可存成 JSON，掉电重启后恢复。

纯 Python，兼容 MicroPython（json / ujson 都行）。
"""

try:
    import json
except ImportError:  # MicroPython
    import ujson as json


class ObjectRegistry(object):
    def __init__(self, merge_distance_m=0.12, max_items=64):
        self.merge_distance = float(merge_distance_m)
        self.max_items = int(max_items)
        self.items = []
        self._next_id = 1

    # ---------------------------------------------------------------- 写入

    def observe(self, kind, x, z, confidence=1.0, ts=None, label=None):
        """登记一次观测，返回合并后（或新建）的条目。"""
        x = float(x)
        z = float(z)
        conf = float(confidence)

        best = None
        best_d = None
        for item in self.items:
            if item["kind"] != kind:
                continue
            dx = item["x"] - x
            dz = item["z"] - z
            d = (dx * dx + dz * dz) ** 0.5
            if d <= self.merge_distance and (best_d is None or d < best_d):
                best = item
                best_d = d

        if best is None:
            best = {
                "id": self._next_id,
                "kind": kind,
                "label": label if label is not None else kind,
                "x": x,
                "z": z,
                "confidence": conf,
                "hits": 1,
                "first_seen": ts,
                "last_seen": ts,
            }
            self._next_id += 1
            self.items.append(best)
            self._enforce_limit()
            return best

        # 加权平均，越新的观测权重越高一点
        n = best["hits"] + 1
        best["x"] = best["x"] * (n - 1) / n + x / n
        best["z"] = best["z"] * (n - 1) / n + z / n
        best["confidence"] = max(best["confidence"], conf)
        best["hits"] = n
        best["last_seen"] = ts
        if label is not None:
            best["label"] = label
        return best

    def _enforce_limit(self):
        while len(self.items) > self.max_items:
            # 淘汰最久没被看到的
            oldest = 0
            for i in range(1, len(self.items)):
                a = self.items[i].get("last_seen")
                b = self.items[oldest].get("last_seen")
                if a is not None and (b is None or a < b):
                    oldest = i
            self.items.pop(oldest)

    # ---------------------------------------------------------------- 查询

    def find(self, kind=None):
        if kind is None:
            return list(self.items)
        return [it for it in self.items if it["kind"] == kind]

    def nearest(self, x, z, kind=None, max_distance=None):
        best = None
        best_d = None
        for item in self.find(kind):
            dx = item["x"] - x
            dz = item["z"] - z
            d = (dx * dx + dz * dz) ** 0.5
            if max_distance is not None and d > max_distance:
                continue
            if best_d is None or d < best_d:
                best = item
                best_d = d
        return best

    def remove(self, item_id):
        before = len(self.items)
        self.items = [it for it in self.items if it["id"] != item_id]
        return len(self.items) != before

    def clear(self):
        self.items = []
        self._next_id = 1

    def __len__(self):
        return len(self.items)

    # ------------------------------------------------------------ 持久化

    def to_dict(self):
        return {"version": 1, "next_id": self._next_id, "items": self.items}

    def load_dict(self, data):
        self.items = list(data.get("items", []))
        self._next_id = int(data.get("next_id", 1))
        return self

    def save(self, path):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f)

    @classmethod
    def load(cls, path, merge_distance_m=0.12, max_items=64):
        reg = cls(merge_distance_m=merge_distance_m, max_items=max_items)
        with open(path, "r") as f:
            reg.load_dict(json.load(f))
        return reg
