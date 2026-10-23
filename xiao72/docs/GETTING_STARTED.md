# 从零跑起来 · 操作手册（给 KURI72）

> 你现在的状态：**有板子、有 Keil、有 Python，但没有串口模块（周六才有）**。
> 所以本手册分 4 个阶段，**前 3 个阶段现在就能做完**，第 4 阶段等周六。

**每一步都有"怎么确认成功"，卡住了直接看对应阶段的排查表。**

---

## 全景图：你要建的是两个独立工程

```
┌─────────────────────┐          ┌──────────────────────┐
│  PC 端（Python）     │  串口线   │  单片机端（Keil C）    │
│  host\main.py        │ ───────► │  x72_proto.c         │
│  跑在 Windows 上      │  115200  │  烧在 STM32F103 上    │
└─────────────────────┘          └──────────────────────┘
        ↑                                  ↑
   用 PyCharm 打开                   用 Keil 打开
```

**关键认知**：这是**两个完全独立的程序**，各自编译、各自运行，只通过串口上的一行文本通信。
不是"一个工程里跑两种语言"。这点搞清楚，后面就不慌了。

---

## 阶段 0 · 环境自检（5 分钟，现在就能做）

### 0.1 检查 Python

打开 PowerShell（Win+X → 终端），输入：

```powershell
python --version
```

**期望**：`Python 3.x.x`

- 如果报"不是内部或外部命令" → Python 没装或没加 PATH，去 python.org 装（**安装时勾选 Add Python to PATH**）
- 如果有 Microsoft Store 弹窗 → 在"设置 → 应用执行别名"里关掉 python.exe 和 python3.exe

### 0.2 装依赖

```powershell
pip install openai
```

**期望**：`Successfully installed openai-...`

> `pyserial` 现在**不用装**，等周六有串口模块了再装。

### 0.3 跑我准备的自检脚本

```powershell
cd C:\Users\ROG\Documents\deepseek-harness\default-workspace\xiao72
python host\check_env.py
```

**期望**：看到几行 `[OK]`。

**这一步过了，说明 PC 端能跑。** 后面出问题就能确定不是 Python 的问题。

---

## 阶段 1 · PC 端跑通（10 分钟，无需硬件、无需 API key）

这是**最重要的一步**：先证明"文本→意图→帧"这段是通的。

### 1.1 跑内置演示

```powershell
cd C:\Users\ROG\Documents\deepseek-harness\default-workspace\xiao72\host
python main.py --mock --dry-run --demo
```

**期望看到**（这就是成功的样子）：

```
==============================================================
  小72 · 灯控链路 v0.1
  意图层：MockParser（离线规则版，不需要 key）
  输出：DRY-RUN（只打印帧）
==============================================================

> 灯好亮啊
  小72：已调暗
  意图：{'cmd': 'set_led', 'say': '已调暗', 'brightness': 40, 'period_ms': 0}
  帧  ：[L00400000|A---|]   (17 字节)
```

### 1.2 交互式玩一下

```powershell
python main.py --mock --dry-run
```

然后输入：

```
灯好亮啊
呼吸模式慢一点
全亮
:state
:quit
```

**期望**：每句话都出一个帧，`:state` 显示当前状态。

### 1.3 跑两端一致性验证

```powershell
cd ..\firmware
# 先编译模拟器（VS2022 已装，用这个）
```

打开一个 **"x64 Native Tools Command Prompt for VS 2022"**（开始菜单搜 `x64 Native`），cd 到 firmware 目录：

```
cl /nologo /wd4819 /DX72_NO_PORT /Fe:sim.exe sim_main.c x72_proto.c
```

然后：

```
cd ..\host
python verify.py
```

**期望**：`结果：全部通过`

> ⚠️ 我第一次给你交付的 sim.exe 已经编译好了，**你可以跳过编译直接用**。
> 但如果以后改了 C 代码，必须重新编译。

**阶段 1 完成的标志：`verify.py` 全绿。**

---

## 阶段 2 · Keil 工程（20 分钟，无需硬件）

这是你最不确定的部分，我拆成最小步骤。

