# AstrBot IndexTTS 2.5

该插件连接已经启动的 IndexTTS 2.5 FastAPI 服务，不在 AstrBot 内加载模型。

## 配置与首次使用

1. 按 API 服务说明启动服务（默认 `http://127.0.0.1:8000`）。
2. 在插件配置中填写 `tts.speaker_audio`，例如 `voices/character_neutral.wav`。
3. 该字段和每个 `emotion.entries[].emotion_audio` 都是 **API 服务器 `reference-dir` 下的相对路径**；插件不会也不能在 AstrBot 主机检查或转换它们。
4. 配置情感条目后发送 `说 你好，今天真开心`；发送 `TTS情绪` 查看名称。

命令：`说 <文本>`（别名 `itts`）、`说情绪 <情感名> <文本>`（别名 `itts_emo`）、`TTS情绪`、`TTS状态`。

自动模式只替换完全由 Plain 文本组成的 LLM 回复。概率、长度和文本适读性在调用情感模型之前检查；失败时保留原文本。关键词命中按配置条目顺序优先。`selection_mode=llm` 时要求模型严格返回一个已配置的 JSON 标签，失败后可按 `fallback_to_keyword` 回退。

两个 Tool 为 `indextts_list_emotions()` 和 `indextts_tts(message, emotion, language)`。后者始终要求有效 `emotion`，缺失或无效时不会请求 API 或读写缓存。

缓存使用请求内容、参考音频相对标识、语言、时长和 namespace 的 SHA-256。更换模型或覆盖同名参考文件后，请修改 `cache.namespace`。不要把 API 密钥写入日志或截图；远程 API 应配置密钥并使用 HTTPS。
