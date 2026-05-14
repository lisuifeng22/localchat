# localchat 火山引擎豆包语音修复说明

这版修复了火山引擎豆包 TTS V3 接入失败的问题，尤其是：

- V3 HTTP Chunked 返回的 JSON/base64 音频块解析。
- 本地 OmniVoice 不再强制启动，火山引擎模式可独立运行。
- 修复豆包 2.0 默认配置：`seed-tts-2.0` 必须配 2.0 音色，默认改为 `zh_female_vv_uranus_bigtts`。
- `resource_id` 支持 `auto`，会根据音色自动推断：
  - `*_uranus_*` -> `seed-tts-2.0`
  - `*_mars_*` / `*_moon_*` / `*_jupiter_*` / `*_saturn_*` -> `seed-tts-1.0`
  - `S_` / `ICL_` 开头 -> `seed-icl-1.0`
- 如果用户显式配置了不匹配组合，例如 `seed-tts-2.0 + zh_female_cancan_mars_bigtts`，会在本地直接给出清楚报错，不再让火山接口返回 `55000000`。

## 重要：如果你已经生成了 config.json

默认配置文件 `config.py` 改了以后，不会自动覆盖已有的 `config.json`。如果你之前已经运行过程序，请手动修改项目根目录的 `config.json`：

```json
"voice": {
  "tts_provider": "volcengine",
  "stt_provider": "local",
  "volcengine": {
    "app_id": "你的 App ID",
    "access_token": "你的 Access Token / Access Key",
    "api_key": "",
    "resource_id": "auto",
    "audio_format": "mp3",
    "sample_rate": 24000,
    "voice_type": "zh_female_vv_uranus_bigtts",
    "model": ""
  }
}
```

如果你要继续用 `zh_female_cancan_mars_bigtts`，那它不是 2.0 默认音色，请改成：

```json
"resource_id": "seed-tts-1.0",
"voice_type": "zh_female_cancan_mars_bigtts"
```

如果你要用豆包语音合成 2.0，请用类似：

```json
"resource_id": "seed-tts-2.0",
"voice_type": "zh_female_vv_uranus_bigtts"
```

更推荐直接用：

```json
"resource_id": "auto"
```

## 安装和运行

```bash
pip install -r requirements.txt
python web/server.py
```

测试：

```bash
curl -X POST http://127.0.0.1:8000/api/tts ^
  -H "Content-Type: application/json" ^
  -d "{\"text\":\"你好，我是豆包语音合成二点零。\",\"speed\":1.0}" ^
  --output test.mp3
```


## v3：删除旧版控制台设置

本次按“保留新版控制台 API Key，删除旧版控制台 App ID / Access Key”的要求处理：

- `config.py` / `config.example.json`：删除 `app_id`、`access_token` 默认项。
- `web/server.py`：删除 `/api/config` 中旧版控制台字段的读取、返回和保存。
- `web/audio_processor.py`：报错提示改为新版控制台 API Key，避免界面已经删除旧版字段后仍提示旧版字段。
- `patch_remove_old_console.py`：用于修改你仓库里已有的 `web/static/index.html`，因为这个前端文件上次包里没有覆盖。运行后会只删除设置界面里的旧版控制台 App ID / Access Key / “或者”分隔线，并保留 API Key（新版控制台）、Resource ID、默认音色等内容。

### 使用方式

把本包覆盖到项目根目录后，额外执行一次：

```bash
python patch_remove_old_console.py
```

脚本会给被修改文件生成 `.bak` 备份。
