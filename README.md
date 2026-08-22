# AstrBot IndexTTS 2.5

本插件大量参考了 [astrbot_plugin_GPT_SoVITS](https://github.com/Zhalslar/astrbot_plugin_GPT_SoVITS)，适配 IndexTTS 2.5。插件连接已经启动的 [IndexTTS 2.5 FastAPI 服务](https://github.com/gomico/index-tts2-api)，不在 AstrBot 内加载模型。

## 配置与首次使用

1. 按 API 服务说明启动服务（默认 `http://127.0.0.1:8000`）。
2. 默认音色参考路径为 `voices/subaru.wav`；如需更换，在插件配置界面的`合成默认值`中修改`服务器端音色参考相对路径`（`tts.speaker_audio`）。
3. 情感控制在插件配置界面的`情感选择`→`控制模式`中选择。默认的`参考音频控制`使用`参考音频情感条目`（`emotion.entries`）；`向量控制`使用`向量情感条目`（`emotion.vector_entries`），需要已支持 `emotion_vector` 的 IndexTTS API。旧版 API 仍可使用参考音频模式。
4. 配置情感条目后发送 `说 你好，今天真开心`；发送 `TTS情感` 查看名称。

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

插件首次生成配置时会预置上面的`开心`参考音频情感条目。全局合成默认情感权重和新建情感条目的默认权重均为 `0.8`；可根据参考音频的表现再单独调整。

### 向量情感控制

向量控制不读取或上传情感音频，只向 API 发送 8 维 `emotion_vector`。维度顺序固定为：`喜、怒、哀、惧、厌恶、低落、惊喜、平静`，对应配置键 `happy、angry、sad、afraid、disgusted、melancholic、surprised、calm`；每个值范围为 `0.0–1.0`，步长为 `0.05`。

默认向量示例：

```yaml
emotion:
  control_mode: vector
  vector_entries:
    - name: 开心
      keywords:
        - 开心
        - 哈哈
        - 太棒了
      emotion_weight: 0.8
      happy: 0.6
      angry: 0.0
      sad: 0.0
      afraid: 0.0
      disgusted: 0.0
      melancholic: 0.0
      surprised: 0.2
      calm: 0.0
    - name: 平静
      keywords:
        - 平静
      emotion_weight: 0.8
      happy: 0.05
      angry: 0.0
      sad: 0.05
      afraid: 0.0
      disgusted: 0.0
      melancholic: 0.1
      surprised: 0.0
      calm: 0.6
    - name: 紧张
      keywords:
        - 紧张
      emotion_weight: 0.8
      happy: 0.0
      angry: 0.35
      sad: 0.0
      afraid: 0.2
      disgusted: 0.0
      melancholic: 0.0
      surprised: 0.25
      calm: 0.0
    - name: 难过
      keywords:
        - 难过
      emotion_weight: 0.8
      happy: 0.0
      angry: 0.0
      sad: 0.45
      afraid: 0.0
      disgusted: 0.0
      melancholic: 0.25
      surprised: 0.0
      calm: 0.1
```

插件预置的四组情感向量名称依次为`开心`、`平静`、`紧张`、`难过`，每组的 `emotion_weight` 均为 `0.8`。这些向量仅供参考，不代表固定的最佳效果；你可以根据所使用的模型、音色和实际文本表现调整各维度数值。

旧配置缺少 `control_mode` 时默认使用参考音频模式；当 `control_mode: vector` 但未配置 `vector_entries` 时，插件会从默认配置补充这四组向量条目，并继续使用向量模式。切换模式不会删除另一套条目。参考音频路径始终按 API 服务端 `--reference-dir` 的相对路径处理。

相对路径可以直接写成 `voices/subaru.wav`，也允许在开头添加 `./`，例如 `./voices/subaru.wav`。推荐始终使用正斜杠 `/`，它在 Windows 和 Linux API 服务器上都可用；反斜杠 `\` 可在 Windows API 服务器上作为目录分隔符，但在 Linux 上会被当作普通字符，因此不建议用于跨平台配置。

不要在配置值前重复添加 `prompts/`，也不要填写 AstrBot 主机上的绝对路径。例如 `prompts/voices/subaru.wav`、`C:\voices\subaru.wav` 和包含 `..` 的路径都是错误的。API 当前只接受 `--reference-dir` 内的 `.wav` 普通文件。

### 手动命令

命令名与参数之间使用空格，多个参数之间使用两个连续的 `&`：

```text
/说 <文本>
/说 EN&&<文本>
/说情感 开心&&<文本>
/说情感 EN&&开心&&<文本>
```

`/说 <文本>` 会使用同一次 LLM 调用判断语言和情感；显式提供语言时只自动判断情感。`/说情感 开心&&<文本>` 使用指定情感并由 LLM 判断语言；同时指定语言和情感时不调用分类 LLM。支持的语言代码为 `ZH/EN/JA/AR/ES`，判断失败时回退到 `tts.default_language`。

空格分隔的旧多参数写法不再支持。`/说` 的别名是 `itts`，`/说情感` 的别名是 `itts_emo` 和旧名 `说情绪`；命令除 `TTS情感`（兼容旧名 `TTS情绪`）外还有 `TTS统计`、`TTS状态`。

`TTS统计` 默认查看累计统计，也可以附带日期查看当天统计：

```text
/TTS统计
/TTS统计 2026-08-22
```

返回格式如下，`bot`、`command`、`auto` 分别表示 LLM Tool、手动命令和自动语音回复来源：

```text
情感统计：
开心: 3（bot:1、command:1、auto:1）
none: 9（bot:0、command:0、auto:9）
```

自动模式只替换完全由 Plain 文本组成的 LLM 回复。文本长度需在 `auto.min_text_length`（默认 `5`）到 `auto.max_text_length` 之间，之后才进行概率触发和情感判断；失败时保留原文本。关键词命中按配置条目顺序优先。`selection_mode=llm` 时要求模型严格返回一个已配置的 JSON 标签，失败后可按 `fallback_to_keyword` 回退。

两个 Tool 为 `indextts_list_emotions()` 和 `indextts_tts(message, emotion, language)`。后者始终要求有效 `emotion`，缺失或无效时不会请求 API 或读写缓存。

插件会自动缓存已经生成的语音，以便相同内容再次合成时直接复用。`cache.namespace` 是缓存版本标识，不是缓存路径；缓存路径由 `cache.path` 控制。更换 API 使用的模型，或替换服务器上的同名参考音频后，请修改`缓存命名空间`（`cache.namespace`），避免继续使用旧缓存。远程 API 建议配置 API 密钥并使用 HTTPS；请妥善保管密钥，不要将其分享给他人。

## 许可证

本项目基于 [GNU Affero General Public License v3.0 or later](LICENSE) 发布，Copyright (C) 2026 gomico。

本插件参考并改编了采用 AGPL v3 发布的 [astrbot_plugin_GPT_SoVITS](https://github.com/Zhalslar/astrbot_plugin_GPT_SoVITS)。分发修改版本或通过网络向用户提供服务时，请遵守 AGPL 的源代码提供义务。
