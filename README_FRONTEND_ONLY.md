# 只删除前端旧版控制台入口

本补丁只修改：

```text
web/static/index.html
```

删除内容：

```text
App ID（旧版控制台）
Access Key（旧版控制台）
— 或者 —
inputVolcAppId
inputVolcToken
```

保留内容：

```text
API Key（新版控制台）
Resource ID
默认音色
TTS / STT 引擎选择
```

## 使用方式

把 `patch_frontend_new_console_only.py` 放到项目根目录，然后执行：

```bash
python patch_frontend_new_console_only.py
```

执行后会生成备份：

```text
web/static/index.html.bak
```

如果你想手工改，也可以参考 `remove_old_console_frontend.diff`。
