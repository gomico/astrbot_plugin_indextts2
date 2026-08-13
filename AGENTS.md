# Repository Guidelines

## Project Structure & Module Organization

`main.py` is the AstrBot entry point and owns lifecycle hooks, commands, automatic reply conversion, and LLM tools. `_conf_schema.json` defines the WebUI configuration. `core/` separates HTTP transport, configuration, language/emotion classification, cache management, text cleanup, and synthesis orchestration. `tests/` contains model-free unit and plugin behavior tests. Runtime data belongs in AstrBot's plugin data directory, never inside this repository.

Root metadata files (`metadata.yaml`, `requirements.txt`, `README.md`, and `LICENSE`) must remain compatible with AstrBot's plugin loader. The plugin is licensed under AGPL-3.0-or-later and derives from `astrbot_plugin_GPT_SoVITS`; preserve attribution and license notices.

## Build, Test, and Development Commands

- `python -m compileall -q .` checks all Python modules.
- `python -m unittest discover -s tests -v` runs the complete model-free suite.
- `python -m json.tool _conf_schema.json > NUL` validates the schema on Windows.
- `python -m json.tool _conf_schema.json >/dev/null` validates the schema on Linux/macOS.
- Install runtime dependencies with `python -m pip install -r requirements.txt` when testing inside AstrBot.

Real API and AstrBot end-to-end checks are manual; unit tests use compatibility stubs and fake clients.

## Coding Style & Naming Conventions

Use four-space indentation, type hints, `snake_case` functions, and `PascalCase` classes. Keep AstrBot-specific imports behind `core/runtime.py` so tests work without AstrBot installed. Async handlers must not perform blocking I/O. Configuration defaults in `core/config.py` and `_conf_schema.json` must stay synchronized.

## Testing Guidelines

Use `unittest`, including `IsolatedAsyncioTestCase` for async behavior. Name tests `test_<behavior>`. Add coverage for command parsing, LLM JSON validation and fallback, API error mapping, cache expiry/atomic writes, event deduplication, and failure paths that preserve text replies. Tests must not call a real LLM or TTS server.

## Commit & Pull Request Guidelines

Use Conventional Commit subjects such as `feat: detect language for TTS commands`, `fix: preserve fallback text`, or `docs: clarify paths`. PRs should summarize user-visible behavior, configuration changes, and test results. Include screenshots only for configuration UI changes.

## Security & Configuration Tips

Never log API keys, full long prompts, absolute API-server paths, or tracebacks sent to chat. Treat `speaker_audio` and `emotion_audio` as server-relative identifiers; do not resolve them on the AstrBot host.
