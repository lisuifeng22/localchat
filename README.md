# LocalChat

LocalChat 是一个本地运行的 AI 聊天客户端，支持命令行和 Web 双端使用。项目集成了多模型聊天、多会话管理、角色卡、图片生成、语音输入、语音合成等功能，适合用于个人本地 AI 助手、角色扮演聊天、语音聊天和图像生成工作流。

> 当前整理基于 GitHub 仓库 `lisuifeng22/localchat` 的 `v5` 分支。

---

## 功能概览

### 1. 多端聊天

- 支持命令行聊天入口。
- 支持 Web 聊天界面。
- 支持流式输出，模型回复可以逐步显示。
- 支持普通聊天模式和角色卡模式。

### 2. 多模型 API 接入

已实现以下模型接入方式：

- OpenAI 兼容接口
  - DeepSeek
  - 月之暗面
  - 智谱
  - OpenRouter
  - 其他兼容 `/chat/completions` 的服务
- Anthropic Claude 接口

支持配置：

- API Key
- Endpoint URL
- 模型名称
- Temperature
- Max Tokens
- System Prompt

### 3. 会话管理

项目已实现完整的多会话管理功能：

- 新建会话
- 查看会话列表
- 切换会话
- 删除会话
- 重命名会话
- 清空当前会话
- 导出会话
- 编辑单条消息
- 删除单条消息
- 重新生成回答
- 按角色隔离聊天记录

### 4. 角色卡系统

角色卡用于让 AI 按指定人物设定进行对话。已支持：

- 读取 `characters/` 目录下的 JSON 角色卡
- 新建角色
- 编辑角色
- 删除角色
- 导入角色
- 导出角色
- 角色头像
- 角色简介
- 角色性格
- 角色背景故事
- 角色说话风格
- 角色开场白
- 角色专属语音音色
- 角色独立会话记录

角色卡字段示例：

```json
{
  "name": "角色名",
  "avatar": "😀",
  "description": "角色简介",
  "personality": "性格设定",
  "backstory": "背景故事",
  "speaking_style": "说话风格",
  "greeting": "开场白",
  "tts_voice": "zh_female_vv_uranus_bigtts"
}
```

### 5. 聊天记录生成角色卡

项目包含工具：

```bash
tools/chat_to_character.py
```

功能：

- 读取聊天记录文本。
- 调用 AI 分析聊天对象的性格、说话习惯和背景特征。
- 自动生成角色卡 JSON。
- 保存到 `characters/` 目录。

使用示例：

```bash
python tools/chat_to_character.py 聊天记录.txt
```

### 6. 图片生成

项目支持连接本地 Stable Diffusion WebUI，也就是 AUTOMATIC1111。

已实现：

- 文本生成图片
- Web 端生图按钮
- 命令行 `/draw` 生图命令
- 默认正向提示词
- 默认反向提示词
- Prompt 自动增强
- 生图参数配置
  - width
  - height
  - steps
  - cfg_scale
  - negative_prompt
- 图片保存到 `generated/` 目录
- Web 端访问生成图片

使用前需要本地启动 Stable Diffusion WebUI，并开启 API：

```bash
webui-user.bat --api
```

默认地址：

```text
http://127.0.0.1:7860
```

### 7. 语音功能

项目已经实现 TTS 和 STT 两条语音能力。

#### TTS：文字转语音

已支持：

- 本地 OmniVoice
- 火山引擎 / 豆包语音合成
- 豆包语音合成 2.0
- 音色选择
- 角色专属音色
- 音频缓存
- Web 端语音播放

当前推荐使用新版控制台 API Key 方式接入火山引擎，不再保留旧版控制台的 App ID / Access Token 设置入口。

豆包语音合成 2.0 推荐配置：

```json
{
  "voice": {
    "tts_provider": "volcengine",
    "stt_provider": "local",
    "volcengine": {
      "api_key": "你的新版控制台 API Key",
      "resource_id": "auto",
      "audio_format": "mp3",
      "sample_rate": 24000,
      "voice_type": "zh_female_vv_uranus_bigtts",
      "model": ""
    }
  }
}
```

如果使用本地 OmniVoice，需要先启动本地语音服务。

#### STT：语音转文字

已支持：

- 本地 faster-whisper
- 火山引擎 ASR 代码实现
- Web 端按住说话
- 语音识别后填入输入框或发送

### 8. Web 设置界面

Web 设置界面已包含：

- API 提供商选择
- OpenAI 兼容 API Key
- Endpoint URL
- 模型名称
- Anthropic API Key
- Anthropic 模型名称
- Temperature
- System Prompt
- 图片生成默认正向提示词
- 图片生成默认反向提示词
- TTS 引擎选择
- STT 引擎选择
- 火山引擎新版控制台 API Key
- Resource ID
- 默认音色
- 重启服务按钮

### 9. 配置系统

配置文件：

```text
config.json
```

示例配置文件：

```text
config.example.json
```

配置管理模块：

```text
config.py
```

主要配置项包括：

- `provider`
- `openai`
- `anthropic`
- `ui`
- `image`
- `voice`
- `voice.volcengine`

默认配置中不应该提交真实 API Key。请把真实密钥只保存在本地 `config.json`，不要提交到 GitHub。

---

## 项目结构

