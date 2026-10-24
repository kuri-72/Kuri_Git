# Keil 工程使用说明

> 2026-10-25 跨设备协商结论落地。
> 目标：**任何设备 clone 仓库后，不用重建工程、不用重新加文件，直接 F7 能编译。**

---

## 1. 工程位置

```
xiao72/firmware/
├── x72_proto.c/.h        ← 协议解析（唯一真源）
├── x72_port.c/.h         ← 平台无关层
├── USART1.c              ← 串口收发（含 [I?] 应答）
├── x72_app.c/.h          ← OLED 显示
├── main_project.c        ← 主循环模板（PC 参考用）
├── stm32_keil/           ← ★ Keil 工程就在这里
│   ├── Project.uvprojx
│   ├── Project.uvoptx
│   ├── keilkill.bat
│   ├── Start/            启动文件 + CMSIS
│   ├── Library/          StdPeriph V3.5.0（46 个）
│   ├── System/           Delay
│   ├── Hardware/         LED / Key / OLED / PWM
│   ├── User/             main.c / stm32f10x_it.c / conf.h
│   └── (无 Xiao72/ 目录，旧副本已删)
├── sim/sim_main.c        PC 模拟器（不进 Keil 工程）
└── template/x72_port_stm32.c  参考实现（不进 Keil 工程）
```

**关键设计**：`stm32_keil/Project.uvprojx` 里的共享源码用的是
**相对路径 `..\x72_proto.c` / `..\main_project.c`**，指向上级 `firmware/` 目录。
所以**源码只有一份**，Keil 里编辑就是编辑共享文件。

---

## 2. 编译单元清单（重要，加错会链接失败）

**必须加入**（`User` 组放 main，`Xiao72` 组放协议与硬件）：

```
..\main_project.c          ← 主循环（唯一 main，原 User\main.c 已删）
..\x72_proto.c  ..\x72_proto.h
..\x72_port.c   ..\x72_port.h
..\USART1.c
..\x72_app.c    ..\x72_app.h
```

**绝对不能加**（会重复定义）：

| 文件 | 为什么 |
|---|---|
| `sim/sim_main.c` | 它有自己的 `main()`，与 `main_project.c` 冲突 → `L6200E` |
| `template/x72_port_stm32.c` | 与 `USART1.c`/`x72_port.c` 重复定义 `USART1_IRQHandler`、`x72_tick_ms`、`x72_led_write` |

> **历史教训**：曾经 `main_project.c` 与 `User\main.c` 同时存在（只差一行开机帧），
> 工程实际编译的是 `User\main.c`，导致"改了 `main_project.c` 却不生效"的陷阱。
> 现已统一为 `main_project.c` 一份。

---

## 3. 编译

### 图形界面

Keil 打开 `xiao72/firmware/stm32_keil/Project.uvprojx` → `F7`。

### 命令行（可脚本化）

```powershell
$uv4 = "E:\Nerv32\UV4\UV4.exe"      # 本机 Keil 路径
& $uv4 -b "E:\kuri\xiao72\firmware\stm32_keil\Project.uvprojx" -j0 -o "$env:TEMP\build.log"
```

**退出码**：`0` 无错无警告 / `1` 有警告 / `2` 有错误 / `3` 致命。

---

## 4. 烧录

ST-Link 接好后：

```powershell
& $uv4 -f "E:\kuri\xiao72\firmware\stm32_keil\Project.uvprojx" -j0 -o "$env:TEMP\flash.log"
```

成功日志末尾应是：

```
Erase Done.Programming Done.Verify OK.Application running ...
```

---

## 5. 身份握手 `[I?]`（v0.4 新增）

CH340 没有 USB 序列号，靠**设备自报身份**区分多台板子。

```
PC  → [I?\n
设备 → [I x72-led|X72-LED|1.0|led,brightness,period]
```

- 身份可在 **Keil → Options → C/C++ → Define** 里覆盖，不用改源码：
  `X72_DEVICE_ID="x72-led"`、`X72_DEVICE_MODEL="X72-LED"`、`X72_DEVICE_CAPS="led,brightness,period"`
- 实现位置：`x72_proto.c` 的 `dispatch_line()` **最前面**一个 `if` 分支，
  **只认 `L` 帧的原有逻辑一行未动**。
- 老固件收到 `[I?]` 会按非法帧丢弃（`E` 计数 +1），不影响运行。

---

## 6. 源码唯一真源

**唯一真源是 `xiao72/firmware/`**（含 `main_project.c` 与 7 个共享源文件）。

- `stm32_keil/` 里**不再保存任何源码副本**（旧 `Xiao72/` 目录已于 2026-10-25 删除）
- 工程通过 `..\xxx.c` 相对路径引用上级目录
- 因此：**在 Keil 里编辑源码 = 编辑仓库里的文件**，不会出现两份漂移

