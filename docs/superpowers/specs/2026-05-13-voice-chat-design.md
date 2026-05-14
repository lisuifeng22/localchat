# 语音聊天功能设计

## 概述

为 Local AI Chat Web 版新增语音聊天功能，支持语音输入（STT）和语音回复（TTS），采用本地模型方案，完全离线运行。

## 架构

### 数据流

```
用户点击🎤录音 → MediaRecorder(audio/webm)
    → POST /api/stt → faster-whisper 转文字
    → 文字填入输入框（用户可修改后发送）
    → POST /api/chat（已有 SSE 流）
    → AI 回复消息气泡右下角 🔊 按钮
    → POST /api/tts → ChatTTS 合成语音
    → 浏览器 <audio> 播放
```

### 新增文件

| 文件 | 说明 |
|------|------|
| `web/audio_processor.py` | STT + TTS 逻辑封装，模型懒加载 |

### 改动文件

| 文件 | 改动说明 |
|------|---------|
| `web/server.py` | 新增 `/api/stt` 和 `/api/tts` 两个路由 |
| `web/static/index.html` | 录音按钮、播放按钮、交互逻辑（~200行 JS/HTML） |
| `requirements.txt` | 增加 `faster-whisper` 和 `ChatTTS` |

## 新增模块：AudioProcessor

```python
class AudioProcessor:
    - _load_stt():  懒加载 faster-whisper（GPU优先）
    - _load_tts():  懒加载 ChatTTS（GPU自动）
    - transcribe(audio_bytes) -> {"text", "duration_ms"}
    - synthesize(text, speed) -> bytes(wav)
```

- STT 首次调用时下载 tiny 模型（~75MB）
- TTS 首次调用时下载 ChatTTS（~200MB）
- TTS 合成结果缓存到 `generated/tts_<hash>.wav`

## API 设计

### POST /api/stt
- Content-Type: multipart/form-data
- 参数: `file` (audio/webm)
- 返回: `{"text": "识别的文字", "duration_ms": 2340}`

### POST /api/tts
- Content-Type: application/json
- 参数: `{"text": "要合成语音的文字", "speed": 1.0}`
- 返回: audio/wav 二进制流

## 前端交互

### 录音
- 点击 🎤 按钮 → `MediaRecorder` 开始录音
- 按钮变红色脉冲动画，显示录音时长
- 再次点击 → 停止录音，自动上传 STT
- 识别结果填入输入框（不自动发送）

### 播放
- AI 消息气泡右下角 🔊 按钮
- 点击 → 调 TTS API → `<audio>` 播放
- 播放中图标变暂停

## 依赖

```txt
faster-whisper>=1.0.0
ChatTTS>=0.1.0
```

首次调用时自动下载模型到 huggingface cache。
