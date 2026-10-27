# 环境交接（一次性·已收窄）

> 用途：主设备（DESKTOP-EMH2SNR）对齐同步设备 1 的运行环境。
> 办完即删。
> 执行方：同步设备 1 的 AI 助手。按 `AGENTS.md`：先 `git pull`，小步改，提交后 `push`。

## 一、主设备已自行搞定（不用你处理）

- venv：`xiao72\.venv`，Python **3.13.15**
- 依赖：按 `requirements.txt` 安装完成（ctranslate2 4.8.4 / onnxruntime 1.31.1 / pywebview 6.2.1 / faster-whisper 1.2.1 / edge-tts 7.3.1 / flask 3.1.3 …）
- 模型：Whisper `small`（463.7 MB，CT2 多语言版）+ `silero_vad.onnx`（2.2 MB），已下载到
  `%LOCALAPPDATA%\xiao72\models\faster-whisper-small\` 和 `…\models\silero_vad.onnx`
- API key：已由用户填入本机 `.env`
- 桌面快捷方式：已创建并冒烟通过（HTTP 200、窗口正常）

## 二、只剩两件事

### 1. 提交 `xiao72/requirements.lock.txt`

```powershell
cd <你的仓库>\xiao72
.venv\Scripts\python.exe --version
.venv\Scripts\python.exe -m pip freeze > requirements.lock.txt
```

`pip freeze` 里若有 `-e ...` 本地路径行，删掉再提交。

### 2. 填写下面的回执（只填非密钥内容，**禁止写 API key**）

## 三、禁止

- 不提交 `.env`、API key、token
- 不提交模型二进制
- 不改 `AGENTS.md` 或新增流程文件

## 四、回执（同步设备 1 填写）

| 项目 | 值 |
|---|---|
| 设备主机名 | `<DESKTOP-4JAFHLD>` |
| Python 版本 | `<3.x.y>` |
| venv 路径 | `<...>` |
| 操作系统版本 | `<Windows 11 ...>` |
| 仓库路径 | `<...>` |
| X72_PROVIDER | `<deepseek / qwen / ...>` |
| X72_MODEL | `<...>` |
| ASR 模型尺寸 | `<small / medium / ...>` |
| 是否用 GPU | `<否，CPU int8 / 是，CUDA>` |
| X72_TTS_ENGINE | `<edge / sapi>` |
| X72_TTS_VOICE | `<...>` |
| 串口 | `<COMx / 自动探测>` |
| 模型目录 | `<...>` |
| 本机特有的坑 | `<启动慢 / 需要代理 / 音频设备名怪 ...>` |

## 五、完成后

- 提交信息：`docs: 环境交接回执`
- `push` 后告诉用户「交接材料已推」
- 主设备收到后删除本文件
