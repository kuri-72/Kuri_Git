# 环境交接（2026-10-27，已完成）

> 一次性文档。交接已完成，保留作记录；确认无用后可删除。
> 参与方：主设备 `DESKTOP-EMH2SNR`（ROG）、同步设备 1 `DESKTOP-4JAFHLD`（笔记本）

## 一、主设备结果（已就绪）

- venv：`xiao72\.venv`，Python **3.13.15**
- 依赖：`requirements.txt` 安装完成（ctranslate2 4.8.4 / onnxruntime 1.31.1 / pywebview 6.2.1 / faster-whisper 1.2.1 / edge-tts 7.3.1 / flask 3.1.3）
- 模型：Whisper `small` CT2（463.7 MB）+ `silero_vad.onnx`（2.2 MB）
  - `%LOCALAPPDATA%\xiao72\models\faster-whisper-small\`
  - `%LOCALAPPDATA%\xiao72\models\silero_vad.onnx`
- API key：已由用户填入本机 `.env`（不提交）
- 启动：桌面 `小72.lnk` → `pythonw.exe run_ui.py`，冒烟通过（HTTP 200，窗口正常）

## 二、同步设备 1 回执

| 项目 | 值 |
|---|---|
| 设备主机名 | `DESKTOP-4JAFHLD` |
| 角色 | 同步设备 1（笔记本） |
| Python 版本 | **3.14.0** |
| Python 路径 | `C:\Users\NERV_Note_02\xiao72-venv\Scripts\python.exe` |
| venv 路径 | `C:\Users\NERV_Note_02\xiao72-venv`（仓库外） |
| 操作系统 | Windows 11 家庭版 10.0.26200 |
| 仓库路径 | `C:\Users\NERV_Note_02\Desktop\git` |
| X72_PROVIDER | deepseek |
| X72_MODEL | deepseek-chat（默认） |
| X72_MODEL_DIR | `C:\Users\NERV_Note_02\AppData\Local\xiao72\models` |
| ASR 模型 | small / int8 / CPU |
| GPU | 无（Intel Arc 140T） |
| X72_TTS_ENGINE | edge |
| X72_TTS_VOICE | zh-CN-XiaoxiaoNeural（语速 +25%，在 settings.json） |
| 串口 | 灯控板 **COM13**（`[I?]` 握手自动发现）、K230 注视板 **COM12** |
| 模型文件 | 8 个 / 465.9 MB |
| silero_vad.onnx SHA256 | `1A153A22F4509E292A94E67D6F9B85E8DEB25B4988682B7E174C65279D8788E3` |

## 三、版本差异（两边都能跑，不必强行统一）

| 项 | 主设备 | 同步设备 1 |
|---|---|---|
| Python | 3.13.15 | 3.14.0 |
| ctranslate2 | 4.8.4 | 4.8.3 |
| onnxruntime | 1.31.1 | 1.31.0 |
| venv | 仓库内 `xiao72\.venv` | 仓库外 `~\xiao72-venv` |

- 对方的完整版本锁在 `xiao72/requirements.lock.txt`
- 启动器按 `.env` 的 `X72_PYTHON` → 仓库内 `.venv` → `~\xiao72-venv` 顺序找解释器，两边都不写死路径
- 模型首次加载约 1–3.5 秒（small / CPU int8）

## 四、备忘

- 模型目录内容不同不影响运行：主设备用扁平目录 + `X72_ASR_MODEL` 指向它；对方用 HF 缓存布局
- 串口号会随设备顺序变，靠握手识别，不要写死