若要新增源文件，请加到 `xiao72/firmware/`，再把工程的 `<FilePath>` 指到 `..\新文件.c`。
## 7. .gitignore 规则（Keil 部分）

`Objects/` 单目录就有 **26.1 MB**，必需排除。完整规则见 `xiao72/.gitignore`：

```
Objects/  Listings/  DebugConfig/
*.hex *.bin *.axf *.o *.d *.crf *.dep *.lnp *.htm *.map *.lst *.sct
*.scvd  JLinkLog.txt  EventRecorderStub.scvd
Project.uvguix.*  *.bak *.bak2 *.orig
```

**保留提交**：`Library/`、`Start/`、`Project.uvprojx`、`Project.uvoptx`、`keilkill.bat`
（`uvoptx` 含调试器配置，提交后换设备调试设置也一致）

---

## 8. 换设备上手步骤

```powershell
git clone https://github.com/kuri-72/Kuri_Git.git
# 用 Keil 打开 xiao72/firmware/stm32_keil/Project.uvprojx
# F7 编译 → 接 ST-Link → F8 烧录
```

**不需要**：新建工程、重新添加文件、改 Include Path。

---

## 9. 实测记录（2026-10-25 03:43）

| 项 | 结果 |
|---|---|
| 基线（原位置、旧副本） | 0 Error / 0 Warning，8.4s |
| 新位置（引用 `..\` 共享源码） | 首次 **1 Error**：`USART1.c: NULL undefined` |
| 修复 | `USART1.c` 补 `#include <stddef.h>` |
| 复编 | **0 Error / 0 Warning** |
| 代码尺寸 | Code=6544  RO-data=1788  RW-data=64  ZI-data=1744 |
| 第 2 轮 Q1 改动后 | 改引用 `..\main_project.c`、删 `User\main.c`、开机帧改 `X72_BOOT_FRAME`（默认关） |
| 改动后编译 | **0 Error / 0 Warning**，Code=6456（少 88 字节，因开机帧未编入） |
| 改动后烧录 | `Programming Done. Verify OK.` |
| 改动后握手 | `[I x72-led\|X72-LED\|1.0\|led,brightness,period]` ✅ |

### 掌机独立复现（2026-10-25 04:05）

| 项 | 结果 |
|---|---|
| Keil | UV4 **5.24.2.0**，安装于 `C:\Nerv32\UV4`（笔记本为 `E:\Nerv32\UV4`，仅盘符不同） |
| 命令 | `UV4.exe -b Project.uvprojx -j0 -o build.log` |
| 结果 | **0 Error / 0 Warning**，Code=6456 RO=1788 RW=64 ZI=1744，8s |
| FilePath 核对 | 74/74 全部存在，0 缺失 |
| 旧副本 | `User\main.c`、`stm32_keil\Xiao72\` 均已删除，无残留引用 |
| 编译产物 | `Objects/Project.axf` 被 `.gitignore` 正确忽略 |

> **更正**：本文件上一版写着"掌机没有 C 编译器"，是错的——掌机同样装有 Keil（UV4 5.24.2.0）。
> 正确约定：**改动共享源码或工程文件的一方，必须自证 F7 通过**；无法编译时在 commit message 里标 `[未编译验证]`。

---

## 10. 协作约定（2026-10-25 第 2 轮共识）

| 约定 | 内容 |
|---|---|
| **谁改谁编译** | 改工程或共享源码的一方，push 前必须自己 F7 一次 |
| **必须贴摘要** | `0 Error / 0 Warning` + 代码尺寸 |
| **无法编译要声明** | commit message 含 `[未编译验证]`，不得默认通过 |
| **uvprojx 改动** | 由改动方负责 F7 |
| **先 pull 再改** | 改共享文件前先 `git pull`；冲突就地合并，不覆盖对方 |
| **开机行为** | `X72_BOOT_FRAME` 默认关闭；开关语义见下 |

### 宏开关语义（别混用）

| 宏 | 语义 | 默认 |
|---|---|---|
| `X72_SELF_TEST` | 跑自检：周期性重复注入测试帧 | 关闭 |
| `X72_BOOT_FRAME` | 产品行为：上电点亮一帧 `[L01002000\|A---\|]`（100%/2s） | **关闭** |
| `X72_USE_OLED` | 是否启用 OLED 显示 | 见源码默认 |

> 为什么 `X72_BOOT_FRAME` 默认关：开机强制 100%/2s 会**覆盖用户上次设定**，
> 与"各模块各司其职、没提到就不动"的原则冲突。演示"上电即亮"时才打开。