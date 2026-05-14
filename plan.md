# LocalChat 项目功能文档

## 项目概述

LocalChat 是一个本地 AI 聊天客户端，支持双界面操作（终端 + Web），兼容 OpenAI 兼容 API 和 Anthropic Claude。核心功能包括多会话管理、角色卡扮演、图片生成、语音合成与识别。

---

## 一、启动方式

| 方式 | 命令 | 说明 |
|------|------|------|
| 终端 UI | `run.bat` 或 `python main.py` | Rich 终端界面，prompt_toolkit 输入 |
| Web UI | `run_web.bat` 或 `python web/server.py` | FastAPI 服务，浏览器访问 `http://localhost:8000` |

`run_web.bat` 会自动启动 OmniVoice TTS 服务并等待其就绪。

---

## 二、AI 提供商系统

### 支持的提供商
- **OpenAI 兼容**（`providers/openai.py`）：支持 DeepSeek、OpenAI、OpenRouter、Moonshot、智谱等任意兼容接口
  - 通过 `/chat/completions` SSE 流式调用
  - 支持 `/models` 接口列出可用模型
- **Anthropic Claude**（`providers/anthropic.py`）
  - 通过 `/messages` SSE 流式调用
  - system 消息转换为 Anthropic `system` 参数
  - 预置模型列表：claude-sonnet-4-6、claude-opus-4-7、claude-haiku-4-5

### 运行时切换
- 终端：`/provider openai|anthropic`、`/model <name>`、`/key <key>`、`/endpoint <url>`
- Web：设置面板中切换

### 配置持久化
- `config.json` 保存所有配置，支持深合并
- 终端与 Web 共享同一配置

---

## 三、会话管理

### 存储结构
```
sessions/
├── default/          # 普通模式会话
│   ├── 会话 05-14_10-00.json
│   └── ...
└── char_角色名/      # 角色模式会话（自动隔离）
    └── 角色名_2026-05-14_10-00-00.json
```

### 功能列表
- **多会话管理**：创建、切换、删除、重命名
- **自动保存**：每次消息后自动保存
- **上下文构建**：角色系统提示 + 会话系统提示 + 历史消息
- **终端命令**：`/new`、`/list`、`/switch <n>`、`/delete <n>`、`/rename <name>`
- **Web API**：RESTful 端点，前端侧边栏管理
- **会话导出**：导出为 Markdown 文件（终端 `/export`、Web 导出按钮）

---

## 四、角色卡系统

### 角色卡文件
`characters/*.json`，示例结构：

```json
{
  "name": "林冬雪",
  "description": "21岁女生，大四文学院学生",
  "personality": "热情多话，调皮活泼",
  "backstory": "...",
  "speaking_style": "...",
  "greeting": "...",
  "avatar": "🎭",
  "tts_voice": "叶奈法"
}
```

### 功能列表
- **角色卡 CRUD**：创建、读取、更新、删除 → `character_manager.py`
- **激活/卸载**：加载角色卡后进入角色扮演模式，AI 按人设回复
- **开场白**：新角色首次加载时自动发送 greeting
- **会话隔离**：每个角色拥有独立的会话目录 `sessions/char_角色名/`
- **系统提示注入**：`build_system_prompt()` 自动生成角色扮演提示词
- **聊天记录→角色卡**：`tools/chat_to_character.py` 通过 AI 分析聊天记录自动生成角色卡
  - 终端命令：`/chat2card <文件>`
  - 支持直接运行：`python tools/chat_to_character.py <文件>`

### Web 前端管理
- 角色列表查看、新建、编辑、删除
- 角色卡导入/导出 JSON
- 角色音色选择下拉框（从 OmniVoice 获取可用音色列表）

---

## 五、图片生成

### 后端
- **提供商**：Stable Diffusion WebUI (AUTOMATIC1111) via `providers/image.py`
  - 通过 `/sdapi/v1/txt2img` API 调用
  - 支持默认 prompt 合并（正面/负面）
- **AI prompt 增强**：发送到 AI 模型优化描述词再传给 SD
- **参数支持**：宽度、高度、步数、CFG Scale、负面提示词
- **输出位置**：`generated/gen_时间戳_哈希.png`

### 终端用法
```
/draw 一只猫 --w 1024 --h 768 --steps 25 --cfg 7.5 --neg "bad quality"
```

### Web 用法
- `/draw <prompt>` 命令自动路由到图片生成
- 专用 `/api/draw` 端点
- 生成的图片引用自动保存到会话消息中

---

## 六、语音功能

### TTS（文字转语音）
- **引擎**：OmniVoice（本地 Gradio 服务 `http://localhost:7862/`）
- **接口**：`gradio_client` → `api_name="/do_job"`
- **可用音色**：`["jok老师", "叶奈法"]`
- **缓存**：MD5 哈希缓存生成的 wav 到 `generated/tts_*.wav`
- **音色分配**：角色卡 `tts_voice` 字段绑定角色音色

### STT（语音转文字）
- **引擎**：faster-whisper（本地模型 `tiny`）
- **设备**：自动检测 CUDA / CPU
- **语言**：中文优先

### Web 前端功能
- **PTT 按钮**（按住说话）：录制音频 → STT → 发送消息
- **语音播放**：AI 回复自动朗读（可选）
- **音色预览**：角色编辑器中试听音色
- **端点**：
  - `GET /api/tts-voices` — 获取可用音色列表
  - `POST /api/tts` — 文本合成语音
  - `POST /api/stt` — 上传音频识别文字