### 2.1 关键决策：新建工程 还是 改现有工程？

**推荐：改你现有的小夜灯工程。**

理由：你已经有 **PWM 初始化**和**按键逻辑**，这些是新建工程要重写的。
我们要做的只是"加一个串口 + 加两个文件"。

> 如果你怕改坏：先把整个工程文件夹**复制一份**备份，改备份。

### 2.2 把文件加进工程

1. 打开 Keil，打开你小夜灯工程的 `.uvprojx`
2. 在左侧 `Project` 窗口，**右键 `Source Group 1`（或任意组）→ Add Existing Files to Group...**
3. 文件类型选 `All files (*.*)`
4. 到 `xiao72\firmware\` 目录，选 **`x72_proto.c`**，点 Add
5. 再 Add **`x72_proto.h`**（头文件可选，但一起加更省事）
6. 关掉对话框

**期望**：左侧工程树里能看到 `x72_proto.c`。

### 2.3 加头文件搜索路径

1. 点工具栏的魔术棒图标（`Options for Target`）
2. 选 `C/C++` 标签页
3. 在 `Include Paths` 右边点 `...`
4. 新建一个路径，指向 `xiao72\firmware\`
5. OK 保存

> **不做这步的后果**：编译报 `cannot open source input file "x72_proto.h"`。

### 2.4 把 3 个端口函数复制进你的工程

打开 `xiao72\firmware\x72_port_stm32.c`，**不要整个加进工程**（会和你的中断函数重复定义）。

需要复制到你现有某个 `.c` 文件里的，只有这 3 个函数：

| 函数 | 做什么 |
|---|---|
| `x72_tick_inc()` + `x72_tick_ms()` | 毫秒计时 |
| `x72_led_write()` | 亮度 → PWM |
| `x72_on_error()` | 空实现即可 |

然后在你的 `SysTick_Handler` 里加**一行**：

```c
void SysTick_Handler(void)
{
    /* 你原来的代码 */
    x72_tick_inc();     /* ← 只加这一行 */
}
```

> 江科大工程的 `SysTick_Handler` 一般在 `delay.c` 里，去找一下。

### 2.5 确认 PWM 级数

打开你的 `PWM_Init`，找 `TIM_Period`：

| TIM_Period | 那 X72_PWM_MAX 应该是 |
|---|---|
| 100 | 100 |
| 999 | 999 |
| 99 | 99 |

**设错的症状**：灯到不了最亮，或者 50% 时就已经全亮。

### 2.6 第一次编译：先用"写死的帧"验证，不碰串口

在 `main.c` 里写：

```c
#include "x72_proto.h"

