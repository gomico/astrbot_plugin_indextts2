# AstrBot IndexTTS v2.5

本插件大量参考了 [astrbot_plugin_GPT_SoVITS](https://github.com/Zhalslar/astrbot_plugin_GPT_SoVITS)，适配 IndexTTS v2.5版本。插件连接已经启动的 [IndexTTS 2.5 FastAPI 服务](https://github.com/gomico/index-tts2-api)，不在 AstrBot 内加载模型。

## 配置与首次使用

1. 按 API 服务说明启动服务（默认 `http://127.0.0.1:8000`）。
2. 默认音色参考路径为 `voices/subaru.wav`；如需更换，在插件配置中修改 `tts.speaker_audio`。
3. `tts.speaker_audio` 和每个 `emotion.entries[].emotion_audio` 都必须填写为 **相对于 API 服务启动参数 `--reference-dir` 的路径**。
4. 配置情感条目后发送 `说 你好，今天真开心`；发送 `TTS情绪` 查看名称。

### 参考音频路径

参考音频位于运行 IndexTTS API 的服务器上，而不是 AstrBot 所在主机上。插件只会把配置的路径原样发送给 API，不会在本地查找、转换或上传音频。

例如 API 在 IndexTTS 项目根目录这样启动：

```powershell
.\run_api.ps1 --reference-dir prompts
```

服务器端目录为：

```text
prompts/
├── voices/
│   └── subaru.wav
└── emotions/
    └── subaru_happy.wav
```

对应的插件配置应为：

```yaml
tts:
  speaker_audio: voices/subaru.wav
  default_emotion_weight: 0.8

emotion:
  entries:
    - name: 开心
      keywords:
        - 开心
        - 哈哈
      emotion_audio: emotions/subaru_happy.wav
      emotion_weight: 0.8
```

插件首次生成配置时会预置上面的“开心”情感条目。全局合成默认情感权重和新建情感条目的默认权重均为 `0.8`；可根据参考音频的表现再单独调整。

相对路径可以直接写成 `voices/subaru.wav`，也允许在开头添加 `./`，例如 `./voices/subaru.wav`。推荐始终使用正斜杠 `/`，它在 Windows 和 Linux API 服务器上都可用；反斜杠 `\` 可在 Windows API 服务器上作为目录分隔符，但在 Linux 上会被当作普通字符，因此不建议用于跨平台配置。

不要在配置值前重复添加 `prompts/`，也不要填写 AstrBot 主机上的绝对路径。例如 `prompts/voices/subaru.wav`、`C:\voices\subaru.wav` 和包含 `..` 的路径都是错误的。API 当前只接受 `--reference-dir` 内的 `.wav` 普通文件。

### 手动命令

命令名与参数之间使用空格，多个参数之间使用两个连续的 `&`：

```text
/说 <文本>
/说 EN&&<文本>
/说情绪 开心&&<文本>
/说情绪 EN&&开心&&<文本>
```

`/说 <文本>` 会使用同一次 LLM 调用判断语言和情感；显式提供语言时只自动判断情感。`/说情绪 开心&&<文本>` 使用指定情感并由 LLM 判断语言；同时指定语言和情感时不调用分类 LLM。支持的语言代码为 `ZH/EN/JA/AR/ES`，判断失败时回退到 `tts.default_language`。

空格分隔的旧多参数写法不再支持。命令别名为 `itts` 和 `itts_emo`，其他命令为 `TTS情绪`、`TTS状态`。

自动模式只替换完全由 Plain 文本组成的 LLM 回复。概率、长度和文本适读性在调用情感模型之前检查；失败时保留原文本。关键词命中按配置条目顺序优先。`selection_mode=llm` 时要求模型严格返回一个已配置的 JSON 标签，失败后可按 `fallback_to_keyword` 回退。

两个 Tool 为 `indextts_list_emotions()` 和 `indextts_tts(message, emotion, language)`。后者始终要求有效 `emotion`，缺失或无效时不会请求 API 或读写缓存。

缓存使用请求内容、参考音频相对标识、语言、时长和 namespace 的 SHA-256。更换模型或覆盖同名参考文件后，请修改 `cache.namespace`。不要把 API 密钥写入日志或截图；远程 API 应配置密钥并使用 HTTPS。
