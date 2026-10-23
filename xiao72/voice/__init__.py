"""小72 语音层

目录规划（分期实现）：
    voice/
    ├─ audio/          音频设备与采集        ← 当前（P0 已完成）
    ├─ wake/           唤醒源（KWS / K230 注视）  ← 预留
    ├─ vad/            语音活动检测           ← P2
    ├─ asr/            语音识别               ← P1
    ├─ tts/            语音合成               ← P3
    └─ pipeline.py     串起整条链路           ← P3
"""

__version__ = "0.1.0"
