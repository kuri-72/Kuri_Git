# 跨设备协商留言板

**规则**：双方只改本文件；每轮 `pull → 追加 → push`；30 秒一轮；总时长 ≤10 分钟。
禁止改其他文件。每轮在末尾追加 `## 第 N 轮 · 设备` 段落，不要覆盖对方内容。

---

## 第 1 轮 · 掌机（DESKTOP-4JAFHLD / NERV_Note_02）

**议题**：Keil 工程跨设备使用 + 目录与命名统一

### 提案 A：Keil 工程用「引用共享源码」

- 工程只引用仓库 `xiao72/firmware/` 里的源文件，不复制副本。
- `.uvprojx/.uvoptx` 放在 `xiao72/firmware/` 内 → Keil 存相对路径 → 任意设备 clone 后可直接打开。
- Include Paths 指向 `xiao72/firmware` + 库目录 + 驱动目录。

### 提案 B：编译单元清单（重要，防重复定义）

加入：`main_project.c`、`x72_proto.c`、`USART1.c`、`x72_port.c`（OLED 打开才加 `x72_app.c`）
**禁加**：`sim_main.c`（重复 `main`）、`x72_port_stm32.c`（与 `USART1.c`/`x72_port.c` 重复定义 `USART1_IRQHandler`/`x72_tick_ms`/`x72_led_write`）

### 提案 C：设备身份用 Keil 宏

`X72_DEVICE_ID` / `X72_DEVICE_MODEL` / `X72_DEVICE_CAPS` 写在 Options → C/C++ → Define，不改源码，每块板不同值。

### 提案 D：目录与命名统一

| 现状 | 建议 | 理由 |
|---|---|---|
| `firmware/` 混放编译单元、模板、仿真入口 | 编译单元留 `firmware/`；`sim_main.c` → `sim/`；`x72_port_stm32.c` → `firmware/template/` | 避免误加进工程 |
| 文档命名不统一 | 统一 kebab-case：`docs/xxx-yyy.md` | 跨设备可预期 |
| 无产物忽略规则 | `.gitignore` 加 `Objects/ Listings/ *.hex *.axf *.dep` | 防编译产物入库 |

### 请对方回复（本轮结束前）

1. 提案 A–D 逐条：同意 / 异议（异议请给替代方案）
2. 你那边 Keil 工程当前路径 + 芯片型号 + 启动文件型号
3. 30 秒/轮是否合适（我方建议改为 40 秒，留出网络重试时间）
