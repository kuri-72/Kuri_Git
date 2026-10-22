"""串口舵机总线协议（飞特 Feetech SCS/STS 兼容帧格式）。

为什么选这个格式：国内云台/机械臂大量使用飞特 STS3215、SCS 系列，
帧结构简单（0xFF 0xFF ID LEN INST PARAMS CHECKSUM），易在 MicroPython 里拼包。
如果你的硬件是别的协议，只需要替换本文件的 build_packet / 寄存器地址。

帧格式
------
0xFF 0xFF ID LENGTH INSTRUCTION PARAMS... CHECKSUM
LENGTH  = len(PARAMS) + 2
CHECKSUM = (~(ID + LENGTH + INSTRUCTION + sum(PARAMS))) & 0xFF

纯 Python，兼容 MicroPython。
"""

INST_PING = 0x01
INST_READ = 0x02
INST_WRITE = 0x03
INST_REG_WRITE = 0x04
INST_ACTION = 0x05
INST_RESET = 0x06
INST_SYNC_WRITE = 0x83

# STS3215 / SCS 系列常用寄存器地址
ADDR_TORQUE_ENABLE = 0x28
ADDR_GOAL_POSITION = 0x2A   # 2 字节，0~4095
ADDR_GOAL_SPEED = 0x2E      # 2 字节
ADDR_PRESENT_POSITION = 0x38
ADDR_PRESENT_SPEED = 0x3A


def checksum(body):
    """body = [ID, LENGTH, INSTRUCTION, *PARAMS]。"""
    s = 0
    for b in body:
        s += b
    return (~s) & 0xFF


def build_packet(servo_id, instruction, params=()):
    """组一帧。返回 bytes。"""
    params = list(params)
    length = len(params) + 2
    body = [servo_id & 0xFF, length & 0xFF, instruction & 0xFF] + [
        int(p) & 0xFF for p in params]
    return bytes([0xFF, 0xFF] + body + [checksum(body)])


def build_write(servo_id, address, data):
    """写寄存器：params = [ADDR, data...]。"""
    payload = [address] + list(data)
    return build_packet(servo_id, INST_WRITE, payload)


def build_write_u16(servo_id, address, value):
    value = int(value)
    return build_write(servo_id, address, [value & 0xFF, (value >> 8) & 0xFF])


def build_sync_write(entries, address):
    """同步写多个舵机。

    entries: [(servo_id, [byte, ...]), ...]，每个舵机的数据长度必须一致。
    params = [ADDR, DATA_LEN, ID1, data1..., ID2, data2...]
    """
    if not entries:
        return bytes([0xFF, 0xFF])
    data_len = len(entries[0][1])
    params = [address, data_len]
    for servo_id, data in entries:
        if len(data) != data_len:
            raise ValueError("sync write data length mismatch")
        params.append(servo_id & 0xFF)
        for b in data:
            params.append(int(b) & 0xFF)
    # SYNC_WRITE 的 LENGTH 不需要额外 +2 以外的特殊处理，直接走通用组帧
    return build_packet(0xFE, INST_SYNC_WRITE, params)


def parse_packet(data, offset=0):
    """从 data[offset:] 解析一帧。

    返回 (servo_id, instruction, params, next_offset)，数据不足或校验失败返回 None。
    """
    n = len(data)
    i = offset
    while i + 1 < n:
        if data[i] == 0xFF and data[i + 1] == 0xFF:
            break
        i += 1
    start = i
    if start + 4 > n:
        return None

    length = data[start + 3]
    total = length + 4
    if start + total > n:
        return None

    # body = [ID, LENGTH, INSTRUCTION, *PARAMS]
    body = list(data[start + 2:start + 3 + length])
    if len(body) != length + 1:
        return None

    chk = data[start + total - 1]
    if checksum(body) != chk:
        return None

    return (body[0], body[2], body[3:], start + total)


class FeetechBus(object):
    """把拼好的帧通过一个 write(bytes) 回调发出去。

    write_fn: 形如 lambda data: uart.write(data)
    """

    def __init__(self, write_fn, position_min=0, position_max=4095):
        self._write = write_fn
        self.position_min = position_min
        self.position_max = position_max

    def _clamp_pos(self, position):
        p = int(position)
        if p < self.position_min:
            return self.position_min
        if p > self.position_max:
            return self.position_max
        return p

    def set_position(self, servo_id, position, speed=None):
        """写目标位置（0~4095）。speed 为 None 时不动 GOAL_SPEED。"""
        pos = self._clamp_pos(position)
        if speed is None:
            self._write(build_write_u16(servo_id, ADDR_GOAL_POSITION, pos))
            return
        spd = int(speed) & 0xFFFF
        payload = [pos & 0xFF, (pos >> 8) & 0xFF, spd & 0xFF, (spd >> 8) & 0xFF]
        self._write(build_write(servo_id, ADDR_GOAL_POSITION, payload))

    def set_positions(self, mapping, speed=None):
        """同步写多路位置。mapping: {servo_id: position}。"""
        entries = []
        for servo_id in mapping:
            pos = self._clamp_pos(mapping[servo_id])
            if speed is None:
                entries.append((servo_id, [pos & 0xFF, (pos >> 8) & 0xFF]))
            else:
                spd = int(speed) & 0xFFFF
                entries.append((servo_id, [
                    pos & 0xFF, (pos >> 8) & 0xFF,
                    spd & 0xFF, (spd >> 8) & 0xFF]))
        if not entries:
            return
        self._write(build_sync_write(entries, ADDR_GOAL_POSITION))

    def torque(self, servo_id, enable=True):
        self._write(build_write(servo_id, ADDR_TORQUE_ENABLE, [1 if enable else 0]))

    def request_position(self, servo_id):
        self._write(build_packet(servo_id, INST_READ,
                                 [ADDR_PRESENT_POSITION, 2]))