```text
localchat/
├── characters/              # 角色卡 JSON 文件
├── docs/                    # 项目说明或设计文档
├── generated/               # 生成的图片和音频缓存
├── providers/               # 模型和图片生成 Provider
│   ├── openai.py            # OpenAI 兼容接口
│   ├── anthropic.py         # Anthropic Claude 接口
│   └── image.py             # Stable Diffusion WebUI 接口
├── tools/
│   └── chat_to_character.py # 聊天记录生成角色卡工具
├── web/
│   ├── server.py            # FastAPI Web 后端
│   ├── audio_processor.py   # TTS / STT 处理逻辑
│   ├── run_web.bat          # Web 启动脚本
│   └── static/
│       └── index.html       # Web 前端页面
├── character_manager.py     # 角色卡管理
├── config.py                # 配置读取与保存
├── main.py                  # 命令行入口
├── session_manager.py       # 会话管理
├── requirements.txt         # Python 依赖
└── run.bat                  # 命令行启动脚本
```

---

## 安装依赖

建议使用 Python 3.10 或更高版本。

```bash
pip install -r requirements.txt
```

主要依赖包括：

- rich
- prompt-toolkit
- httpx
- fastapi
- uvicorn
- pydantic
- python-multipart
- faster-whisper
- gradio_client
- websocket-client
- ChatTTS
- torch
- torchaudio

---

## 启动方式

### 启动命令行版本

```bash
python main.py
```

或运行：

```bash
run.bat
```

### 启动 Web 版本

```bash
python web/server.py
```

或运行：

```bash
web/run_web.bat
```

启动后在浏览器访问：

```text
http://127.0.0.1:8000
```

---

## 常用命令

命令行端常用命令包括：

```text
/new                新建会话
/list               查看会话列表
/switch <编号>      切换会话
/delete <编号>      删除会话
/rename <名称>      重命名当前会话
/clear              清空当前会话
/export             导出当前会话
/draw <描述>        生成图片
/chat2card <文件>   根据聊天记录生成角色卡
```

---

## 火山引擎 / 豆包语音配置说明

当前项目建议只使用新版控制台 API Key。

Web 设置界面中保留：

- API Key（新版控制台）
- Resource ID
- 默认音色

已删除或不建议继续使用：

- App ID（旧版控制台）
- Access Key / Access Token（旧版控制台）

推荐配置：

```json
{
  "api_key": "你的新版控制台 API Key",
  "resource_id": "auto",
  "audio_format": "mp3",
  "sample_rate": 24000,
  "voice_type": "zh_female_vv_uranus_bigtts",
  "model": ""
}
```

如果出现下面错误：

```text
resource ID is mismatched with speaker related resource
```

通常表示 Resource ID 与音色不匹配。推荐保持：

```json
"resource_id": "auto"
```

并使用豆包 2.0 音色：

```json
"voice_type": "zh_female_vv_uranus_bigtts"
```

---

## 当前已知维护事项

### 1. 部分 Python 文件格式异常

当前 `v4` 分支里有几个 Python 文件在 GitHub Raw 视图中被压缩成一行或极少数几行，不影响一定等于不能运行，但非常不利于维护和继续开发。

建议优先格式化：

```text
config.py
web/server.py
web/audio_processor.py
session_manager.py
providers/openai.py
providers/anthropic.py
providers/image.py
character_manager.py
```

其中最优先处理：

```text
config.py
web/server.py
web/audio_processor.py
```

### 2. 不要提交真实密钥

请不要把下面内容提交到 GitHub：

- OpenAI API Key
- DeepSeek API Key
- Anthropic API Key
- 火山引擎 API Key
- 任何 `sk-` 开头或其他服务商密钥

推荐做法：

- `config.example.json` 只放占位符。
- `config.json` 放入 `.gitignore`。
- 本地运行时只修改本地 `config.json`。

### 3. 建议清理临时文件

项目中如果还存在以下临时文件，可以删除：

```text
README_FIX.md
README_FRONTEND_ONLY.md
patch_frontend_new_console_only.py
patch_remove_old_console.py
remove_old_console_frontend.diff
web/static/index.html.bak
test.txt
statusline.sh
telegram_bot.py
```

---

## 后续优化建议

建议下一步优化顺序：

1. 格式化被压缩成一行的 Python 文件。
2. 修复并验证 Web 设置保存逻辑。
3. 清理补丁脚本、备份文件和临时测试文件。
4. 完善 README、`.gitignore` 和 `config.example.json`。
5. 将火山引擎 TTS / STT 抽象成独立 Provider，减少 `web/audio_processor.py` 体积。
6. 增加启动前配置检查，例如 API Key 是否为空、音色与 Resource ID 是否匹配。
7. 增加日志系统，替代散落的 `print`。
8. 增加基础测试脚本，至少覆盖配置保存、TTS 请求构造、角色卡读写、会话保存。

---

## 项目定位

LocalChat 当前已经具备以下能力：

```text
多模型聊天
多会话管理
角色卡系统
角色独立聊天记录
聊天记录生成角色卡
Stable Diffusion 图片生成
Prompt 自动增强
本地语音识别
火山引擎语音识别
本地 OmniVoice TTS
豆包语音合成 2.0 TTS
Web 设置界面
语音输入和语音播放
```

因此它已经不是简单聊天 Demo，而是一个本地化、多模态、可扩展的 AI 聊天客户端。
