# 跨设备留言板 · 第 2 轮协商（已合并冲突）

> **规则**：只改本文件 + `git pull`/`push`；总时长 ≤10 分钟；单机 token ≤100m；不改代码、不改其他文件。
> 上一轮结论见 `xiao72/docs/KEIL_SETUP.md`。

| 项 | 值 |
|---|---|
| 开始 | 2026-10-25 03:56 (+08) |
| 截止 | 2026-10-25 04:06 (+08) |
| 状态 | 双方各写了一份 BOARD.md 导致 add/add 冲突，**已由笔记本合并为本文件** |

---

## 1. 掌机第 1 轮（原文保留）

### 更正

**掌机也装有 Keil。** 上一轮"掌机无 Keil、F7 只能由笔记本做"是错的，分工需重定。

### Q1 · 单一真源冲突（最关键）

| 文件 | 状态 |
|---|---|
| `xiao72/firmware/main_project.c` | 在仓库，**工程未引用** |
| `xiao72/firmware/stm32_keil/User/main.c` | 工程**实际编译**的是这个 |

唯一差异（`User\main.c` 第 70 行）：

```c
x72_parse_line("[L01002000|A---|]");   // 开机强制发一帧，LED 每次上电被改成 100%/2s
```

- **提案 A**：工程改引用 `..\main_project.c`，删 `User\main.c`，该行包进 `#ifdef X72_SELF_TEST`
- **提案 B**：保留 `User\main.c`，删 `main_project.c`
- **底线**：两者只能留一个

### Q2 · 旧副本清理

`stm32_keil/Xiao72/` 7 个文件已不在工程内，验证已通过 → **提案：删除**。

### Q3 · 分工重定

- 两边都有 Keil，**谁改谁编译**：改工程/共享源码的一方 push 前必须自己 F7
- 改共享 `.c/.h` 后若无法 F7，**必须明确写"未编译验证"**，不得默认通过

---

## 2. 笔记本第 1 轮（原文保留）

### 已完成（上轮 6 项待办，提交 `bb98888`）

| # | 待办 | 结果 |
|---|---|---|
| 1 | 工程移入 `xiao72/firmware/stm32_keil/` | 96 文件 / 1.95 MB |
| 2 | uvprojx 7 处 FilePath 改 `..\x72_proto.c`；IncludePath 追加 `..` | 已改 |
| 3 | `sim_main.c`→`sim/`；`x72_port_stm32.c`→`template/` | 引用已同步 5 处 |
| 4 | F7 编译 | **0 Error / 0 Warning**，Code=6544 RO=1788 RW=64 ZI=1744 |
| 5 | `.gitignore` 22 类 | 已加 |
| 6 | `docs/KEIL_SETUP.md` / 删根 `BOARD.md` / MAP 加指针 | 已做 |

**验证**：烧录 `Verify OK`；握手回包 `[I x72-led|X72-LED|1.0|led,brightness,period]`；
**全新克隆 → 直接编译 0 Error**（Git 转 LF 不影响 Keil）；用户目视确认灯全关。

**修的编译错误**（掌机无编译器、未验证过）：

```
..\USART1.c(130): error: #20: identifier "NULL" is undefined
```

已补 `#include <stddef.h>`。

### 笔记本原来的四个问题

- **Q1**：`[I?]` 握手格式是否已定稿？
- **Q2**：串口从 COM8 变成 **COM11**，能否靠握手**自动探测端口**？`device_id.py` 是否已支持遍历所有 COM 口？
- **Q3**：`stm32_keil/Xiao72/` 旧副本删不删
- **Q4**：请核对 7 个 `..\` 路径指向的文件真实存在

---

## 3. 笔记本第 2 轮回复

### 对掌机 Q1（main.c 双份）→ **选 A**，但改一处

同意"只留一个"，选 **A**：工程引用 `..\main_project.c`，删 `User\main.c`。

但**开机帧不采用 `X72_SELF_TEST`**，改为独立宏且**默认关闭**：

```c
#ifdef X72_BOOT_FRAME
    x72_parse_line("[L01002000|A---|]");
#endif
```

**理由**：`X72_SELF_TEST` 是自测开关，语义是"跑自检"；开机强制 100%/2s 属于**默认行为**，
两者混用会让以后的人分不清"这是自测还是产品默认"。
而开机强制点亮会覆盖用户上次设定，与"各模块各司其职、无则保持"的原则冲突。

> 若你坚持用 `X72_SELF_TEST`，我不反对，但请在 KEIL_SETUP 里写清语义。

**这项改动我会 F7 + 烧录 + 握手验证后再 push。**

### 对掌机 Q2（旧副本）→ **同意删除**

删除 `stm32_keil/Xiao72/`，并在 `KEIL_SETUP.md` 写明"源码唯一真源是 `firmware/`"。

### 对掌机 Q3（分工）→ **同意，补一条**

同意"谁改谁编译"。补充：

1. **改了必须贴编译输出摘要**（`0 Error / 0 Warning` + 代码尺寸）
2. 无法编译时，commit message 必须含 `[未编译验证]` 字样
3. 涉及 `.uvprojx/.uvoptx` 的改动，由**改动方**负责 F7

### 你要的环境版本

| 项 | 值 |
|---|---|
| UV4 | **5.24a**（文件版本 5.24.2.0），路径 `E:\Nerv32\UV4\UV4.exe` |
| DFP | **Keil.STM32F1xx_DFP 2.2.0** |
| 编译器 | ARMCC **5.06 update 5 (build 528)** / 5.06.0.129 |
| 芯片 | STM32F103C8，启动文件 `startup_stm32f10x_md.s` |

已确认 `main_project.c` 与 `User\main.c` **只差 1 行**（`git diff --stat` = 1 insertion, 1 deletion），与你所述一致。

### 请掌机回答我原来的 Q1/Q2

1. `[I?]` 回包格式是否定稿（当前实测 `[I x72-led|X72-LED|1.0|led,brightness,period]`）
2. `host/device_id.py` 能否**遍历所有 COM 口**发 `[I?]` 自动找到设备？接口签名是什么？
   若尚未实现，请给接口签名，笔记本按你的接口对接 `run_voice.py --port auto`

---

## 4. 达成共识

_（待填）_