---

## 七、Web 前端界面

### 技术栈
- 纯 HTML/CSS/JavaScript（无框架）
- `marked.js` Markdown 渲染
- `highlight.js` 代码高亮
- SSE `ReadableStream` 流式读取 AI 回复

### 布局
- **顶栏**：Logo、当前模型、角色标识、设置/角色管理按钮
- **侧边栏**：会话列表（新建/切换/删除）
- **主区域**：消息列表 + 底部输入框
- **输入框**：文本输入 + PTT 按钮 + 发送按钮

### 功能列表
- **聊天**：消息发送、流式显示、Markdown 渲染（代码高亮）
- **消息操作**：编辑消息（截断重流）、重新生成最后一条 AI 回复、删除单条消息
- **设置面板**：Provider 切换、API Key / Endpoint / Model 配置、Temperature、SD 默认 prompt
- **角色管理**：新建/编辑/删除角色卡、角色导入/导出 JSON、音色选择
- **图片生成**：`/draw` 命令自动识别并生成图片
- **语音**：PTT 录音、TTS 播放、音色预览
- **主题**：深色主题（Tokyo Night 风格）

---

## 八、命令行终端界面

### 技术栈
- `rich`：Markdown 渲染、Panel、Table、Spinner
- `prompt_toolkit`：输入历史、自动建议、快捷键

### 命令列表

| 命令 | 功能 |
|------|------|
| `/help` | 显示帮助 |
| `/model <name>` | 切换模型 |
| `/models` | 列出可用模型 |
| `/provider <type>` | 切换提供商 |
| `/key <key>` | 设置 API Key |
| `/endpoint <url>` | 设置 API 端点 |
| `/new` | 新建会话 |
| `/list` | 列出会话 |
| `/switch <n>` | 切换会话 |
| `/rename <name>` | 重命名会话 |
| `/delete <n>` | 删除会话 |
| `/system <text>` | 设置系统提示词 |
| `/temp <n>` | 设置温度 |
| `/draw <prompt>` | 生成图片 |
| `/clear` | 清空会话 |
| `/export` | 导出会话 |
| `/info` | 会话信息 |
| `/characters` | 列出角色卡 |
| `/character <name>` | 加载角色卡 |
| `/character_stop` | 卸载角色卡 |
| `/character_show` | 显示当前角色卡 |
| `/chat2card <file>` | 聊天记录→角色卡 |
| `/exit` | 退出 |

---

## 九、配置文件

`config.json`（自动生成，已 .gitignore）：

```json
{
  "provider": "openai",
  "openai": { "api_key": "...", "base_url": "...", "model": "deepseek-chat" },
  "anthropic": { "api_key": "", "model": "claude-sonnet-4-6" },
  "ui": { "theme": "dracula", "max_tokens": 4096, "temperature": 0.7 },
  "image": {
    "provider": "sd_webui",
    "sd_webui": {
      "base_url": "http://127.0.0.1:7860",
      "default_prompt": "masterpiece, best quality, highly detailed",
      "default_negative_prompt": "nsfw, low quality, distorted, deformed, blurry, bad anatomy"
    }
  }
}
```

`config.example.json` 为可提交 Git 的模板。

---

## 十、项目结构

```
localchat/
├── main.py                    # 终端 UI 入口
├── run.bat                    # 终端启动脚本
├── config.py                  # 配置管理
├── config.json                # 用户配置（已 gitignore）
├── config.example.json        # 配置模板
├── session_manager.py         # 会话管理
├── character_manager.py       # 角色卡管理
├── CLAUDE.md                  # 项目 AI 助手指南
├── requirements.txt           # Python 依赖
├── providers/
│   ├── base.py                # Provider 抽象基类 + ChatMessage
│   ├── openai.py              # OpenAI 兼容提供商
│   ├── anthropic.py           # Anthropic Claude 提供商
│   └── image.py               # Stable Diffusion 图片生成
├── tools/
│   └── chat_to_character.py   # 聊天记录→角色卡
├── web/
│   ├── server.py              # FastAPI Web 服务
│   ├── run_web.bat            # Web 启动脚本（含 OmniVoice 自启）
│   ├── audio_processor.py     # TTS/STT 音频处理
│   └── static/
│       └── index.html         # Web 前端单页应用
├── characters/                # 角色卡 JSON 文件
│   ├── 林冬雪.json
│   ├── 小爱.json
│   ├── 小琪.json
│   ├── chen_phd.json
│   ├── li_detective.json
│   └── lin_mengyao.json
├── sessions/                  # 会话数据（自动生成）
├── generated/                 # 生成文件（图片、语音缓存）
├── docs/                      # 设计文档
└── plan.md                    # 本文件
```

---

## 十一、依赖清单

| 包 | 用途 |
|----|------|
| `rich` | 终端富文本渲染 |
| `prompt-toolkit` | 终端输入历史/自动建议 |
| `httpx` | HTTP 异步请求 |
| `fastapi` + `uvicorn` | Web 服务器 |
| `faster-whisper` | 本地语音识别 |
| `gradio-client` | OmniVoice TTS 调用 |
| `pydantic` | FastAPI 请求模型 |
