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
│   └── Xiao72/           ⚠ 旧副本，验证通过后可删（见第 6 节）
├── sim/sim_main.c        PC 模拟器（不进 Keil 工程）
└── template/x72_port_stm32.c  参考实现（不进 Keil 工程）
```

**关键设计**：`stm32_keil/Project.uvprojx` 里 7 个 Xiao72 文件用的是
**相对路径 `..\x72_proto.c`**，指向上级 `firmware/` 目录。
所以**源码只有一份**，Keil 里编辑就是编辑共享文件。

---

## 2. 编译单元清单（重要，加错会链接失败）

**必须加入**（`Xiao72` 组）：

```
x72_proto.c   x72_proto.h
x72_port.c    x72_port.h
USART1.c
x72_app.c     x72_app.h
```

**绝对不能加**（会重复定义）：

| 文件 | 为什么 |
|---|---|
| `main_project.c` | 它是参考模板，和 `User/main.c` 都定义 `main()` → `L6200E` |
| `sim/sim_main.c` | 同上，PC 模拟器专用 |
| `template/x72_port_stm32.c` | 与 `USART1.c`/`x72_port.c` 重复定义 `USART1_IRQHandler`、`x72_tick_ms`、`x72_led_write` |

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

## 6. `Xiao72/` 旧副本怎么处理

建工程时曾把 7 个源文件复制进 `stm32_keil/Xiao72/`。
现在工程已改为引用 `..\`，这个目录**不再参与编译**。

- **暂不删除**，作为回滚保险。
- 确认新路径编译 + 烧录 + 灯正常后，可执行：
  ```powershell
  Remove-Item -Recurse -Force E:\kuri\xiao72\firmware\stm32_keil\Xiao72
  ```
- 注意：删掉后若有人把工程 FilePath 改回 `.\Xiao72\`，会找不到文件。

---

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
| 烧录 | `Programming Done. Verify OK.` |
| 握手验证 | `[I x72-led|X72-LED|1.0|led,brightness,period]` ✅ |

> **教训**：掌机没有 C 编译器，它改的固件代码未经编译验证。
> 跨设备协作时，**必须由有工具链的一方做编译验证**。
