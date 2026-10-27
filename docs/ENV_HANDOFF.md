# 环境交接（一次性）

> 用途：主设备（DESKTOP-EMH2SNR）复刻同步设备 1 上能跑的小72运行环境。
> 办完即删，不要长期保留。
> 执行方：同步设备 1 上的 AI 助手。按 `AGENTS.md`：先 `git pull`，小步改，提交后 `push`。

## 一、主设备现状（已就绪，不用处理）

- 仓库：`C:\Users\ROG\Desktop\Kuri_Git`
- venv：`xiao72\.venv`，Python **3.13.15**
- 依赖已按 `requirements.txt` 装好：
  - ctranslate2 4.8.4 / onnxruntime 1.31.1 / pywebview 6.2.1 / pythonnet 3.2.1
  - faster-whisper 1.2.1 / edge-tts 7.3.1 / soundfile 0.14.0 / sounddevice 0.5.6
  - flask 3.1.3 / numpy 2.5.4 / pyserial 3.5
- WebView2 运行时：155.0.4283.62（已装）
- **缺**：模型文件、API key、版本对齐

## 二、需要你这台做的事

### 1. 导出版本锁（提交 `xiao72/requirements.lock.txt`）

```powershell
cd <你的仓库>\xiao72
.venv\Scripts\python.exe --version
.venv\Scripts\python.exe -m pip freeze > requirements.lock.txt
```

如果 `pip freeze` 里有 `-e ...` 这类本地路径条目，删掉那几行再提交。

### 2. 填写文末「回执」表格

把 `<...>` 换成实际值，只填非密钥内容。**不要写 API key。**

### 3. 给出模型清单（只提交清单，不提交模型文件）

模型约 480 MB，**禁止提交进仓库**。请提供文件清单与校验值：

```powershell
# 若设了 X72_MODEL_DIR 用你的路径，否则默认如下
$md = if ($env:X72_MODEL_DIR) { $env:X72_MODEL_DIR } else { "$env:LOCALAPPDATA\xiao72\models" }
Get-ChildItem $md -Recurse -File | Select-Object FullName, Length | Sort-Object FullName

Get-FileHash "$md\silero_vad.onnx" -Algorithm SHA256
```

把「文件相对路径 + 字节数」和 `silero_vad.onnx` 的 SHA256 填进回执。

> 模型本体由用户用 U 盘 / 网盘从你那台拷到主设备，**不走 git**。

## 三、禁止

- 不要提交 `.env`、API key、token、任何密钥
- 不要提交模型二进制（>100 MB）
- 不要修改 `AGENTS.md` 或新增流程文件

## 四、回执（由同步设备 1 填写）

| 项目 | 值 |
|---|---|
| 设备主机名 | `<DESKTOP-4JAFHLD>` |
| 角色 | `<同步设备 1>` |
| Python 版本 | `<3.x.y>` |
| Python 可执行文件路径 | `<...>` |
| venv 路径 | `<...>` |
| 操作系统版本 | `<Windows 11 24H2 ...>` |
| 仓库路径 | `<...>` |
| X72_PROVIDER | `<deepseek / qwen / ...>` |
| X72_MODEL | `<...>` |
| X72_MODEL_DIR | `<...>` |
| ASR 模型尺寸 | `<small / medium / ...>` |
| 是否用 GPU | `<否，CPU int8 / 是，CUDA>` |
| X72_TTS_ENGINE | `<edge / sapi>` |
| X72_TTS_VOICE | `<...>` |
| 串口 | `<COMx / 自动探测>` |
| 模型目录实际路径 | `<...>` |
| 模型文件总数 / 总大小 | `<N 个 / xxx MB>` |
| silero_vad.onnx SHA256 | `<...>` |
| 模型文件清单 | `<贴 Get-ChildItem 的相对路径+大小，可折叠>` |
| 本机特有的坑 | `<启动慢 / 需要代理 / 音频设备名怪 ...>` |

## 五、完成后

- 提交信息用 `docs: 环境交接回执`
- `push` 成功后，告诉用户「交接材料已推」
- 主设备收到后会删除本文件
