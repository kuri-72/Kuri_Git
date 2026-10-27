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
| 设备主机名 | DESKTOP-4JAFHLD |
| 角色 | 同步设备 1（笔记本） |
| Python 版本 | **3.14.0** ⚠️ 与主设备 3.13.15 不一致 |
| Python 可执行文件路径 | `C:\Users\NERV_Note_02\xiao72-venv\Scripts\python.exe` |
| venv 路径 | `C:\Users\NERV_Note_02\xiao72-venv`　⚠️ **在仓库外**，仓库下没有 `xiao72\.venv` |
| 操作系统版本 | Windows 11 家庭版 10.0.26200 |
| 仓库路径 | `C:\Users\NERV_Note_02\Desktop\git` |
| X72_PROVIDER | deepseek |
| X72_MODEL | deepseek-chat（.env 未显式设置，走默认） |
| X72_MODEL_DIR | `C:\Users\NERV_Note_02\AppData\Local\xiao72\models` |
| ASR 模型尺寸 | small（faster-whisper, int8, CPU） |
| 是否用 GPU | 否，CPU int8（本机是 Intel Arc 140T，无 NVIDIA） |
| X72_TTS_ENGINE | edge |
| X72_TTS_VOICE | zh-CN-XiaoxiaoNeural（语速 +25%，在 settings.json 里） |
| 串口 | 灯控板 **COM13**（靠 `[I?]` 握手自动发现，不写死）；K230 注视板占 **COM12** |
| 模型目录实际路径 | `C:\Users\NERV_Note_02\AppData\Local\xiao72\models` |
| 模型文件总数 / 总大小 | **8 个 / 465.9 MB** |
| silero_vad.onnx SHA256 | `1A153A22F4509E292A94E67D6F9B85E8DEB25B4988682B7E174C65279D8788E3` |

### 模型文件清单

| 相对路径 | 字节 |
|---|---:|
| `silero_vad.onnx` | 2,327,524 |
| `CACHEDIR.TAG` | 195 |
| `models--Systran--faster-whisper-small/refs/main` | 40 |
| `models--Systran--faster-whisper-small/snapshots/536b0662.../config.json` | 2,370 |
| `models--Systran--faster-whisper-small/snapshots/536b0662.../model.bin` | 483,546,902 |
| `models--Systran--faster-whisper-small/snapshots/536b0662.../tokenizer.json` | 2,203,239 |
| `models--Systran--faster-whisper-small/snapshots/536b0662.../vocabulary.txt` | 459,861 |
| `models--Systran--faster-whisper-small/trees/536b0662...json` | 867 |

> `536b0662...` = `536b0662742c02347bc0e980a01041f333bce120`

### 本机特有的坑

1. **Python 3.14 而不是 3.13**：`ctranslate2==4.8.3`、`onnxruntime==1.31.0`（主设备是 4.8.4 / 1.31.1）。
   版本锁见 `xiao72/requirements.lock.txt`。主设备若要完全复刻，建议直接用这份锁。
2. **venv 在仓库外**（`C:\Users\NERV_Note_02\...`），不是仓库内的 `xiao72\.venv`。
   `run_voice.bat` / `run_ui.bat` 通过 `.env` 里的 `X72_PYTHON` 找解释器，不依赖固定路径。
3. **两个串口同时占**：COM13（灯）/ COM12（K230）。换设备顺序会变，靠握手识别。
4. **模型首次加载 ~3.5 秒**（small / CPU int8），不是"20 秒"那个提示。


## 五、完成后

- 提交信息用 `docs: 环境交接回执`
- `push` 成功后，告诉用户「交接材料已推」
- 主设备收到后会删除本文件

---

## 附：两台机器的分工建议（同步设备 1 补充，供参考）

**不要试图把两台复刻成一样**——硬件差异太大，复刻只会两个都别扭。

| | 笔记本（DESKTOP-4JAFHLD） | 台式机 / 4090 |
|---|---|---|
| 强项 | 麦、串口、显示器都在这台；人也在 | GPU |
| 弱项 | **无 NVIDIA**（Intel Arc 140T） | 不在手边 |
| 适合干 | 录音 / ASR / UI / 串口 / K230 目视 | 本地 8B~14B、SoVITS、批量转换 |
| 不适合 | 任何吃 CUDA 的活 | 需要麦克风和串口的活 |

**真正需要对齐的**，只有「能跑通的基础依赖」这一层：

```
faster-whisper + ctranslate2 + onnxruntime  → ASR
sounddevice + soundfile + numpy             → 采集与播放
pywebview + pythonnet + flask               → 界面
pyserial                                    → 串口
```

`requirements.lock.txt` 就是这套东西的版本快照。**其余差异（Python 3.14 vs 3.13）不必强行拉平**——
各自用自己跑得动的版本，接口是 HTTP / 串口，不是共享进程。

如果哪天要做「笔记本听、台式机想」，中间是局域网 HTTP，不是代码复用。