int main(void)
{
    /* 你原有的初始化 */
    PWM_Init();
    /* ... */

    /* ★ 测试：直接喂一帧进去，绕过串口 */
    x72_parse_line("[L00502000|A---|]");   /* 亮度 50%，呼吸 2 秒 */

    while (1)
    {
        x72_effect_tick(x72_tick_ms());
        /* 你的按键逻辑放这里 */
    }
}
```

**编译 + 烧录 + 上电**，期望：**灯 2 秒一次呼吸，亮度 50%**。

### ✅ 阶段 2 完成标志

灯在呼吸，且周期确实是 2 秒。

> **如果灯不呼吸**：
> - 灯完全不动 → 检查 `x72_led_write` 里的 `TIM_SetCompare1(TIM2, ...)` 是不是和你原来的 `PWM_SetCompare1` 一致
> - 呼吸但周期不对 → 检查 `x72_tick_ms()` 是否真的每 1ms 加 1（用 `LED_On()` 闪一下测）
> - 呼吸但很抖 → `X72_PWM_MAX` 设错了

---

## 阶段 3 · 加串口接收（周六，有 USB-TTL 后）

### 3.1 接线（这是最容易错的地方）

```
STM32F103           USB-TTL 模块
---------           -------------
PA9  (TX)  ──────►  RX
PA10 (RX)  ◄──────  TX
GND        ──────►  GND      ← 必须接！否则收不到数据
```

**三条铁律**：
1. **TX 接 RX，RX 接 TX**（交叉，不是直连）
2. **GND 必须连**（不共地 = 数据全是乱码）
3. **不要用 5V 供电去接 3.3V 的板子**（F103C8T6 的 IO 是 3.3V 电平）

### 3.2 初始化串口

如果你工程里已经有 `USART1_Init`，**用它**，只要确认：
- 波特率 **115200**
- 开了 **RXNE 接收中断**

如果没有，就用 `x72_port_stm32.c` 里我写的 `x72_usart1_init(115200)`，但**注意**它里面有 `USART1_IRQHandler`，别和你工程里已有的重复。

### 3.3 主循环

```c
while (1)
{
    /* 1) 收字节：中断里置标志，主循环取走（不要在中断里解析） */
    if (g_x72_rx_ready)
    {
        uint8_t b = g_x72_rx_byte;
        g_x72_rx_ready = 0;
        x72_feed(b);                 /* 喂给解析器 */
    }

    /* 2) 呼吸效果，非阻塞 */
    x72_effect_tick(x72_tick_ms());

    /* 3) 你的按键逻辑，完全不受影响 */
}
```

### 3.4 用串口助手手工验证（先别用 Python！）

1. 下载 **SSCOM** 或 **XCOM**（免费串口助手）
2. 选对 COM 口（设备管理器里看 CH340 的端口号）
3. 设置：**115200, 8, N, 1**
4. 在发送框输入（**注意是 4 位 + 4 位**）：

```
[L00502000|A---|]
```

5. 勾选"发送新行"，点发送

**期望**：灯变成 50% 亮度、2 秒呼吸。

再试：

```
[L01000000|A---|]     → 常亮 100%
[L00000000|A---|]     → 熄灭
[L00801000|A---|]     → 80% 亮度，1 秒呼吸（变快）
```

### ✅ 阶段 3 完成标志

手敲命令，灯的亮度/呼吸周期立刻变。

### 3.5 最后才用 Python 发

```powershell
cd host
python main.py --port COM3
```

（COM3 换成你的实际端口号）

---

## 阶段 4 · 接真 AI（可选，随时可做）

1. 复制 `.env.example` → `.env`
2. 填入你的 key：

```ini
X72_PROVIDER=deepseek
X72_API_KEY=sk-你的key
```

3. 先只看帧：

```powershell
python main.py --dry-run
```

4. 再真发：

```powershell
python main.py --port COM3
```

---

## 排查表（按症状查）

| 症状 | 最可能的原因 | 怎么办 |
|---|---|---|
| `python` 不是命令 | 没装或没加 PATH | 重装并勾选 Add to PATH |
| `ModuleNotFoundError: openai` | 没装 | `pip install openai` |
| Keil 报 `cannot open x72_proto.h` | Include Paths 没加 | 见 2.3 |
| Keil 报 `multiple definition of SysTick_Handler` | 端口文件整个加进去了 | 只复制 3 个函数，别加整个文件 |
| 灯完全不亮 | PWM 引脚/定时器不对 | 先确认原来的 `PWM_SetCompare1` 能亮 |
| 灯到不了最亮 | `X72_PWM_MAX` 设大了 | 按 2.5 对照表改 |
| 串口收到的全是乱码 | 波特率不对 / 没共地 | 确认 115200 且 GND 连了 |
| 串口完全没有反应 | TX/RX 接反了 | 对调一下 |
| 发命令灯不动 | 主循环没调 `x72_feed` | 检查 3.3 |
| 灯一直闪一下灭一下 | 帧长度写错（3位当成4位） | 用 `[L00502000|A---|]` 这个标准例子 |

---

## 你现在该做什么（按顺序）

- [ ] **今天**：阶段 0 + 阶段 1，跑到 `verify.py` 全绿
- [ ] **今天**：阶段 2，灯能呼吸 2 秒（这一步不需要串口！）
- [ ] **周六**：阶段 3，接线 + 串口助手手敲命令
- [ ] **随时**：阶段 4，填 key 接真 AI

**卡在哪一步，把"阶段编号 + 期望看到什么 + 实际看到什么"告诉我，我直接给你下一步。**
