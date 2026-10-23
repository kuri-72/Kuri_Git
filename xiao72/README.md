# 小72 · 灯控链路 v0.1

KURI72 的 MOSS 系统第一块「垂直切片」：**文本 → 意图 → 帧 → 单片机 → PWM**。

本版范围（已确认）：只做 **LED 一路 PWM + 呼吸周期**，机械臂段保留占位不实现。

> ## 🤖 接手的 AI 助手先读这个
>
> **[docs/USER_PROFILE.md](docs/USER_PROFILE.md)** —— 用户身份、能力边界、
> 协作硬规则（先问再做、一轮一个概念、不要劝学、交付三件套）。
>
> 读完再看 [docs/MAP.md](docs/MAP.md)（项目地图）和
> [docs/GLOSSARY.md](docs/GLOSSARY.md)（代码词汇解码）。
>
> 跳过这几页就直接改代码，大概率会让用户脱节。

---

## 目录结构

```
xiao72/
├─ docs/
│  ├─ GETTING_STARTED.md ★ 从零操作手册（先看这个）
│  ├─ project_charter.md 项目章程：长期需求、边界、分阶段路线、不做什么
│  ├─ capabilities.md    能力边界与使用手册（怎么问我最有效）
│  ├─ protocol.md        帧格式规格（改协议只改这里 + 两处代码）
│  └─ intent_prompt.md   意图识别 System Prompt（直接粘给 AI 用）
├─ host/                 PC 端（Python）
│  ├─ config.py          配置 / .env 读取 / 密钥遮蔽
│  ├─ intent.py          ① 意图识别层（LLM）+ ③ 的解析校验
│  ├─ state.py           ③ 状态合并 + 协议编解码
│  ├─ serial_link.py     ④ 串口发送（可选）
│  ├─ main.py            入口（CLI）
│  ├─ check_env.py       环境自检（缺什么一目了然）
│  └─ verify.py          两端一致性验证（重要）
└─ firmware/             单片机端（C，标准库）
   ├─ x72_proto.h        对外接口
   ├─ x72_proto.c        解析器 + 非阻塞呼吸（核心，2KB 以内）
   ├─ x72_port_stm32.c   平台适配（你只改这 3 个函数）
   └─ sim_main.c         PC 模拟器（不需要板子就能测试）
```

---

## ⚡ 第一次接触？先看 [GETTING_STARTED.md](docs/GETTING_STARTED.md)

那份手册把"建工程、编译、烧录、接线、排查"拆成了带勾选框的步骤。
本 README 只讲结构和原理。

### 先跑一次环境自检

```powershell
python xiao72/host/check_env.py
```

它会告诉你缺什么、怎么补，不用猜。

---

## 现在就能跑的三件事（不需要板子、不需要 key）

### 1. 看整条链路怎么走

```powershell
cd xiao72\host
python main.py --mock --dry-run --demo
```

输出里会看到：每句话 → 意图 JSON → 完整状态帧。**这就是你要的全流程。**

### 2. 验证两端一致（最关键）

```powershell
# 先编译模拟器
cd xiao72\firmware
cl /nologo /wd4819 /DX72_NO_PORT /Fe:sim.exe sim_main.c x72_proto.c   # VS
# 或 gcc -DX72_NO_PORT -I. sim_main.c x72_proto.c -o sim.exe

cd ..\host
python verify.py
```

它会用 Python 编码 10 种状态，喂给 **C 解析器**，比对解析结果。
全绿 = 周六上板时协议不会打架。

### 3. 交互式试

```powershell
python main.py --mock --dry-run
> 灯好亮啊
> 呼吸模式慢一点
> :state
```

---

## 接真 AI（方案 B）

1. 复制 `.env.example` 为 `.env`，填入你的 key：

```ini
X72_PROVIDER=deepseek
X72_API_KEY=sk-你的key
```

2. 装依赖：

```powershell
pip install openai
pip install pyserial     # 只有要发串口时才需要
```

3. 跑：

```powershell
python main.py --dry-run      # 先只看帧
python main.py --port COM3    # 真发串口
```

> **不要把 key 贴进任何聊天窗口。** `.env` 已在 `.gitignore` 里。

支持 deepseek / qwen / moonshot / openai / ollama（本地模型），改 `X72_PROVIDER` 即可。

---

## 周六上板要做的三件事

### ① Keil 工程里加入文件
把 `x72_proto.c`、`x72_proto.h` 加入工程；`x72_port_stm32.c` **只抄里面的函数**（不要整个加，避免和你的 `SysTick_Handler`、`USART1` 冲突）。

### ② 确认三个适配点
| 位置 | 要确认 |
|---|---|
| `x72_led_write()` | 你的 PWM 是 100 级还是 1000 级，改 `X72_PWM_MAX` |
| `x72_tick_ms()` | 有没有 1ms 递增的变量；没有就在 SysTick 里加 `s_ms++` |
| USART1 中断 | 收到字节就 `x72_feed(byte)`，不要在里面做耗时操作 |

### ③ 主循环

```c
while (1) {
    if (g_rx_byte_ready) {              /* ISR 里置位 */
        x72_feed(g_rx_byte);
        g_rx_byte_ready = 0;
    }
    x72_effect_tick(x72_tick_ms());     /* 呼吸 + 平滑，非阻塞 */
    /* 你的按键逻辑放这里，完全不受影响 */
}
```

### 串口助手手工验证（不接 PC）

发这一行（**注意 4 位 + 4 位**）：

```
[L00502000|A---|]
```

含义：亮度 50%，呼吸周期 2000ms。能亮起来就说明 ⑥ 通了。

> ⚠️ **焊接/接线前必看**：PA0 在很多 F103 最小系统板上同时接了按键，
> 且 PWM 通常需要串限流电阻。上电前用万用表确认 PA0 对地没有直接短路。

---

## 设计上的三个关键决定

| 决定 | 为什么 |
|---|---|
| **AI 只输出 JSON，不输出协议** | AI 是概率模型，会加废话/换格式。协议文本由确定性代码生成，AI 挂了也只是"听不懂" |
| **每次发全量状态，不是增量命令** | 幂等。丢帧、重发、PC 重启都不会累积错误 |
| **单片机限幅而不是拒收** | 对灯来说"保持亮"比"突然灭"安全。（但**机械臂将来必须反过来**：越界即停机） |

---

## 修改协议的正确姿势

只改这三处，然后跑 `verify.py`：

1. `host/state.py` 的 `encode()` / `decode()`
2. `firmware/x72_proto.c` 的 `parse_line_impl()`
3. `docs/protocol.md` 的测试向量表

`verify.py` 全绿之前，不要上板。

---

## 已知边界（本版不做）

- 机械臂段固定 `A---`，解析器只校验首字母 `A`
- 无超时兜底（PC 掉线后灯保持最后状态）——**下一版必须加**
- 单向通信（PC → 板子），板子不回 ACK
- 无 gamma 校正（呼吸是线性三角波，看起来"中段偏快"）
